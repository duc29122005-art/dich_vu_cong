"""Frozen corpus construction. Real builds require existing evidence, never CLI approval."""

import json
import re
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal

from pydantic import Field, model_validator

from pfa.annotation import approval, pilot
from pfa.annotation import pilot_store as store
from pfa.annotation.agreement import TASKS
from pfa.annotation.schema import Annotation, DatasetVersion, FeedbackID
from pfa.annotation.taxonomy import CHECKSUM, VERSION
from pfa.data import official
from pfa.data.official_io import (
    IngestionBlocked,
    IngestionError,
    protect_directory,
    safe_path,
    write_json,
)
from pfa.data.permissions import current_decision, require_access
from pfa.data.preprocessing import normalize_text
from pfa.data.privacy import audit_screen
from pfa.data.registry import Identifier, Metadata, Registry
from pfa.data.splitting import (
    ALGORITHM,
    SPLITS,
    CorpusRow,
    SplitConfig,
    group_rows,
    leakage,
    split_rows,
)

CORPUS_VERSION = "corpus-1"


class FrozenManifest(Metadata):
    schema_version: Literal["corpus-1"]
    dataset_version: Identifier
    dataset_type: Literal["SYNTHETIC", "RESEARCH"]
    taxonomy_version: Literal[VERSION]
    taxonomy_checksum: Literal[CHECKSUM]
    label_mapping: dict[str, list[str]]
    config: SplitConfig
    config_checksum: str
    seed: int = Field(ge=0, lt=2**32)
    built_at: str
    construction_checksum: str
    provenance: dict
    dataset_approval: dict | None
    report: dict
    membership: dict[str, list[FeedbackID]]
    test_membership_checksum: str

    @model_validator(mode="after")
    def complete(self) -> "FrozenManifest":
        approval.reviewed_time(self.built_at)
        if set(self.membership) != set(SPLITS):
            raise ValueError("All frozen split memberships required")
        if self.dataset_type != self.provenance.get("dataset_type"):
            raise ValueError("Frozen provenance mismatch")
        if self.label_mapping != {task: list(labels) for task, labels in TASKS.items()}:
            raise ValueError("Frozen label mappings differ from taxonomy")
        return self


class BuildPlan(Metadata):
    version: Identifier
    source_id: Identifier
    dataset_version: DatasetVersion
    research_pilot: Identifier
    gold_pilots: list[Identifier] = Field(min_length=1)
    config_checksum: str
    seed: int = Field(ge=0, lt=2**32)
    relations: dict[FeedbackID, list[str]]
    pilot_holdout_approved_ids: list[FeedbackID]
    unknown_severity_approved_ids: list[FeedbackID]
    reviewer_id: Identifier
    evidence_reference: Identifier
    reviewed_at: str
    human_verified: Literal[True]

    @model_validator(mode="after")
    def reviewed(self) -> "BuildPlan":
        approval.reviewed_time(self.reviewed_at)
        if len(set(self.gold_pilots)) != len(self.gold_pilots):
            raise ValueError("Repeated gold annotation batches")
        if self.reviewer_id in {"unknown", "pending"} or self.evidence_reference in {
            "unknown",
            "pending",
        }:
            raise ValueError("Human dataset plan evidence required")
        for values in self.relations.values():
            if any(
                not re.fullmatch(r"(?:case|thread|source|near):[a-f0-9]{64}", value)
                for value in values
            ):
                raise ValueError("Only keyed non-identifying reviewed group relations allowed")
        return self


class DatasetApproval(Metadata):
    version: Identifier
    construction_checksum: str
    card_checksum: str
    reviewer_id: Identifier
    evidence_reference: Identifier
    reviewed_at: str
    human_verified: Literal[True]
    decision: Literal["APPROVED"]

    @model_validator(mode="after")
    def reviewed(self) -> "DatasetApproval":
        approval.reviewed_time(self.reviewed_at)
        if self.reviewer_id in {"unknown", "pending"} or self.evidence_reference in {
            "unknown",
            "pending",
        }:
            raise ValueError("Actual dataset and card approval evidence required")
        return self


def directory(root: Path, version: str) -> Path:
    return safe_path(root / "data/processed" / store.identifier(version), root)


