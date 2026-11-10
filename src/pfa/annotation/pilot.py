"""Coordinator-operated pilot workflow; real actions require existing human/data evidence."""

import csv
import json
import os
import random
import subprocess
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime
from functools import wraps
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal

from pydantic import Field, model_validator

from pfa.annotation import agreement
from pfa.annotation import pilot_store as store
from pfa.annotation.approval import requests, require_taxonomy, reviewed_time
from pfa.annotation.io import COLUMNS, annotation_rows, inventory, metadata_path
from pfa.annotation.schema import (
    Annotation,
    AnnotationMetadata,
    AnnotatorID,
    BlankAnnotation,
    DatasetVersion,
    FeedbackID,
)
from pfa.annotation.taxonomy import CHECKSUM, VERSION, load_taxonomy
from pfa.data import official, profiling
from pfa.data.official_io import (
    IngestionBlocked,
    IngestionError,
    protect_directory,
    rows,
    safe_path,
    windows_sid,
    write_json,
)
from pfa.data.official_schema import Feedback, ImportOptions
from pfa.data.permissions import current_decision
from pfa.data.preprocessing import normalize_text
from pfa.data.privacy import audit_screen
from pfa.data.quality import ProfileContext, QualityConfig
from pfa.data.registry import Identifier, Metadata, Registry


class Actor(Metadata):
    annotator_id: AnnotatorID
    windows_sid: str = Field(pattern=r"^S-1-[0-9-]+$")


class PilotPlan(Metadata):
    plan_ref: Identifier
    dataset_type: Literal["SYNTHETIC", "RESEARCH"]
    source_id: Identifier
    dataset_version: DatasetVersion
    target_count: int = Field(ge=2, le=5000)
    seed: int = Field(ge=0, le=2**32 - 1)
    coordinator_sid: str = Field(pattern=r"^S-1-[0-9-]+$")
    annotators: dict[str, Actor]
    adjudicator: Actor
    submission_deadline: str
    reviewer_id: Identifier
    evidence_reference: Identifier
    reviewed_at: str
    human_verified: bool

    @model_validator(mode="after")
    def independent(self) -> "PilotPlan":
        reviewed_time(self.reviewed_at)
        deadline = datetime.fromisoformat(self.submission_deadline)
        if deadline.tzinfo is None or set(self.annotators) != {"A", "B"}:
            raise ValueError("Two independent actors A/B and a timezone-aware deadline required")
        actors = [*self.annotators.values(), self.adjudicator]
        if (
            len({item.annotator_id for item in actors}) != 3
            or len({self.coordinator_sid, *(item.windows_sid for item in actors)}) != 4
        ):
            raise ValueError("Coordinator, A, B and adjudicator need distinct OS accounts")
        if self.dataset_type == "RESEARCH" and not self.human_verified:
            raise ValueError("Existing human-verified research plan required")
        if self.reviewer_id in {"unknown", "pending"} or self.evidence_reference in {
            "unknown",
            "pending",
        }:
            raise ValueError("Responsible human and protected plan evidence references required")
        if self.dataset_type == "SYNTHETIC" and self.human_verified:
            raise ValueError("Synthetic plans must never impersonate human approval")
        return self


class PilotManifest(Metadata):
    format_version: Literal["pilot-1"]
    pilot_id: Identifier
    dataset_type: Literal["SYNTHETIC", "RESEARCH"]
    dataset_version: DatasetVersion
    source_id: Identifier
    source_manifest_checksum: str
    taxonomy_version: Literal[VERSION]
    taxonomy_checksum: Literal[CHECKSUM]
    taxonomy_approval_checksum: str | None
    plan: PilotPlan
    selected_ids: list[FeedbackID]
    sampling: dict
    duplicate_groups: dict[str, str]

    @model_validator(mode="after")
    def bound(self) -> "PilotManifest":
        if (
            len(self.selected_ids) != len(set(self.selected_ids))
            or len(self.selected_ids) != self.plan.target_count
        ):
            raise ValueError("Pilot sample count or uniqueness invalid")
        if (self.dataset_type, self.dataset_version, self.source_id) != (
            self.plan.dataset_type,
            self.plan.dataset_version,
            self.plan.source_id,
        ):
            raise ValueError("Plan and pilot provenance mismatch")
        if self.dataset_type == "RESEARCH" and not self.taxonomy_approval_checksum:
            raise ValueError("Real pilot requires taxonomy approval provenance")
        if self.dataset_type == "SYNTHETIC" and self.taxonomy_approval_checksum is not None:
            raise ValueError("Synthetic pilot cannot claim human approval")
        if set(self.duplicate_groups) != set(self.selected_ids):
            raise ValueError("Every selected record requires group lineage")
        return self


