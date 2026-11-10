"""Permission-first citizen feedback ingestion. No network or raw-data copies."""

import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import stat
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import BinaryIO, Literal

from pydantic import Field, model_validator

from pfa.data.official_io import (
    IngestionBlocked,
    IngestionError,
    protect_directory,
    rows,
    safe_path,
    write_json,
)
from pfa.data.official_schema import Feedback, ImportOptions
from pfa.data.permissions import Decision, current_decision, require_access
from pfa.data.privacy import screen
from pfa.data.registry import Identifier, Metadata, Registry, Text

PROCESSING_VERSION = "official-1"
VERSION_PATTERN = r"of_[a-f0-9]{32}"
SYNTHETIC_FIXTURE_SHA256 = "ec1dd7a5a85eba6322eae86c400c4a6f6858ebeea84d3a83e075133eca762f1b"


def fingerprint(key: bytes, namespace: str, value: str) -> str:
    """Domain-separated keyed hashes; never persist raw identifiers or token maps."""
    return hmac.new(key, (namespace + "\0" + value).encode("utf-8"), hashlib.sha256).hexdigest()


def file_digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def source_digest(stream: BinaryIO, key: bytes, limit: int) -> str:
    digest = hmac.new(key, b"source-file\0", hashlib.sha256)
    size = 0
    stream.seek(0)
    while chunk := stream.read(65536):
        size += len(chunk)
        if size > limit:
            raise IngestionError("Input exceeds configured maximum size")
        digest.update(chunk)
    stream.seek(0)
    return digest.hexdigest()


def authorize(
    root: Path, registry: Registry, source_id: str, reference: str, commit: bool = False
) -> Decision:
    """Validate identity, current audit snapshot, rights, scope, expiry and retention."""
    try:
        source = registry.source(source_id)
        require_access(root, registry, source_id, "internal_analysis")
        if commit:
            require_access(root, registry, source_id, "publication")
        decision = current_decision(root, registry, source_id)
        if (
            source.dataset_role != "PRIMARY_CANDIDATE"
            or source.permission_status != "APPROVED"
            or source.license_status != "VERIFIED"
            or decision is None
            or decision.approval_ref != reference
            or decision.expires_on is None
            or date.fromisoformat(decision.expires_on) < date.today()
        ):
            raise ValueError
    except (ValueError, OSError):
        raise IngestionBlocked(
            "BLOCKED_PERMISSION: verified primary source, current matching approval, "
            "internal_analysis scope, explicit expiry and retention required; "
            "commit also requires publication scope. Review evidence and audit consistency."
        ) from None
    return decision


class ReviewItem(Metadata):
    feedback_id: Text
    action: Literal["APPROVE", "REJECT"]
    privacy_cleared: bool

    @model_validator(mode="after")
    def cleared(self) -> "ReviewItem":
        if not re.fullmatch(r"f_[a-f0-9]{32}", self.feedback_id):
            raise ValueError("Review requires generated candidate IDs")
        if self.action == "APPROVE" and not self.privacy_cleared:
            raise ValueError("Accepted records require explicit human privacy clearance")
        return self


class PrivacyReview(Metadata):
    dataset_version: Text
    source_id: Identifier
    source_checksum: Text
    candidates_checksum: Text
    queue_checksum: Text
    permission_reference: Identifier | None
    reviewer: Identifier
    evidence_reference: Identifier
    reviewed_at: Text
    provenance: Literal["REAL_EXTERNAL", "SYNTHETIC"]
    quality_accepted: bool
    decisions: list[ReviewItem]

    @model_validator(mode="after")
    def human_metadata(self) -> "PrivacyReview":
        when = datetime.fromisoformat(self.reviewed_at)
        if when.tzinfo is None or when > datetime.now(UTC) or not self.quality_accepted:
            raise ValueError("Review requires valid date and acknowledged quality report")
        if self.reviewer in {"unknown", "pending"} or self.evidence_reference in {
            "unknown",
            "pending",
        }:
            raise ValueError("Existing human reviewer and protected evidence reference required")
        ids = [item.feedback_id for item in self.decisions]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate review decisions")
        return self