def request(root: Path, reference: str) -> object:
    return store.read_json(approval.requests(root, reference))


def gather(
    root: Path, registry: Registry, version: str, config: SplitConfig, seed: int, key: bytes
) -> tuple[list[CorpusRow], dict]:
    """All human/data gates precede source reads; no synthetic branch in this real entry."""
    taxonomy_checkpoint = approval.require_taxonomy(root)
    plan = BuildPlan.model_validate(request(root, "build_" + store.identifier(version)))
    if (
        plan.version != version
        or plan.seed != seed
        or plan.config_checksum != store.digest(config.model_dump())
    ):
        raise IngestionBlocked("Human plan does not match build configuration")
    decision = current_decision(root, registry, plan.source_id)
    rights = official.authorize(
        root, registry, plan.source_id, decision.approval_ref if decision else "", commit=True
    )
    require_access(root, registry, plan.source_id, "training")
    try:
        research = pilot.verify_pilot(root, registry, plan.research_pilot)
    except IngestionError:
        raise IngestionBlocked("BLOCKED_PILOT: verified real pilot artifacts required") from None
    if not research["research_pilot_complete"] or research["dataset_type"] != "RESEARCH":
        raise IngestionBlocked("BLOCKED_PILOT: verified real 200-record adjudicated pilot required")
    research_manifest, _ = pilot.load_pilot(root, registry, plan.research_pilot)
    if (research_manifest.source_id, research_manifest.dataset_version) != (
        plan.source_id,
        plan.dataset_version,
    ):
        raise IngestionBlocked("BLOCKED_PILOT: research source/version mismatch")
    source_manifest_path = root / "data/manifests" / plan.dataset_version / "manifest.json"
    source_manifest = official.OfficialManifest.model_validate(
        store.read_json(source_manifest_path)
    )
    official.verify(root, registry, plan.dataset_version)
    if source_manifest.source_id != plan.source_id or source_manifest.provenance != "REAL_EXTERNAL":
        raise IngestionBlocked("Synthetic or mismatched source cannot become research")
    annotations, groups, checksums, context = {}, {}, {}, {}
    for batch in plan.gold_pilots:
        pilot.verify_pilot(root, registry, batch)
        manifest, definition_checksum = pilot.load_pilot(root, registry, batch)
        if (manifest.dataset_type, manifest.source_id, manifest.dataset_version) != (
            "RESEARCH",
            plan.source_id,
            plan.dataset_version,
        ):
            raise IngestionBlocked("Gold batch source/taxonomy provenance mismatch")
        docs, checksum = store.bundle(pilot.location(root, batch) / "adjudicated")
        checksums[batch] = {
            "definition": definition_checksum,
            "adjudicated": checksum,
            "agreement": docs["manifest.json"]["agreement_version"],
        }
        batch_records = pilot._records(root, manifest)
        for value in docs["decision.json"]["final_records"]:
            item = Annotation.model_validate(value)
            if (item.dataset_type, item.dataset_version, item.source_id) != (
                "RESEARCH",
                plan.dataset_version,
                plan.source_id,
            ):
                raise IngestionBlocked(
                    "Gold record source/version or synthetic provenance mismatch"
                )
            if item.feedback_id in annotations:
                raise IngestionError(
                    "Gold batches repeat a record; select explicit annotation revisions"
                )
            annotations[item.feedback_id] = item
            groups[item.feedback_id] = manifest.duplicate_groups[item.feedback_id]
            context[item.feedback_id] = batch_records[item.feedback_id]
    if set(annotations) != set(context) or set(plan.relations) != set(annotations):
        raise IngestionBlocked("Complete reviewed grouping and gold membership required")
    if not set(plan.pilot_holdout_approved_ids) <= set(research_manifest.selected_ids) or not set(
        plan.unknown_severity_approved_ids
    ) <= set(annotations):
        raise IngestionError("Human task/holdout decisions refer to unknown records")
    if not set(research_manifest.selected_ids) <= set(annotations):
        raise IngestionBlocked("Full annotation corpus must account for the research pilot")
    if len(key) < 32:
        raise IngestionError("Protected fingerprint key required")

    def fp(value: str) -> str:
        return official.fingerprint(key, "corpus-lineage-1", value)

    rows, exclusions = [], Counter()
    for identifier, item in sorted(annotations.items()):
        source = context[identifier]
        if item.annotation_status in {"OUT_OF_SCOPE", "UNLABELABLE"}:
            exclusions[item.annotation_status] += 1
            continue
        unknown = item.severity_label == "unknown"
        if item.annotation_status == "REQUIRES_REVIEW" and not (
            unknown
            and identifier in plan.unknown_severity_approved_ids
            and item.topic_label
            and item.sentiment_label
        ):
            raise IngestionBlocked("Unresolved human annotation review prevents freezing")
        values = {
            task: getattr(item, task + "_label") for task in ("topic", "sentiment", "severity")
        }
        if unknown:
            values["severity"] = None
        if any(
            audit_screen(value).counts
            for name, value in source.model_dump().items()
            if isinstance(value, str) and name not in {"feedback_id", "source_id"}
        ):
            raise IngestionBlocked("Unresolved privacy risk prevents corpus construction")
        rows.append(
            CorpusRow(
                feedback_id=identifier,
                content=normalize_text(source.content),
                source_id=plan.source_id,
                source_version=plan.dataset_version,
                taxonomy_checksum=CHECKSUM,
                dataset_type="RESEARCH",
                event_time=source.created_at,
                group_id=groups[identifier],
                relations=plan.relations[identifier],
                labels=values,
                eligible={task: value is not None for task, value in values.items()},
                exclusion_reasons={
                    task: "UNKNOWN_SEVERITY_HUMAN_ACCEPTED" if value is None else None
                    for task, value in values.items()
                },
                holdout_eligible=identifier not in research_manifest.selected_ids
                or identifier in plan.pilot_holdout_approved_ids,
                domain_bucket=fp("domain:" + source.domain) if source.domain else None,
                agency_bucket=fp("agency:" + source.agency) if source.agency else None,
            )
        )
    return group_rows(rows, fp), {
        "dataset_type": "RESEARCH",
        "human_gold": True,
        "source_id": plan.source_id,
        "source_version": plan.dataset_version,
        "source_manifest_checksum": official.file_digest(source_manifest_path),
        "source_record_count": source_manifest.published_count,
        "annotated_count": len(annotations),
        "excluded_records": dict(exclusions),
        "unannotated_source_count": source_manifest.published_count - len(annotations),
        "taxonomy_approval": taxonomy_checkpoint,
        "gold_revisions": checksums,
        "permission": rights.model_dump(),
        "plan": plan.model_dump(),
    }