def location(root: Path, pilot_id: str) -> Path:
    return safe_path(store.base(root) / "pilots" / store.identifier(pilot_id), root)


def require_operator(root: Path, plan: PilotPlan) -> None:
    if plan.dataset_type == "SYNTHETIC":
        store.require_synthetic(root)
    elif os.name != "nt" or windows_sid() != plan.coordinator_sid:
        raise IngestionBlocked("Designated Windows coordinator account required")


def source_metadata(plan: PilotPlan) -> AnnotationMetadata:
    return AnnotationMetadata(
        format_version="annotation-1",
        purpose="ANNOTATION_SUBMISSION",
        taxonomy_version=VERSION,
        taxonomy_checksum=CHECKSUM,
        dataset_type=plan.dataset_type,
        source_id=plan.source_id,
        dataset_version=plan.dataset_version,
        columns=COLUMNS,
        human_gold=False,
    )


def sample_records(
    records: list[Feedback],
    n: int,
    seed: int,
    key: bytes,
    groups: dict[str, str] | None = None,
) -> tuple[list[str], dict, dict[str, str]]:
    """Proportional domain/month stratified pseudorandom sample; no topic inference."""
    if not 2 <= n <= 5000 or not 0 <= seed < 2**32 or len(key) < 32:
        raise IngestionError("Invalid pilot count, seed or fingerprint key")
    unique, seen_ids, seen_text = [], set(), set()
    for item in sorted(records, key=lambda record: record.feedback_id):
        content = official.fingerprint(
            key, "pilot-normalized-content", normalize_text(item.content)
        )
        if item.feedback_id in seen_ids or content in seen_text:
            continue
        seen_ids.add(item.feedback_id)
        seen_text.add(content)
        unique.append(item)
    if len(unique) < n:
        raise IngestionError(
            "Insufficient eligible unique records; sampling with replacement forbidden"
        )
    strata = defaultdict(list)
    for item in unique:
        month = (
            item.created_at.astimezone(UTC).strftime("%Y-%m")
            if item.created_at and item.created_at.tzinfo
            else "UNKNOWN"
        )
        stratum = official.fingerprint(key, "pilot-domain-month", json.dumps([item.domain, month]))
        strata[stratum].append(item.feedback_id)
    rng = random.Random(seed)
    size = len(unique)
    quotas = {name: n * len(values) // size for name, values in sorted(strata.items())}
    priority = sorted(strata, key=lambda name: (-(n * len(strata[name]) % size), rng.random()))
    for name in priority[: n - sum(quotas.values())]:
        quotas[name] += 1
    selected = []
    for name in sorted(strata):
        selected.extend(rng.sample(strata[name], quotas[name]))
    rng.shuffle(selected)
    lineage = {
        record_id: (groups or {}).get(record_id)
        or "g_" + official.fingerprint(key, "pilot-group", record_id)
        for record_id in selected
    }
    return (
        selected,
        {
            "algorithm": "proportional_domain_utc_month_largest_remainder_random_v1",
            "runtime": "Python 3.11 stdlib random",
            "method": "STRATIFIED_RANDOM",
            "seed": seed,
            "requested_count": n,
            "selected_count": len(selected),
            "input_count": len(records),
            "unique_count": size,
            "exact_duplicate_count": len(records) - size,
            "strata": {
                name: {"available": len(strata[name]), "selected": quotas[name]}
                for name in sorted(strata)
            },
            "missing_domain_count": sum(item.domain is None for item in unique),
            "unknown_time_count": sum(
                not item.created_at or not item.created_at.tzinfo for item in unique
            ),
            "representativeness": "Not established; sparse strata may receive zero quota",
        },
        lineage,
    )


def _create(
    root: Path,
    pilot_id: str,
    plan: PilotPlan,
    records: list[Feedback],
    key: bytes,
    source_checksum: str,
    approval_checksum: str | None,
    quality: dict,
    groups: dict[str, str],
) -> PilotManifest:
    require_operator(root, plan)
    selected, criteria, lineage = sample_records(records, plan.target_count, plan.seed, key, groups)
    manifest = PilotManifest(
        format_version="pilot-1",
        pilot_id=pilot_id,
        dataset_type=plan.dataset_type,
        dataset_version=plan.dataset_version,
        source_id=plan.source_id,
        source_manifest_checksum=source_checksum,
        taxonomy_version=VERSION,
        taxonomy_checksum=CHECKSUM,
        taxonomy_approval_checksum=approval_checksum,
        plan=plan,
        selected_ids=selected,
        sampling=criteria,
        duplicate_groups=lineage,
    )
    documents = {"manifest.json": manifest.model_dump(), "quality.json": quality}
    if plan.dataset_type == "SYNTHETIC":
        documents["synthetic_records.json"] = [record.model_dump(mode="json") for record in records]
    store.publish(location(root, pilot_id) / "definition", documents)
    return manifest


def sample_pilot(
    root: Path,
    registry: Registry,
    source_id: str,
    n: int = 200,
    seed: int = 42,
    pilot_id: str = "pilot_v1",
    plan_ref: str = "pilot_v1",
    key: bytes | None = None,
) -> dict:
    taxonomy_approval = require_taxonomy(root)
    decision = current_decision(root, registry, source_id)
    official.authorize(root, registry, source_id, decision.approval_ref if decision else "")
    plan = PilotPlan.model_validate(store.read_json(requests(root, plan_ref)))
    if (plan.plan_ref, plan.source_id, plan.target_count, plan.seed, plan.dataset_type) != (
        plan_ref,
        source_id,
        n,
        seed,
        "RESEARCH",
    ):
        raise IngestionBlocked("Human plan must match requested real pilot scope, count and seed")
    require_operator(root, plan)
    if datetime.fromisoformat(plan.submission_deadline) <= datetime.now(UTC):
        raise IngestionBlocked("Pilot submission deadline already passed")
    allowed, checksum = inventory(root, registry, source_metadata(plan))
    if key is None or len(key) < 32:
        raise IngestionError("Protected fingerprint key required for real pilot diagnostics")
    data_path = safe_path(root / "data/processed" / plan.dataset_version / "feedback.jsonl", root)
    context = ProfileContext(
        dataset_source=source_id,
        dataset_version=plan.dataset_version,
        dataset_type="RESEARCH",
        expected_record_source=source_id,
        source_manifest_reference=plan.dataset_version,
        source_manifest_checksum=checksum,
        permission_verified=True,
        manifest_verified=True,
        human_reviewed=True,
    )
    with data_path.open("rb") as stream:
        report, audit = profiling.profile_records(
            rows(stream, ".jsonl", ImportOptions()), context, key, QualityConfig()
        )
    if not report.publication_eligible:
        raise IngestionBlocked("Quality/privacy review gates must pass before real pilot sampling")
    records = []
    with data_path.open("rb") as stream:
        for _, row in rows(stream, ".jsonl", ImportOptions()):
            records.append(Feedback.model_validate(row))
    by_ref = {
        entry["record_ref"]: records[entry["ordinal"] - 1].feedback_id
        for entry in audit["record_audit"]
    }
    groups = {by_ref[item["record_ref"]]: item["group_id"] for item in audit["split_group_lineage"]}
    if (
        inventory(root, registry, source_metadata(plan)) != (allowed, checksum)
        or require_taxonomy(root) != taxonomy_approval
    ):
        raise IngestionBlocked("Research provenance changed during sampling")
    manifest = _create(
        root, pilot_id, plan, records, key, checksum, taxonomy_approval, report.model_dump(), groups
    )
    return {
        "status": "PILOT_SAMPLED",
        "pilot": manifest.pilot_id,
        "count": n,
        "dataset_type": "RESEARCH",
        "human_gold": False,
    }


def load_pilot(root: Path, registry: Registry, pilot_id: str) -> tuple[PilotManifest, str]:
    documents, checksum = store.bundle(location(root, pilot_id) / "definition")
    manifest = PilotManifest.model_validate(documents.get("manifest.json"))
    if manifest.pilot_id != pilot_id:
        raise IngestionError("Pilot identity mismatch")
    load_taxonomy(root)
    require_operator(root, manifest.plan)
    if manifest.dataset_type == "SYNTHETIC":
        store.require_synthetic(root)
    else:
        if require_taxonomy(root) != manifest.taxonomy_approval_checksum:
            raise IngestionBlocked("Pilot taxonomy approval is no longer current")
        plan = PilotPlan.model_validate(store.read_json(requests(root, manifest.plan.plan_ref)))
        if plan != manifest.plan:
            raise IngestionBlocked("Pilot plan differs from the reviewed snapshot")
        ids, source_checksum = inventory(root, registry, source_metadata(plan))
        if (
            source_checksum != manifest.source_manifest_checksum
            or not set(manifest.selected_ids) <= ids
        ):
            raise IngestionBlocked("Pilot dataset membership or provenance changed")
    return manifest, checksum


def _records(root: Path, manifest: PilotManifest) -> dict[str, Feedback]:
    if manifest.dataset_type == "SYNTHETIC":
        store.require_synthetic(root)
        docs, _ = store.bundle(location(root, manifest.pilot_id) / "definition")
        records = [Feedback.model_validate(item) for item in docs["synthetic_records.json"]]
    else:
        path = safe_path(
            root / "data/processed" / manifest.dataset_version / "feedback.jsonl", root
        )
        with path.open("rb") as stream:
            records = [
                Feedback.model_validate(row) for _, row in rows(stream, ".jsonl", ImportOptions())
            ]
    selected = {
        item.feedback_id: item for item in records if item.feedback_id in manifest.selected_ids
    }
    if set(selected) != set(manifest.selected_ids):
        raise IngestionError("Pilot selected records unavailable")
    for item in selected.values():
        if any(
            audit_screen(value).counts
            for name, value in item.model_dump().items()
            if isinstance(value, str) and name not in {"feedback_id", "source_id"}
        ):
            raise IngestionBlocked("New privacy findings require renewed human review")
    return selected


def coordinator_transaction(function: Callable[..., dict]) -> Callable[..., dict]:
    """Serialize corrections, exports and finalization for this local pilot."""

    @wraps(function)
    def locked(
        root: Path, registry: Registry, pilot_id: str, *args: object, **kwargs: object
    ) -> dict:
        load_pilot(root, registry, pilot_id)
        lock = safe_path(location(root, pilot_id) / ".transaction.lock", root)
        try:
            handle = lock.open("x")
        except FileExistsError:
            raise IngestionBlocked(
                "Pilot transaction busy; retry after reviewing the lock"
            ) from None
        try:
            with handle:
                return function(root, registry, pilot_id, *args, **kwargs)
        finally:
            lock.unlink()

    return locked


def delivery(root: Path, pilot_id: str, actor: str) -> Path:
    if actor not in {"A", "B", "adjudicator"}:
        raise IngestionError("Unknown assigned actor")
    return safe_path(
        root / "data/private/annotation_deliveries" / store.identifier(pilot_id) / actor, root
    )


def _grant_actor(path: Path, root: Path, sid: str) -> None:
    protect_directory(path)
    if store.is_synthetic(root):
        return  # Simulated accounts only; no claim of OS isolation in the smoke test.
    result = subprocess.run(
        ["icacls", str(path), "/grant:r", f"*{sid}:(OI)(CI)M"], capture_output=True, check=False
    )
    if result.returncode:
        raise IngestionBlocked("Unable to grant isolated delivery access to designated account")


@coordinator_transaction
def export_assignment(root: Path, registry: Registry, pilot_id: str, actor: str) -> dict:
    manifest, checksum = load_pilot(root, registry, pilot_id)
    if actor not in {"A", "B"}:
        raise IngestionError("Independent assignments require actor A or B")
    if datetime.fromisoformat(manifest.plan.submission_deadline) <= datetime.now(UTC):
        raise IngestionBlocked("Assignment deadline has passed")
    destination = delivery(root, pilot_id, actor)
    assignment_path = location(root, pilot_id) / "assignments" / actor
    if destination.exists() or assignment_path.exists():
        raise IngestionError("Assignment already exported; original work will not be overwritten")
    selected = _records(root, manifest)
    identity = manifest.plan.annotators[actor]
    context = [
        {
            "feedback_id": record_id,
            "content": selected[record_id].content,
            "created_at": selected[record_id].model_dump(mode="json")["created_at"],
            "domain": selected[record_id].domain,
        }
        for record_id in manifest.selected_ids
    ]
    blanks = [
        BlankAnnotation(
            feedback_id=record_id,
            dataset_version=manifest.dataset_version,
            taxonomy_version=VERSION,
            taxonomy_checksum=CHECKSUM,
            source_id=manifest.source_id,
            dataset_type=manifest.dataset_type,
            annotator_id=identity.annotator_id,
            annotation_status="DRAFT",
        ).model_dump(mode="json")
        for record_id in manifest.selected_ids
    ]
    metadata = source_metadata(manifest.plan).model_dump()
    store.private_directory(destination.parent)
    with TemporaryDirectory(prefix=".delivery-", dir=destination.parent) as temporary:
        work = Path(temporary)
        _grant_actor(work, root, identity.windows_sid)
        write_json(
            work / "context.json", {"dataset_type": manifest.dataset_type, "records": context}
        )
        with (work / "annotation.csv").open("x", encoding="utf-8", newline="") as stream:
            if os.name != "nt":
                (work / "annotation.csv").chmod(0o600)
            writer = csv.DictWriter(stream, fieldnames=COLUMNS)
            writer.writeheader()
            writer.writerows(blanks)
            stream.flush()
            os.fsync(stream.fileno())
        write_json(metadata_path(work / "annotation.csv"), metadata)
        receipt = {
            "pilot_checksum": checksum,
            "actor": actor,
            "annotator_id": identity.annotator_id,
            "context_checksum": official.file_digest(work / "context.json"),
            "blank_checksum": official.file_digest(work / "annotation.csv"),
            "metadata": metadata,
            "record_order": manifest.selected_ids,
            "dataset_type": manifest.dataset_type,
            "exported_at": datetime.now(UTC).isoformat(),
        }
        if load_pilot(root, registry, pilot_id)[1] != checksum:
            raise IngestionBlocked("Pilot changed during export")
        store.publish(assignment_path, {"assignment.json": receipt})
        work.rename(destination)
    return {
        "status": "ASSIGNMENT_EXPORTED",
        "actor": actor,
        "count": len(blanks),
        "dataset_type": manifest.dataset_type,
        "delivery_directory": str(destination.relative_to(root)),
        "labels_prefilled": False,
    }


class SubmissionReceipt(Metadata):
    decision_ref: Identifier
    pilot_id: Identifier
    pilot_checksum: str
    actor: Literal["A", "B"]
    revision: int = Field(ge=1, le=100)
    previous_submission_checksum: str | None
    input_checksum: str
    context_checksum: str
    annotator_id: AnnotatorID
    independent_attestation: bool
    human_verified: bool
    reviewed_at: str
    evidence_reference: Identifier


def submissions(root: Path, pilot_id: str, actor: str) -> list[tuple[dict, str]]:
    path = location(root, pilot_id) / "submissions" / actor
    if not path.exists():
        return []
    results = []
    for index, directory in enumerate(sorted(path.iterdir()), 1):
        if directory.name != f"revision_{index:04d}":
            raise IngestionBlocked("Submission history is locked or inconsistent")
        docs, checksum = store.bundle(directory)
        receipt = SubmissionReceipt.model_validate(docs.get("receipt.json"))
        reviewed_time(receipt.reviewed_at)
        if receipt.pilot_id != pilot_id or receipt.actor != actor:
            raise IngestionError("Submission history identity mismatch")
        if (
            SubmissionReceipt.model_validate(store.read_json(requests(root, receipt.decision_ref)))
            != receipt
        ):
            raise IngestionBlocked("Submission receipt differs from recorded human evidence")
        if receipt.revision != index or receipt.previous_submission_checksum != (
            results[-1][1] if results else None
        ):
            raise IngestionError("Submission correction history is inconsistent")
        results.append((docs, checksum))
    return results


@coordinator_transaction
def import_submission(
    root: Path,
    registry: Registry,
    pilot_id: str,
    actor: str,
    input_path: Path,
    receipt_ref: str,
    revision: int = 1,
) -> dict:
    manifest, checksum = load_pilot(root, registry, pilot_id)
    if actor not in {"A", "B"}:
        raise IngestionError("Unknown independent actor")
    if (location(root, pilot_id) / "adjudicated").exists():
        raise IngestionBlocked("Completed adjudication locks all submissions")
    if datetime.now(UTC) > datetime.fromisoformat(manifest.plan.submission_deadline):
        raise IngestionBlocked("Submission/correction deadline has passed")
    assignment, _ = store.bundle(location(root, pilot_id) / "assignments" / actor)
    assigned = assignment["assignment.json"]
    receipt = SubmissionReceipt.model_validate(store.read_json(requests(root, receipt_ref)))
    reviewed_time(receipt.reviewed_at)
    history = submissions(root, pilot_id, actor)
    expected_previous = history[-1][1] if history else None
    if (
        receipt.decision_ref,
        receipt.pilot_id,
        receipt.pilot_checksum,
        receipt.actor,
        receipt.annotator_id,
        receipt.revision,
        receipt.previous_submission_checksum,
    ) != (
        receipt_ref,
        pilot_id,
        checksum,
        actor,
        manifest.plan.annotators[actor].annotator_id,
        revision,
        expected_previous,
    ) or revision != len(history) + 1:
        raise IngestionBlocked(
            "Existing human receipt must match assignment and explicit correction revision"
        )
    synthetic = manifest.dataset_type == "SYNTHETIC"
    if not receipt.independent_attestation or receipt.human_verified == synthetic:
        raise IngestionBlocked(
            "Independent submission attestation and correct human/synthetic provenance required"
        )
    if receipt.evidence_reference in {"unknown", "pending"}:
        raise IngestionBlocked("Existing protected submission evidence reference required")
    if history and any(
        item[0]["receipt.json"]["input_checksum"] == receipt.input_checksum for item in history
    ):
        raise IngestionError(
            "Duplicate submission content; a correction must contain actual changes"
        )
    if datetime.fromisoformat(receipt.reviewed_at) < datetime.fromisoformat(
        assigned["exported_at"]
    ):
        raise IngestionError("Submission receipt predates assignment")
    if history and reviewed_time(receipt.reviewed_at) < reviewed_time(
        history[-1][0]["receipt.json"]["reviewed_at"]
    ):
        raise IngestionError("Correction receipt predates previous submission")
    if (
        receipt.context_checksum != assigned["context_checksum"]
        or assigned["pilot_checksum"] != checksum
    ):
        raise IngestionError("Assignment binding mismatch")
    context_path = safe_path(delivery(root, pilot_id, actor) / "context.json", root)
    if official.file_digest(context_path) != receipt.context_checksum:
        raise IngestionBlocked("Assigned sanitized context was modified")
    input_path = safe_path(input_path if input_path.is_absolute() else root / input_path)
    if not input_path.is_file() or input_path.stat().st_size > 20 * 1024**2:
        raise IngestionError("Bounded submission file required")
    if store.file_checksum(input_path) != receipt.input_checksum:
        raise IngestionBlocked("Input differs from the human-verified submission checksum")
    if store.read_json(metadata_path(input_path), 65536) != assigned["metadata"]:
        raise IngestionBlocked("Submission metadata was modified or unauthorized")
    annotations, seen = [], set()
    for ordinal, row in annotation_rows(input_path):
        if ordinal > len(manifest.selected_ids) or row is None:
            raise IngestionError("Invalid annotation row count or structure")
        try:
            annotation = Annotation.model_validate(row)
        except ValueError:
            raise IngestionError(
                "Invalid submitted annotation; labels, reasons and workflow must validate"
            ) from None
        for field in (
            "dataset_version",
            "taxonomy_version",
            "taxonomy_checksum",
            "source_id",
            "dataset_type",
        ):
            if getattr(annotation, field) != getattr(manifest, field):
                raise IngestionBlocked("Submitted provenance does not match pilot")
        if annotation.annotator_id != receipt.annotator_id or annotation.feedback_id in seen:
            raise IngestionError("Annotator identity mismatch or duplicate submitted record")
        if (
            not datetime.fromisoformat(assigned["exported_at"])
            <= annotation.annotated_at
            <= datetime.fromisoformat(receipt.reviewed_at)
        ):
            raise IngestionError("Annotation timestamp must lie between assignment and receipt")
        seen.add(annotation.feedback_id)
        annotations.append(annotation.model_dump(mode="json"))
    if seen != set(manifest.selected_ids):
        raise IngestionError("Submission must contain every pilot record exactly once")
    if (
        store.file_checksum(input_path) != receipt.input_checksum
        or load_pilot(root, registry, pilot_id)[1] != checksum
    ):
        raise IngestionBlocked("Submission or pilot changed during validation")
    store.publish(
        location(root, pilot_id) / "submissions" / actor / f"revision_{revision:04d}",
        {"annotations.json": annotations, "receipt.json": receipt.model_dump()},
    )
    return {
        "status": "SUBMISSION_IMPORTED",
        "actor": actor,
        "revision": revision,
        "count": len(annotations),
        "dataset_type": manifest.dataset_type,
        "human_gold": False,
    }


def agreement_report(root: Path, registry: Registry, pilot_id: str) -> tuple[dict, str]:
    manifest, checksum = load_pilot(root, registry, pilot_id)
    histories = [submissions(root, pilot_id, actor) for actor in ("A", "B")]
    versions = [history[-1][1] if history else None for history in histories]
    annotations = [
        [Annotation.model_validate(item) for item in history[-1][0]["annotations.json"]]
        if history
        else []
        for history in histories
    ]
    report = agreement.calculate(
        *annotations, manifest.selected_ids, synthetic=manifest.dataset_type == "SYNTHETIC"
    )
    report.update(
        pilot_checksum=checksum, taxonomy_checksum=CHECKSUM, submission_checksums=versions
    )
    current_versions = [
        history[-1][1] if history else None
        for history in (submissions(root, pilot_id, actor) for actor in ("A", "B"))
    ]
    if current_versions != versions or load_pilot(root, registry, pilot_id)[1] != checksum:
        raise IngestionBlocked("Independent submissions changed during agreement calculation")
    version = "agreement_" + store.digest([checksum, versions])[:32]
    path = location(root, pilot_id) / "agreement" / version
    if path.exists():
        stored, _ = store.bundle(path)
        if stored != {"report.json": report}:
            raise IngestionError("Immutable agreement report differs from recomputation")
    else:
        store.publish(path, {"report.json": report})
    return report, version


@coordinator_transaction
def export_review(root: Path, registry: Registry, pilot_id: str) -> dict:
    manifest, checksum = load_pilot(root, registry, pilot_id)
    report, version = agreement_report(root, registry, pilot_id)
    if any(item is None for item in report["submission_checksums"]):
        raise IngestionError("NOT_AVAILABLE: both independent submissions required for review")
    selected = _records(root, manifest)
    destination = delivery(root, pilot_id, "adjudicator")
    if destination.exists():
        raise IngestionError("Review already exported; no silent overwrite")
    store.private_directory(destination.parent)
    with TemporaryDirectory(prefix=".review-", dir=destination.parent) as temporary:
        work = Path(temporary)
        _grant_actor(work, root, manifest.plan.adjudicator.windows_sid)
        write_json(
            work / "review.json",
            {
                "dataset_type": manifest.dataset_type,
                "pilot_checksum": checksum,
                "agreement_version": version,
                "adjudicator_id": manifest.plan.adjudicator.annotator_id,
                "disagreements": report["disagreements"],
                "records": [
                    {"feedback_id": item, "content": selected[item].content}
                    for item in manifest.selected_ids
                ],
                "submission_checksums": report["submission_checksums"],
                "independent_annotations": {
                    actor: submissions(root, pilot_id, actor)[-1][0]["annotations.json"]
                    for actor in ("A", "B")
                },
                "instruction": "Review every record, including agreements; never auto-fill gold",
            },
        )
        work.rename(destination)
    return {
        "status": "CONTROLLED_REVIEW_EXPORTED",
        "dataset_type": manifest.dataset_type,
        "count": len(manifest.selected_ids),
        "human_gold": False,
    }


class AdjudicationDecision(Metadata):
    decision_ref: Identifier
    pilot_id: Identifier
    pilot_checksum: str
    submission_checksums: list[str]
    adjudicator_id: AnnotatorID
    reviewed_at: str
    evidence_reference: Identifier
    human_verified: bool
    approve_final: bool
    final_records: list[Annotation]


@coordinator_transaction
def adjudicate(root: Path, registry: Registry, pilot_id: str, decision_ref: str) -> dict:
    manifest, checksum = load_pilot(root, registry, pilot_id)
    report, version = agreement_report(root, registry, pilot_id)
    decision = AdjudicationDecision.model_validate(store.read_json(requests(root, decision_ref)))
    reviewed_time(decision.reviewed_at)
    synthetic = manifest.dataset_type == "SYNTHETIC"
    if not synthetic and datetime.now(UTC) <= datetime.fromisoformat(
        manifest.plan.submission_deadline
    ):
        raise IngestionBlocked("Research adjudication starts only after the correction deadline")
    if not synthetic and reviewed_time(decision.reviewed_at) < datetime.fromisoformat(
        manifest.plan.submission_deadline
    ):
        raise IngestionBlocked("Human final review must follow the correction deadline")
    if (
        decision.decision_ref,
        decision.pilot_id,
        decision.pilot_checksum,
        decision.adjudicator_id,
        decision.submission_checksums,
    ) != (
        decision_ref,
        pilot_id,
        checksum,
        manifest.plan.adjudicator.annotator_id,
        report["submission_checksums"],
    ) or any(item is None for item in report["submission_checksums"]):
        raise IngestionBlocked("Designated adjudicator and exact independent submissions required")
    if decision.human_verified == synthetic or not decision.approve_final:
        raise IngestionBlocked(
            "Final records require existing human approval; synthetic review stays simulated"
        )
    if decision.evidence_reference in {"unknown", "pending"}:
        raise IngestionBlocked("Human adjudication evidence reference required")
    ids = [item.feedback_id for item in decision.final_records]
    if len(ids) != len(set(ids)) or set(ids) != set(manifest.selected_ids):
        raise IngestionError(
            "Adjudicator must explicitly decide every pilot record, including agreements"
        )
    for item in decision.final_records:
        if (
            item.annotator_id != decision.adjudicator_id
            or item.annotated_at > datetime.fromisoformat(decision.reviewed_at)
        ):
            raise IngestionError("Final record reviewer/timestamp mismatch")
        for field in (
            "dataset_type",
            "dataset_version",
            "source_id",
            "taxonomy_version",
            "taxonomy_checksum",
        ):
            if getattr(item, field) != getattr(manifest, field):
                raise IngestionBlocked(
                    "Synthetic or mismatched records cannot be promoted to research gold"
                )
    load_pilot(root, registry, pilot_id)
    gold = [
        item.model_dump(mode="json")
        for item in decision.final_records
        if item.annotation_status == "SUBMITTED"
    ]
    review_pending = sum(
        item.annotation_status == "REQUIRES_REVIEW" for item in decision.final_records
    )
    summary = {
        "status": "ADJUDICATED_SYNTHETIC" if synthetic else "HUMAN_ADJUDICATED",
        "dataset_type": manifest.dataset_type,
        "human_gold": not synthetic and bool(gold),
        "gold_count": 0 if synthetic else len(gold),
        "synthetic_resolved_count": len(gold) if synthetic else 0,
        "unresolved_count": review_pending,
        "excluded_count": len(ids) - len(gold) - review_pending,
        "pilot_checksum": checksum,
        "taxonomy_checksum": CHECKSUM,
        "agreement_version": version,
        "submission_checksums": report["submission_checksums"],
    }
    store.publish(
        location(root, pilot_id) / "adjudicated",
        {
            "decision.json": decision.model_dump(mode="json"),
            "manifest.json": summary,
            "resolved_records.json": gold,
        },
    )
    return summary


def verify_pilot(root: Path, registry: Registry, pilot_id: str) -> dict:
    manifest, checksum = load_pilot(root, registry, pilot_id)
    report, version = agreement_report(root, registry, pilot_id)
    docs, _ = store.bundle(location(root, pilot_id) / "adjudicated")
    summary = docs["manifest.json"]
    decision = AdjudicationDecision.model_validate(docs["decision.json"])
    reviewed_time(decision.reviewed_at)
    synthetic = manifest.dataset_type == "SYNTHETIC"
    current = AdjudicationDecision.model_validate(
        store.read_json(requests(root, decision.decision_ref))
    )
    if current != decision or not decision.approve_final or decision.human_verified == synthetic:
        raise IngestionBlocked("Adjudication human evidence or provenance no longer valid")
    if (
        summary["dataset_type"],
        summary["taxonomy_checksum"],
        summary["pilot_checksum"],
        summary["submission_checksums"],
        summary["agreement_version"],
    ) != (manifest.dataset_type, CHECKSUM, checksum, report["submission_checksums"], version):
        raise IngestionError("Adjudicated manifest provenance mismatch")
    if (
        decision.pilot_id,
        decision.pilot_checksum,
        decision.submission_checksums,
        decision.adjudicator_id,
    ) != (
        pilot_id,
        checksum,
        report["submission_checksums"],
        manifest.plan.adjudicator.annotator_id,
    ):
        raise IngestionError("Adjudicator or independent submission binding mismatch")
    finals = decision.final_records
    ids = [item.feedback_id for item in finals]
    expected = [
        item.model_dump(mode="json") for item in finals if item.annotation_status == "SUBMITTED"
    ]
    if (
        len(ids) != len(set(ids))
        or set(ids) != set(manifest.selected_ids)
        or docs["resolved_records.json"] != expected
    ):
        raise IngestionError("Adjudicated record membership or decision mismatch")
    for item in finals:
        if item.annotator_id != decision.adjudicator_id or any(
            getattr(item, field) != getattr(manifest, field)
            for field in (
                "dataset_type",
                "dataset_version",
                "source_id",
                "taxonomy_version",
                "taxonomy_checksum",
            )
        ):
            raise IngestionBlocked("Final annotation identity or provenance mismatch")
    unresolved = sum(item.annotation_status == "REQUIRES_REVIEW" for item in finals)
    if (
        summary["unresolved_count"],
        summary["excluded_count"],
        summary["gold_count"],
        summary["synthetic_resolved_count"],
        summary["human_gold"],
    ) != (
        unresolved,
        len(finals) - len(expected) - unresolved,
        0 if synthetic else len(expected),
        len(expected) if synthetic else 0,
        not synthetic and bool(expected),
    ):
        raise IngestionError("Gold manifest counts or human approval claims inconsistent")
    if synthetic and (summary["human_gold"] or summary["gold_count"]):
        raise IngestionBlocked("Synthetic research-gold promotion rejected")
    return {
        "status": "VERIFIED_SYNTHETIC" if manifest.dataset_type == "SYNTHETIC" else "VERIFIED",
        "human_gold": summary["human_gold"],
        "dataset_type": manifest.dataset_type,
        "research_pilot_complete": not synthetic and len(ids) == 200 and unresolved == 0,
    }