class OfficialManifest(Metadata):
    dataset_version: Text
    source_id: Identifier
    provenance: Literal["REAL_EXTERNAL", "SYNTHETIC"]
    source_checksum: Text
    source_checksum_algorithm: Literal["HMAC-SHA256"]
    output_checksum: Text
    quality_checksum: Text
    processing_version: Literal[PROCESSING_VERSION]
    permission_reference: Identifier | None
    review_reference: Identifier
    review_checksum: Text
    review_state: Literal["HUMAN_REVIEWED", "SIMULATED_SYNTHETIC"]
    published_count: int = Field(ge=0)
    storage_protection: Literal["WINDOWS_OWNER_SYSTEM_ACL", "POSIX_0700_0600"]
    built_at: Text
    options: ImportOptions

    @model_validator(mode="after")
    def provenance_valid(self) -> "OfficialManifest":
        if not re.fullmatch(VERSION_PATTERN, self.dataset_version):
            raise ValueError("Invalid immutable dataset version")
        for value in (
            self.source_checksum,
            self.output_checksum,
            self.quality_checksum,
            self.review_checksum,
        ):
            if not re.fullmatch(r"[a-f0-9]{64}", value):
                raise ValueError("Invalid manifest checksum")
        if self.provenance == "REAL_EXTERNAL":
            if self.permission_reference is None or self.review_state != "HUMAN_REVIEWED":
                raise ValueError("Real data requires human review and permission provenance")
        elif (
            self.source_id != "synthetic_fixture"
            or self.permission_reference is not None
            or self.review_state != "SIMULATED_SYNTHETIC"
        ):
            raise ValueError("Synthetic provenance must remain explicit")
        if datetime.fromisoformat(self.built_at).tzinfo is None:
            raise ValueError("Build timestamp must include a timezone")
        return self


def deduplicate(
    tokens: set[str], candidate_id: str, token_sets: dict, inverted: dict, threshold: float
) -> list[list[str]]:
    """Generate candidate pairs from keyed token overlap; never merge near matches."""
    pairs = []
    if len(tokens) >= 3:
        counts: Counter = Counter()
        for token in sorted(tokens):
            counts.update(inverted.get(token, ()))
        for previous, overlap in sorted(counts.items()):
            union = len(tokens) + len(token_sets[previous]) - overlap
            if overlap / union >= threshold:
                pairs.append([previous, candidate_id])
        token_sets[candidate_id] = tokens
        for token in sorted(tokens):
            inverted.setdefault(token, []).append(candidate_id)
    return pairs