def _prepare(
    records: list[CorpusRow], provenance: dict, config: SplitConfig, seed: int
) -> tuple[dict, dict, str]:
    records = [CorpusRow.model_validate(row.model_dump()) for row in records]
    if len({row.feedback_id for row in records}) != len(records):
        raise IngestionError("Duplicate corpus record IDs")
    if any(
        row.taxonomy_checksum != CHECKSUM
        or row.dataset_type != provenance["dataset_type"]
        or row.source_id != provenance["source_id"]
        or row.source_version != provenance["source_version"]
        for row in records
    ):
        raise IngestionError("Corpus taxonomy or source-version mismatch")
    partitions, report = split_rows(records, config, seed)
    report["leakage"] = leakage(partitions, config)
    if report["leakage"]["critical_count"]:
        raise IngestionError("Critical leakage prevents dataset publication")
    report["task_exclusions"] = {
        task: dict(
            Counter(row.exclusion_reasons[task] for row in records if not row.eligible[task])
        )
        for task in ("topic", "sentiment", "severity")
    }
    report["missingness"] = {
        field: sum(getattr(row, field) is None for row in records)
        for field in ("event_time", "agency_bucket", "domain_bucket")
    }
    report["coverage"] = {
        field: dict(
            sorted(
                Counter(
                    getattr(row, field) for row in records if getattr(row, field) is not None
                ).items()
            )
        )
        for field in ("agency_bucket", "domain_bucket")
    }
    report["record_count"] = len(records)
    known_dates = [
        row.event_time.astimezone(UTC)
        for row in records
        if row.event_time and row.event_time.tzinfo
    ]
    report["event_time_range"] = {
        "minimum": min(known_dates).isoformat() if known_dates else None,
        "maximum": max(known_dates).isoformat() if known_dates else None,
    }
    report["source_record_count"] = provenance["source_record_count"]
    report["annotated_count"] = provenance["annotated_count"]
    report["excluded_records"] = provenance["excluded_records"]
    report["unannotated_source_count"] = provenance["unannotated_source_count"]
    if provenance.get("unannotated_source_count"):
        report["warnings"].append("SOURCE_RECORDS_NOT_YET_ANNOTATED")
    if not 2000 <= len(records) <= 5000:
        report["warnings"].append("OUTSIDE_TARGET_CORPUS_SIZE")
    construction = store.digest(
        {
            "rows": {
                split: [row.model_dump(mode="json") for row in partitions[split]]
                for split in SPLITS
            },
            "provenance": provenance,
            "config": config.model_dump(),
            "seed": seed,
            "version": CORPUS_VERSION,
        }
    )
    return partitions, report, construction