def build_candidates(
    stream: BinaryIO,
    suffix: str,
    stage: Path,
    source_id: str,
    key: bytes,
    version: str,
    options: ImportOptions,
) -> dict:
    """Stream to protected sanitized candidates; retain only keyed dedup indexes."""
    seen_ids, seen_content, seen_records = set(), set(), set()
    # ponytail: keyed token index stays in memory; use a disk index for larger corpora.
    token_sets, inverted = {}, {}
    queue, errors, pairs, lengths, dates = [], [], [], [], []
    totals = Counter(
        input_records=0,
        valid_records=0,
        invalid_records=0,
        duplicate_count=0,
        privacy_flagged_count=0,
    )
    missing, detections, duplicate_reasons = Counter(), Counter(), Counter()
    with (stage / "candidates.jsonl").open("x", encoding="utf-8", newline="\n") as output:
        if os.name != "nt":
            (stage / "candidates.jsonl").chmod(0o600)
        for index, record in rows(stream, suffix, options):
            totals["input_records"] += 1
            if index > options.max_records:
                raise IngestionError("Input exceeds configured maximum record count")
            try:
                if record is None:
                    raise ValueError
                feedback = Feedback.model_validate(record)
                if feedback.source_id != source_id:
                    raise IngestionError("Input source identity does not match authorized source")
                values = feedback.model_dump(mode="json")
                raw_hash = fingerprint(key, "source-record", json.dumps(values, sort_keys=True))
                categories: Counter = Counter()
                ambiguous = False
                for field, value in values.items():
                    if isinstance(value, str) and field not in {
                        "feedback_id",
                        "source_id",
                        "created_at",
                        "response_date",
                    }:
                        result = screen(value, options.pii_categories, options.max_text_length)
                        values[field] = result.text
                        categories.update(result.counts)
                        ambiguous |= result.ambiguous
                Feedback.model_validate(values)
            except IngestionError:
                raise
            except (ValueError, UnicodeError):
                totals["invalid_records"] += 1
                errors.append({"row": index, "code": "INVALID_SCHEMA_OR_VALUE"})
                continue
            totals["valid_records"] += 1
            for field, value in values.items():
                if value is None:
                    missing[field] += 1
            if categories:
                totals["privacy_flagged_count"] += 1
            detections.update(categories)
            identity = fingerprint(key, "source-id", feedback.feedback_id)
            content = fingerprint(key, "sanitized-content", values["content"])
            reason = (
                "source_record"
                if raw_hash in seen_records
                else "feedback_id"
                if identity in seen_ids
                else "sanitized_content"
                if content in seen_content
                else None
            )
            seen_records.add(raw_hash)
            seen_ids.add(identity)
            seen_content.add(content)
            if reason is not None:
                totals["duplicate_count"] += 1
                duplicate_reasons[reason] += 1
                continue
            candidate_id = "f_" + fingerprint(key, version, feedback.feedback_id)[:32]
            values["feedback_id"] = candidate_id
            output.write(json.dumps(values, ensure_ascii=True, sort_keys=True) + "\n")
            tokens = {
                fingerprint(key, "token", word)
                for word in re.findall(r"\w+", values["content"].casefold())
            }
            pairs.extend(
                deduplicate(
                    tokens, candidate_id, token_sets, inverted, options.near_duplicate_threshold
                )
            )
            if len(pairs) > 10000:
                raise IngestionError("Near-duplicate review exceeds 10000 pairs; split the input")
            queue.append(
                {
                    "feedback_id": candidate_id,
                    "categories": dict(categories),
                    "ambiguous": ambiguous,
                    "state": "PENDING_HUMAN_REVIEW",
                }
            )
            lengths.append(len(values["content"]))
            if feedback.created_at is not None:
                dates.append(feedback.created_at.date().isoformat())
        output.flush()
        os.fsync(output.fileno())
    write_json(
        stage / "review_queue.json",
        {"records": queue, "near_duplicate_pairs": pairs, "invalid_rows": errors},
    )
    ordered = sorted(lengths)
    distribution = (
        None
        if not ordered
        else {
            "min": ordered[0],
            "max": ordered[-1],
            "mean": sum(ordered) / len(ordered),
            "p50": ordered[(len(ordered) - 1) // 2],
            "p95": ordered[int((len(ordered) - 1) * 0.95)],
        }
    )
    return {
        **dict(totals),
        "unique_record_count": len(queue),
        "exact_duplicate_count": totals["duplicate_count"],
        "suspected_duplicate_count": len(pairs),
        "duplicate_reasons": dict(duplicate_reasons),
        "pii_detections": dict(detections),
        "missing_values": dict(missing),
        "text_length_distribution": distribution,
        "date_coverage": {"min": min(dates), "max": max(dates)} if dates else None,
        "human_review_pending_count": len(queue),
        "published_count": 0,
    }


def load_review(
    root: Path, reference: str, stage: Path, report: dict, synthetic: bool
) -> PrivacyReview:
    if not re.fullmatch(r"[a-z][a-z0-9_]*", reference):
        raise IngestionBlocked("BLOCKED_REVIEW: valid protected review reference required")
    path = safe_path(root / "data/private/reviews" / f"{reference}.json", root / "data/private")
    if not path.is_file():
        raise IngestionBlocked(
            "BLOCKED_REVIEW: an existing human privacy-review record is required"
        )
    try:
        review = PrivacyReview.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except ValueError:
        raise IngestionBlocked("BLOCKED_REVIEW: invalid human decision metadata") from None
    if (
        review.dataset_version != report["dataset_version"]
        or review.source_id != report["source_id"]
        or review.source_checksum != report["source_checksum"]
        or review.permission_reference != report["permission_reference"]
        or review.provenance != report["provenance"]
        or review.candidates_checksum != file_digest(stage / "candidates.jsonl")
        or review.queue_checksum != file_digest(stage / "review_queue.json")
    ):
        raise IngestionBlocked("BLOCKED_REVIEW: review is not bound to this exact staged build")
    ids = {
        item["feedback_id"]
        for item in json.loads((stage / "review_queue.json").read_text())["records"]
    }
    if {item.feedback_id for item in review.decisions} != ids:
        raise IngestionBlocked("BLOCKED_REVIEW: every candidate requires an explicit decision")
    if not synthetic and review.reviewer.startswith("synthetic"):
        raise IngestionBlocked("BLOCKED_REVIEW: simulated review cannot authorize real data")
    return review


def remove_owned(path: Path, boundary: Path) -> None:
    """Cleanup only a checked application-owned temporary/publication directory."""
    checked = safe_path(path, boundary)
    if checked == boundary.resolve():
        raise IngestionError("Refusing storage-root removal")
    shutil.rmtree(checked)


def ingest(
    root: Path,
    registry: Registry,
    source_id: str,
    input_path: Path,
    approval_ref: str,
    key: bytes,
    mode: Literal["preview", "commit"] = "preview",
    options: ImportOptions | None = None,
    options_path: Path | None = None,
    review_ref: str | None = None,
) -> dict:
    """Real ingestion: permission validation always precedes input/config file reads."""
    authorize(root, registry, source_id, approval_ref, commit=mode == "commit")
    if options_path is not None:
        options = ImportOptions.model_validate(
            json.loads(safe_path(options_path).read_text(encoding="utf-8"))
        )
    return _ingest(
        root,
        registry,
        source_id,
        input_path,
        approval_ref,
        key,
        mode,
        options or ImportOptions(),
        review_ref,
        synthetic=False,
    )


def _ingest(
    root: Path,
    registry: Registry,
    source_id: str,
    input_path: Path,
    approval_ref: str | None,
    key: bytes,
    mode: str,
    options: ImportOptions,
    review_ref: str | None,
    *,
    synthetic: bool,
) -> dict:
    if mode not in {"preview", "commit"} or len(key) < 32:
        raise IngestionError("Valid mode and at least 32 bytes of secret fingerprint key required")
    if mode == "commit" and review_ref is None:
        raise IngestionBlocked(
            "BLOCKED_REVIEW: preview first, then provide a verified review reference"
        )
    boundary = root / "data/synthetic" if synthetic else root / "data/private"
    input_path = safe_path(input_path, boundary)
    if input_path.suffix.lower() not in {".csv", ".jsonl"}:
        raise IngestionError("Unsupported input format; CSV or JSONL required")
    if not stat.S_ISREG(input_path.stat().st_mode):
        raise IngestionError("Input must be a regular local file")
    storage = root / "data/synthetic" if synthetic else root / "data"
    staging = safe_path(storage / "staging", root)
    staging.mkdir(parents=True, exist_ok=True)
    with input_path.open("rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > options.max_input_bytes:
            raise IngestionError("Input must be a regular file within the configured size limit")
        original = source_digest(stream, key, options.max_input_bytes)
        version = (
            "of_"
            + fingerprint(
                key,
                "dataset-version",
                json.dumps(
                    [PROCESSING_VERSION, source_id, original, approval_ref, options.model_dump()],
                    sort_keys=True,
                ),
            )[:32]
        )
        stage = staging / version
        with TemporaryDirectory(prefix=".build-", dir=staging) as temporary:
            work = Path(temporary)
            protection = protect_directory(work)
            report = build_candidates(
                stream, input_path.suffix.lower(), work, source_id, key, version, options
            )
            if source_digest(stream, key, options.max_input_bytes) != original:
                raise IngestionError("Input changed during processing; no version published")
            report.update(
                dataset_version=version,
                source_id=source_id,
                source_checksum=original,
                source_checksum_algorithm="HMAC-SHA256",
                processing_version=PROCESSING_VERSION,
                permission_reference=approval_ref,
                provenance="SYNTHETIC" if synthetic else "REAL_EXTERNAL",
                metrics_usage="SOFTWARE_TEST_ONLY" if synthetic else "AWAITING_RESEARCH_REVIEW",
                storage_protection=protection,
                options=options.model_dump(),
            )
            report.update(
                output_checksum=file_digest(work / "candidates.jsonl"),
                output_kind="STAGED_CANDIDATES",
            )
            write_json(work / "quality_report.json", report)
            if not synthetic:
                authorize(root, registry, source_id, approval_ref, commit=mode == "commit")
            if mode == "preview":
                if stage.exists():
                    if any(
                        file_digest(stage / name) != file_digest(work / name)
                        for name in ("candidates.jsonl", "review_queue.json", "quality_report.json")
                    ):
                        raise IngestionError("Immutable staged version differs; refusing overwrite")
                else:
                    work.rename(stage)
                return {
                    "status": "PREVIEW",
                    **report,
                    "candidates_checksum": file_digest(stage / "candidates.jsonl"),
                    "queue_checksum": file_digest(stage / "review_queue.json"),
                }
            review = load_review(root, review_ref, work, report, synthetic)
            approved = {item.feedback_id for item in review.decisions if item.action == "APPROVE"}
            if not approved:
                raise IngestionBlocked("BLOCKED_REVIEW: no human-cleared records to publish")
            published = safe_path(storage / "processed" / version, root)
            catalog = safe_path(storage / "manifests" / version, root)
            if published.exists() or catalog.exists():
                raise IngestionError("Immutable published version exists; verify it instead")
            published.parent.mkdir(parents=True, exist_ok=True)
            catalog.parent.mkdir(parents=True, exist_ok=True)
            with TemporaryDirectory(prefix=".publish-", dir=published.parent) as publish_temp:
                bundle = Path(publish_temp)
                protect_directory(bundle)
                with (bundle / "feedback.jsonl").open(
                    "x", encoding="utf-8", newline="\n"
                ) as output:
                    if os.name != "nt":
                        (bundle / "feedback.jsonl").chmod(0o600)
                    with (work / "candidates.jsonl").open(encoding="utf-8") as candidates:
                        for line in candidates:
                            if json.loads(line)["feedback_id"] in approved:
                                output.write(line)
                    output.flush()
                    os.fsync(output.fileno())
                report.update(
                    human_review_pending_count=0,
                    published_count=len(approved),
                    human_review_rejected_count=len(review.decisions) - len(approved),
                    output_checksum=file_digest(bundle / "feedback.jsonl"),
                    output_kind="REVIEWED_DATASET",
                )
                with TemporaryDirectory(prefix=".manifest-", dir=catalog.parent) as catalog_temp:
                    metadata = Path(catalog_temp)
                    protect_directory(metadata)
                    write_json(metadata / "quality_report.json", report)
                    review_file = root / "data/private/reviews" / f"{review_ref}.json"
                    manifest = OfficialManifest(
                        dataset_version=version,
                        source_id=source_id,
                        provenance=report["provenance"],
                        source_checksum=original,
                        source_checksum_algorithm="HMAC-SHA256",
                        output_checksum=report["output_checksum"],
                        quality_checksum=file_digest(metadata / "quality_report.json"),
                        processing_version=PROCESSING_VERSION,
                        permission_reference=approval_ref,
                        review_reference=review_ref,
                        review_checksum=file_digest(review_file),
                        review_state="SIMULATED_SYNTHETIC" if synthetic else "HUMAN_REVIEWED",
                        published_count=len(approved),
                        storage_protection=protection,
                        built_at=datetime.now(UTC).isoformat(),
                        options=options,
                    )
                    write_json(metadata / "manifest.json", manifest.model_dump(mode="json"))
                    if not synthetic:
                        authorize(root, registry, source_id, approval_ref, commit=True)
                    bundle.rename(published)
                    try:
                        metadata.rename(catalog)  # Commit marker; readers require both locations.
                    except OSError:
                        remove_owned(published, published.parent)
                        raise
            return {"status": "COMMITTED_SYNTHETIC" if synthetic else "COMMITTED", **report}


def verify(root: Path, registry: Registry, version: str) -> dict:
    """Verify manifest, quality, schema, review binding and actual published count."""
    if not re.fullmatch(VERSION_PATTERN, version):
        raise IngestionError("Invalid dataset version identifier")
    roots = [root / "data", root / "data/synthetic"]
    available = [
        storage for storage in roots if safe_path(storage / "manifests" / version, root).is_dir()
    ]
    if len(available) != 1:
        raise IngestionError("NOT_AVAILABLE: no unambiguous published dataset version")
    storage = available[0]
    metadata = safe_path(storage / "manifests" / version, root)
    published = safe_path(storage / "processed" / version, root)
    manifest_path = safe_path(metadata / "manifest.json", root)
    report_path = safe_path(metadata / "quality_report.json", root)
    data_path = safe_path(published / "feedback.jsonl", root)
    try:
        manifest = OfficialManifest.model_validate(
            json.loads(manifest_path.read_text(encoding="utf-8"))
        )
    except (ValueError, OSError):
        raise IngestionError("Invalid or unavailable official manifest") from None
    synthetic = manifest.provenance == "SYNTHETIC"
    if manifest.dataset_version != version or synthetic != (storage == roots[1]):
        raise IngestionError("Manifest version/provenance does not match storage")
    if not synthetic:
        authorize(root, registry, manifest.source_id, manifest.permission_reference, commit=True)
    if (
        {item.name for item in metadata.iterdir()} != {"manifest.json", "quality_report.json"}
        or not published.is_dir()
        or {item.name for item in published.iterdir()} != {"feedback.jsonl"}
    ):
        raise IngestionError("Published file inventory mismatch")
    if (
        file_digest(data_path) != manifest.output_checksum
        or file_digest(report_path) != manifest.quality_checksum
    ):
        raise IngestionError("Published dataset or quality checksum mismatch")
    review_path = safe_path(
        root / "data/private/reviews" / f"{manifest.review_reference}.json", root
    )
    if not review_path.is_file() or file_digest(review_path) != manifest.review_checksum:
        raise IngestionError("Protected human-review evidence missing or changed")
    review = PrivacyReview.model_validate(json.loads(review_path.read_text(encoding="utf-8")))
    if (
        review.dataset_version != version
        or review.source_id != manifest.source_id
        or review.permission_reference != manifest.permission_reference
        or review.source_checksum != manifest.source_checksum
        or review.provenance != manifest.provenance
    ):
        raise IngestionError("Human review provenance mismatch")
    approved = {item.feedback_id for item in review.decisions if item.action == "APPROVE"}
    ids = set()
    try:
        with data_path.open(encoding="utf-8") as stream:
            for line in stream:
                record = Feedback.model_validate(json.loads(line))
                if (
                    record.source_id != manifest.source_id
                    or record.feedback_id in ids
                    or record.feedback_id not in approved
                ):
                    raise ValueError
                ids.add(record.feedback_id)
    except ValueError:
        raise IngestionError("Published canonical schema or review membership invalid") from None
    report = json.loads(report_path.read_text(encoding="utf-8"))
    try:
        consistent = (
            ids == approved
            and len(ids) == manifest.published_count == report["published_count"]
            and report["dataset_version"] == version
            and report["source_id"] == manifest.source_id
            and report["provenance"] == manifest.provenance
            and report["output_checksum"] == manifest.output_checksum
            and report["source_checksum"] == manifest.source_checksum
            and report["permission_reference"] == manifest.permission_reference
            and report["processing_version"] == PROCESSING_VERSION
            and report["options"] == manifest.options.model_dump()
            and report["human_review_pending_count"] == 0
            and report["input_records"] == report["valid_records"] + report["invalid_records"]
            and report["valid_records"] == report["unique_record_count"] + report["duplicate_count"]
            and report["published_count"] + report["human_review_rejected_count"]
            == report["unique_record_count"]
            and len(review.decisions) == report["unique_record_count"]
        )
    except (KeyError, TypeError):
        consistent = False
    if not consistent:
        raise IngestionError("Quality report is inconsistent with the verified dataset")
    return {
        "status": "VERIFIED_SYNTHETIC" if synthetic else "VERIFIED",
        "dataset_version": version,
        "provenance": manifest.provenance,
        "published_count": len(ids),
        "processing_version": PROCESSING_VERSION,
    }


def synthetic_fixture_bytes(fixture: Path | None = None) -> bytes:
    """Read only the checksum-bound project fixture, never an arbitrary synthetic label."""
    trusted = (
        Path(__file__).resolve().parents[3] / "tests/fixtures/public_service_feedback_synthetic.csv"
    )
    fixture = safe_path(trusted if fixture is None else fixture)
    if fixture != trusted or fixture.stat().st_size > 65536:
        raise IngestionError("Smoke accepts only the bundled project-generated synthetic fixture")
    payload = fixture.read_bytes().replace(b"\r\n", b"\n")
    if hashlib.sha256(payload).hexdigest() != SYNTHETIC_FIXTURE_SHA256:
        raise IngestionError("Bundled synthetic fixture differs from the trusted test definition")
    return payload


def smoke(fixture: Path, registry: Registry) -> dict:
    """Only the exact project fixture may enter this isolated synthetic workflow."""
    payload = synthetic_fixture_bytes(fixture)
    with TemporaryDirectory(prefix="pfa-synthetic-") as temporary:
        root = Path(temporary)
        protect_directory(root)
        inputs = root / "data/synthetic"
        inputs.mkdir(parents=True)
        protect_directory(inputs)
        input_file = inputs / "SYNTHETIC.csv"
        with input_file.open("xb") as stream:
            stream.write(payload)
        options = ImportOptions()
        key = secrets.token_bytes(32)
        preview = _ingest(
            root,
            registry,
            "synthetic_fixture",
            input_file,
            None,
            key,
            "preview",
            options,
            None,
            synthetic=True,
        )
        stage = inputs / "staging" / preview["dataset_version"]
        queue = json.loads((stage / "review_queue.json").read_text())
        reviews = root / "data/private/reviews"
        reviews.mkdir(parents=True)
        protect_directory(reviews)
        review = PrivacyReview(
            dataset_version=preview["dataset_version"],
            source_id="synthetic_fixture",
            source_checksum=preview["source_checksum"],
            candidates_checksum=preview["candidates_checksum"],
            queue_checksum=preview["queue_checksum"],
            permission_reference=None,
            reviewer="synthetic_smoke_simulation",
            evidence_reference="synthetic_test_only",
            reviewed_at=datetime.now(UTC).isoformat(),
            provenance="SYNTHETIC",
            quality_accepted=True,
            decisions=[
                ReviewItem(
                    feedback_id=item["feedback_id"],
                    action="REJECT" if item["ambiguous"] else "APPROVE",
                    privacy_cleared=not item["ambiguous"],
                )
                for item in queue["records"]
            ],
        )
        write_json(reviews / "synthetic_smoke.json", review.model_dump(mode="json"))
        result = _ingest(
            root,
            registry,
            "synthetic_fixture",
            input_file,
            None,
            key,
            "commit",
            options,
            "synthetic_smoke",
            synthetic=True,
        )
        verified = verify(root, registry, result["dataset_version"])
        return {
            "status": "SMOKE_PASS_SYNTHETIC",
            "isolated_temporary_storage": True,
            "review_state": "SIMULATED_SYNTHETIC",
            "quality_report": result,
            "verification": verified,
        }