def dataset_card(version: str, provenance: dict, report: dict, construction: str) -> str:
    """Aggregate card only; source text and human identifiers never enter this document."""
    synthetic = provenance["dataset_type"] == "SYNTHETIC"
    sections = {
        "Dataset name and version": version,
        "Research objective": "Vietnamese public-service topic, sentiment and severity research",
        "Source and provenance": {
            "source_id": provenance["source_id"],
            "source_version": provenance["source_version"],
        },
        "Permission and usage scope": "SOFTWARE_TEST_ONLY"
        if synthetic
        else "Source-authorized training/internal analysis; external release separately governed",
        "Construction methodology": {"algorithm": ALGORITHM, "construction_checksum": construction},
        "Annotation methodology": "PREDETERMINED SYNTHETIC LABELS; NO HUMAN GOLD"
        if synthetic
        else (
            "Independent annotations and explicit human adjudication; "
            "private evidence-bound revisions"
        ),
        "Taxonomy version": {"version": VERSION, "checksum": CHECKSUM},
        "Agreement reference": "SOFTWARE_TEST_ONLY"
        if synthetic
        else {name: value["agreement"] for name, value in provenance["gold_revisions"].items()},
        "Number of records": {
            name: report[name]
            for name in (
                "record_count",
                "source_record_count",
                "annotated_count",
                "excluded_records",
                "unannotated_source_count",
            )
        },
        "Class distribution for each task": report["class_distributions"],
        "Train validation test sizes": {"counts": report["counts"], "ratios": report["ratios"]},
        "Time agency domain coverage": {
            "metadata": report["coverage"],
            "event_time_known": report["leakage"]["timestamp_known"],
            "event_time_range": report["event_time_range"],
        },
        "Missingness": report["missingness"],
        "Duplicates and leakage": report["leakage"],
        "Privacy limitations": (
            "Human clearance required; regex does not guarantee anonymity; "
            "no raw identifiers in reports"
        ),
        "Sampling bias and representativeness": (
            "Source selection, missing metadata and annotation coverage limit representativeness"
        ),
        "Known limitations": {
            "warnings": report["warnings"],
            "task_exclusions": report["task_exclusions"],
        },
        "Permitted and prohibited uses": "Synthetic: software tests only"
        if synthetic
        else (
            "Use only within recorded source scope; no re-identification "
            "or test-driven model selection"
        ),
        "Reproducibility metadata": {
            "construction_checksum": construction,
            "seed": report["seed"],
            "processing_version": CORPUS_VERSION,
        },
    }
    prefix = "# SYNTHETIC SOFTWARE DATASET CARD\n" if synthetic else "# Research dataset card\n"
    return prefix + "\n".join(
        "\n## "
        + name
        + "\n\n"
        + json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2)
        + "\n"
        for name, value in sections.items()
    )


def _publish(
    root: Path,
    version: str,
    records: list[CorpusRow],
    provenance: dict,
    config: SplitConfig,
    seed: int,
    final_approval: dict | None = None,
    recheck: Callable[[], None] | None = None,
) -> dict:
    """Private build primitive. Synthetic capability or human-bound evidence is mandatory."""
    if provenance["dataset_type"] == "SYNTHETIC":
        store.require_synthetic(root)
        if provenance.get("human_gold") or final_approval is not None:
            raise IngestionBlocked("Synthetic records cannot be promoted to research gold")
    elif final_approval is None or recheck is None:
        raise IngestionBlocked("Existing final human dataset approval required")
    partitions, report, construction = _prepare(records, provenance, config, seed)
    card = dataset_card(version, provenance, report, construction)
    import hashlib

    card_checksum = hashlib.sha256(card.encode("utf-8")).hexdigest()
    if final_approval is not None:
        human = DatasetApproval.model_validate(final_approval)
        if (human.version, human.construction_checksum, human.card_checksum) != (
            version,
            construction,
            card_checksum,
        ):
            raise IngestionBlocked(
                "Human dataset/card approval differs from the proposed frozen build"
            )
    target = directory(root, version)
    store.private_directory(target.parent)
    lock = target.parent / ("." + store.identifier(version) + ".lock")
    try:
        handle = lock.open("x")
    except FileExistsError:
        raise IngestionBlocked("Dataset build is locked; coordinator review required") from None
    try:
        with handle:
            if target.exists():
                raise IngestionError("Immutable dataset version exists; never overwrite")
            with TemporaryDirectory(prefix=".corpus-", dir=target.parent) as temporary:
                work = Path(temporary)
                protect_directory(work)
                import pyarrow as pa
                import pyarrow.parquet as pq

                for split, values in partitions.items():
                    table = pa.Table.from_pylist([row.model_dump(mode="json") for row in values])
                    pq.write_table(table, work / (split + ".parquet"))
                (work / "DATASET_CARD.md").write_text(card, encoding="utf-8", newline="\n")
                manifest = {
                    "schema_version": CORPUS_VERSION,
                    "dataset_version": version,
                    "dataset_type": provenance["dataset_type"],
                    "taxonomy_version": VERSION,
                    "taxonomy_checksum": CHECKSUM,
                    "label_mapping": {task: list(labels) for task, labels in TASKS.items()},
                    "config": config.model_dump(mode="json"),
                    "config_checksum": store.digest(config.model_dump()),
                    "seed": seed,
                    "built_at": datetime.now(UTC).isoformat(),
                    "construction_checksum": construction,
                    "provenance": provenance,
                    "dataset_approval": final_approval,
                    "report": report,
                    "membership": {
                        split: [row.feedback_id for row in values]
                        for split, values in partitions.items()
                    },
                    "test_membership_checksum": store.digest(
                        [row.feedback_id for row in partitions["test"]]
                    ),
                }
                write_json(work / "manifest.json", manifest)
                checksums = {
                    name: official.file_digest(work / name)
                    for name in (
                        "train.parquet",
                        "validation.parquet",
                        "test.parquet",
                        "manifest.json",
                        "DATASET_CARD.md",
                    )
                }
                write_json(work / "checksums.json", checksums)
                _verify_files(work)
                if recheck is not None:
                    recheck()
                work.rename(target)
        return {
            "status": "WARN" if report["warnings"] or report["leakage"]["warnings"] else "PASS",
            "dataset_type": provenance["dataset_type"],
            "human_gold": provenance["human_gold"],
            "version": version,
            "report": report,
        }
    finally:
        lock.unlink()


def build(
    root: Path,
    registry: Registry,
    version: str,
    seed: int = 42,
    config: SplitConfig | None = None,
    key: bytes = b"",
    preview: bool = False,
) -> dict:
    config = config or SplitConfig()
    records, provenance = gather(root, registry, version, config, seed, key)
    partitions, report, checksum = _prepare(records, provenance, config, seed)
    card = dataset_card(version, provenance, report, checksum)
    import hashlib

    if preview:
        # Preview contains safe aggregate card and hashes, never source text or labels by ID.
        return {
            "status": "WARN",
            "construction_checksum": checksum,
            "card_checksum": hashlib.sha256(card.encode()).hexdigest(),
            "card": card,
            "report": report,
            "published": False,
        }
    try:
        human = DatasetApproval.model_validate(request(root, "dataset_" + version)).model_dump()
    except IngestionError:
        raise IngestionBlocked(
            "BLOCKED_PERMISSION: existing human dataset and card approval required"
        ) from None

    def recheck() -> None:
        current, evidence = gather(root, registry, version, config, seed, key)
        if (
            _prepare(current, evidence, config, seed)[2] != checksum
            or request(root, "dataset_" + version) != human
        ):
            raise IngestionBlocked("Build evidence changed during publication")

    return _publish(root, version, records, provenance, config, seed, human, recheck)


def _verify_files(path: Path) -> dict:
    checksums = store.read_json(path / "checksums.json", 65536)
    expected = {
        "manifest.json",
        "train.parquet",
        "validation.parquet",
        "test.parquet",
        "DATASET_CARD.md",
    }
    if (
        not isinstance(checksums, dict)
        or set(checksums) != expected
        or {item.name for item in path.iterdir()} != expected | {"checksums.json"}
    ):
        raise IngestionError("Frozen dataset file inventory mismatch")
    for name, checksum in checksums.items():
        file = safe_path(path / name, path)
        if not file.is_file() or official.file_digest(file) != checksum:
            raise IngestionError("Frozen dataset checksum mismatch")
    manifest = FrozenManifest.model_validate(store.read_json(path / "manifest.json")).model_dump(
        mode="json"
    )
    if (
        manifest.get("schema_version") != CORPUS_VERSION
        or manifest.get("taxonomy_checksum") != CHECKSUM
        or manifest.get("taxonomy_version") != VERSION
    ):
        raise IngestionError("Frozen dataset schema/taxonomy mismatch")
    config = SplitConfig.model_validate(manifest["config"])
    if manifest["config_checksum"] != store.digest(config.model_dump()):
        raise IngestionError("Frozen build configuration checksum mismatch")
    if manifest["test_membership_checksum"] != store.digest(manifest["membership"]["test"]):
        raise IngestionError("Frozen test membership checksum mismatch")
    human = manifest["dataset_approval"]
    if human is not None and human.get("card_checksum") != checksums["DATASET_CARD.md"]:
        raise IngestionError("Dataset card differs from human approval")
    return manifest


def _authorized_manifest(root: Path, registry: Registry, version: str) -> tuple[Path, dict]:
    path = directory(root, version)
    if not path.is_dir():
        raise IngestionError("NOT_AVAILABLE: frozen dataset is missing")
    # Control metadata only; no Parquet/data reads until current governance is revalidated.
    manifest = FrozenManifest.model_validate(store.read_json(path / "manifest.json")).model_dump(
        mode="json"
    )
    if manifest.get("dataset_type") == "SYNTHETIC":
        store.require_synthetic(root)
    elif manifest.get("dataset_type") == "RESEARCH":
        approval.require_taxonomy(root)
        provenance = manifest["provenance"]
        plan = BuildPlan.model_validate(provenance.get("plan"))
        if plan.version != version or request(root, "build_" + version) != plan.model_dump():
            raise IngestionBlocked("Frozen plan evidence changed")
        rights = official.authorize(
            root, registry, plan.source_id, provenance["permission"]["approval_ref"], commit=True
        )
        require_access(root, registry, plan.source_id, "training")
        if rights.model_dump() != provenance["permission"]:
            raise IngestionBlocked("Frozen permission evidence changed")
        if approval.require_taxonomy(root) != provenance["taxonomy_approval"]:
            raise IngestionBlocked("Frozen taxonomy approval no longer current")
        if not pilot.verify_pilot(root, registry, plan.research_pilot)["research_pilot_complete"]:
            raise IngestionBlocked("BLOCKED_PILOT: real research pilot is incomplete")
        official.verify(root, registry, plan.dataset_version)
        if (
            official.file_digest(root / "data/manifests" / plan.dataset_version / "manifest.json")
            != provenance["source_manifest_checksum"]
        ):
            raise IngestionBlocked("Frozen source manifest changed")
        for batch, binding in provenance["gold_revisions"].items():
            pilot.verify_pilot(root, registry, batch)
            if (
                store.bundle(pilot.location(root, batch) / "adjudicated")[1]
                != binding["adjudicated"]
            ):
                raise IngestionBlocked("Frozen gold evidence changed")
        human = DatasetApproval.model_validate(request(root, "dataset_" + version))
        if (
            human.model_dump() != manifest["dataset_approval"]
            or human.construction_checksum != manifest["construction_checksum"]
        ):
            raise IngestionBlocked("Frozen dataset approval changed")
    else:
        raise IngestionBlocked("Invalid dataset provenance")
    verified = _verify_files(path)
    if verified != manifest or manifest["dataset_version"] != version:
        raise IngestionError("Frozen dataset identity changed")
    return path, manifest


def _read_partition(path: Path) -> list[CorpusRow]:
    import pyarrow.parquet as pq

    try:
        if pq.read_metadata(path).num_rows > 5000:
            raise IngestionError("Frozen partition exceeds corpus size limit")
        return [CorpusRow.model_validate(value) for value in pq.read_table(path).to_pylist()]
    except (OSError, ValueError):
        raise IngestionError("Invalid frozen Parquet partition") from None


def verify(root: Path, registry: Registry, version: str) -> dict:
    path, manifest = _authorized_manifest(root, registry, version)
    partitions = {split: _read_partition(path / (split + ".parquet")) for split in SPLITS}
    config = SplitConfig.model_validate(manifest["config"])
    report = leakage(partitions, config)
    if report["critical_count"]:
        raise IngestionError("Critical frozen dataset leakage detected")
    for split, records in partitions.items():
        if [row.feedback_id for row in records] != manifest["membership"][split]:
            raise IngestionError("Frozen split assignment differs from manifest")
    records = [row for split in SPLITS for row in partitions[split]]
    rebuilt, diagnostics, construction = _prepare(
        records, manifest["provenance"], config, manifest["seed"]
    )
    if construction != manifest["construction_checksum"] or diagnostics != manifest["report"]:
        raise IngestionError("Frozen construction or diagnostics differ from recomputation")
    if any(rebuilt[split] != partitions[split] for split in SPLITS):
        raise IngestionError("Frozen split assignment is inconsistent")
    return {
        "status": report["status"],
        "dataset_type": manifest["dataset_type"],
        "leakage": report,
        "counts": manifest["report"]["counts"],
    }


def model_selection(
    root: Path, registry: Registry, version: str, partition: str
) -> list[CorpusRow]:
    """The sole development reader; rejects test before opening any dataset artifact."""
    if partition not in {"train", "validation"}:
        raise IngestionBlocked("Final test access requires the separate evaluation protocol")
    path, manifest = _authorized_manifest(root, registry, version)
    records = _read_partition(path / (partition + ".parquet"))
    if [row.feedback_id for row in records] != manifest["membership"][partition]:
        raise IngestionError("Development partition membership mismatch")
    return records


def evaluation_data(
    root: Path, registry: Registry, version: str, evaluation_ref: str
) -> list[CorpusRow]:
    path, manifest = _authorized_manifest(root, registry, version)
    if manifest["dataset_type"] != "RESEARCH":
        raise IngestionBlocked("Synthetic fixtures cannot authorize real final evaluation")
    evidence = request(root, evaluation_ref)
    required = {
        "version",
        "test_checksum",
        "reviewer_id",
        "reviewed_at",
        "expires_at",
        "purpose",
        "human_verified",
        "evidence_reference",
    }
    if not isinstance(evidence, dict) or set(evidence) != required:
        raise IngestionBlocked("Existing human final evaluation protocol required")
    approval.reviewed_time(evidence["reviewed_at"])
    expiry = datetime.fromisoformat(evidence["expires_at"])
    if (
        evidence["version"] != version
        or evidence["purpose"] != "FINAL_EVALUATION"
        or evidence["human_verified"] is not True
        or expiry.tzinfo is None
        or expiry <= datetime.now(UTC)
        or evidence["reviewer_id"] in {"unknown", "pending"}
        or evidence["evidence_reference"] in {"unknown", "pending"}
        or evidence["test_checksum"] != store.read_json(path / "checksums.json")["test.parquet"]
    ):
        raise IngestionBlocked("Final evaluation authorization is invalid or expired")
    audit = root / "data/private/evaluation_access" / store.identifier(evaluation_ref)
    store.publish(audit, {"decision.json": evidence})
    return _read_partition(path / "test.parquet")
