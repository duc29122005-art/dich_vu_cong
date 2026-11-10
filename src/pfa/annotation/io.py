"""Offline template generation and validation; no label assignment or annotation export."""

import csv
import hashlib
import io
import json
import os
from collections import Counter
from collections.abc import Iterator
from pathlib import Path
from tempfile import TemporaryDirectory

from pydantic import ValidationError

from pfa.annotation.schema import VALIDATION_RULES, Annotation, AnnotationMetadata, BlankAnnotation
from pfa.annotation.taxonomy import CHECKSUM, VERSION, load_taxonomy, unique_object
from pfa.data import official
from pfa.data.official_io import (
    BoundedReader,
    IngestionError,
    protect_directory,
    rows,
    safe_path,
    write_json,
)
from pfa.data.official_schema import Feedback, ImportOptions
from pfa.data.permissions import current_decision
from pfa.data.privacy import audit_screen
from pfa.data.profiling import SYNTHETIC_KEY
from pfa.data.registry import Registry

COLUMNS = list(BlankAnnotation.model_fields)
MAX_BYTES = 20 * 1024**2
MAX_RECORDS = 10000


def metadata_path(path: Path) -> Path:
    return path.with_name(path.name + ".metadata.json")


def template(root: Path, output: Path) -> dict:
    """Write an empty header plus metadata without fake rows or silent overwrite."""
    load_taxonomy(root)
    output = safe_path(output if output.is_absolute() else root / output, root)
    if output.suffix.lower() not in {".csv", ".jsonl"}:
        raise IngestionError("Annotation templates support CSV or JSONL only")
    sidecar = safe_path(metadata_path(output), root)
    if output.exists() or sidecar.exists():
        raise IngestionError("Annotation output already exists; choose a new path")
    output.parent.mkdir(parents=True, exist_ok=True)
    metadata = AnnotationMetadata(
        format_version="annotation-1",
        purpose="BLANK_TEMPLATE",
        taxonomy_version=VERSION,
        taxonomy_checksum=CHECKSUM,
        dataset_type="TEMPLATE",
        source_id=None,
        dataset_version=None,
        columns=COLUMNS,
        human_gold=False,
    )
    with TemporaryDirectory(prefix=".annotation-", dir=output.parent) as temporary:
        work = Path(temporary)
        protect_directory(work)
        staged = work / "template"
        with staged.open("x", encoding="utf-8", newline="") as stream:
            if os.name != "nt":
                staged.chmod(0o600)
            if output.suffix.lower() == ".csv":
                csv.writer(stream).writerow(COLUMNS)
            stream.flush()
            os.fsync(stream.fileno())
        write_json(work / "metadata", metadata.model_dump(mode="json"))
        # Exclusive hard links preserve file ACLs; sidecar is the pair's commit marker.
        os.link(staged, output)
        try:
            os.link(work / "metadata", sidecar)
        except OSError:
            if output.samefile(staged):
                output.unlink()
            raise
    return {
        "status": "TEMPLATE_CREATED",
        "record_count": 0,
        "dataset_type": "TEMPLATE",
        "taxonomy_version": VERSION,
        "taxonomy_checksum": CHECKSUM,
        "metadata_required": True,
        "human_gold": False,
    }


def synthetic_inventory() -> tuple[str, set[str]]:
    """Checksum-bound project fixture IDs only; no synthetic-to-real promotion."""
    payload = official.synthetic_fixture_bytes()
    version = (
        "of_"
        + official.fingerprint(
            SYNTHETIC_KEY, "annotation-software-fixture", hashlib.sha256(payload).hexdigest()
        )[:32]
    )
    ids = set()
    with io.BytesIO(payload) as stream:
        for _, row in rows(stream, ".csv", ImportOptions()):
            try:
                item = Feedback.model_validate(row)
            except ValueError:
                continue
            if any(
                audit_screen(value).counts
                for name, value in item.model_dump().items()
                if isinstance(value, str) and name not in {"feedback_id", "source_id"}
            ):
                continue
            ids.add("f_" + official.fingerprint(SYNTHETIC_KEY, version, item.feedback_id)[:32])
    return version, ids


def inventory(
    root: Path, registry: Registry, metadata: AnnotationMetadata
) -> tuple[set[str], str | None]:
    """Permission and review-bound provenance precede all real annotation/data reads."""
    if metadata.dataset_type == "TEMPLATE":
        return set(), None
    if metadata.dataset_type == "SYNTHETIC":
        version, ids = synthetic_inventory()
        if metadata.source_id != "synthetic_demo" or metadata.dataset_version != version:
            raise IngestionError("Synthetic submission must reference the bundled software fixture")
        return ids, official.SYNTHETIC_FIXTURE_SHA256
    decision = current_decision(root, registry, metadata.source_id)
    official.authorize(
        root, registry, metadata.source_id, decision.approval_ref if decision else ""
    )
    path = safe_path(root / "data/manifests" / metadata.dataset_version / "manifest.json", root)
    if not path.is_file():
        raise IngestionError("Verified research manifest is required for annotation membership")
    payload = path.read_bytes()
    manifest_checksum = hashlib.sha256(payload).hexdigest()
    manifest = official.OfficialManifest.model_validate_json(payload)
    if manifest.source_id != metadata.source_id or manifest.provenance != "REAL_EXTERNAL":
        raise IngestionError("Annotation source does not match verified research provenance")
    official.verify(root, registry, metadata.dataset_version)
    data = safe_path(root / "data/processed" / metadata.dataset_version / "feedback.jsonl", root)
    ids = set()
    with data.open("rb") as stream:
        for ordinal, row in rows(stream, ".jsonl", ImportOptions()):
            if ordinal > MAX_RECORDS or row is None:
                raise IngestionError("Verified dataset exceeds annotation contract limits")
            ids.add(Feedback.model_validate(row).feedback_id)
    if official.file_digest(path) != manifest_checksum:
        raise IngestionError("Research manifest changed during membership validation")
    return ids, manifest_checksum


def annotation_rows(path: Path) -> Iterator[tuple[int, dict | None]]:
    """Bounded UTF-8 input; never echo malformed human content or unexpected columns."""
    if path.suffix.lower() not in {".csv", ".jsonl"}:
        raise IngestionError("Annotation input must be CSV or JSONL")
    if not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise IngestionError("Annotation input unavailable or exceeds size limit")
    with path.open("rb") as raw:
        text = io.TextIOWrapper(
            io.BufferedReader(BoundedReader(raw, MAX_BYTES)),
            encoding="utf-8-sig",
            errors="strict",
            newline="",
        )
        try:
            if path.suffix.lower() == ".csv":
                reader = csv.DictReader(text, strict=True)
                columns = reader.fieldnames or []
                if len(columns) != len(COLUMNS) or set(columns) != set(COLUMNS):
                    raise IngestionError("Annotation CSV columns missing, duplicated or unexpected")
                for ordinal, row in enumerate(reader, 1):
                    if None in row or None in row.values():
                        yield ordinal, None
                        continue
                    values = {name: None if value == "" else value for name, value in row.items()}
                    if values["multiple_issues"] in {"true", "false"}:
                        values["multiple_issues"] = values["multiple_issues"] == "true"
                    yield ordinal, values
            else:
                for ordinal, line in enumerate(text, 1):
                    try:
                        value = json.loads(line, object_pairs_hook=unique_object)
                        if not isinstance(value, dict) or set(value) != set(COLUMNS):
                            raise ValueError
                    except ValueError:
                        yield ordinal, None
                        continue
                    yield ordinal, value
        except UnicodeError:
            raise IngestionError("Annotation encoding invalid; UTF-8 required") from None
        except csv.Error:
            raise IngestionError("Malformed annotation CSV") from None
        finally:
            text.close()


def validate(root: Path, registry: Registry, input_path: Path, schema_only: bool = False) -> dict:
    """Validate without writing labels or copying reasoning into validation reports."""
    load_taxonomy(root)
    path = safe_path(input_path if input_path.is_absolute() else root / input_path)
    sidecar = safe_path(metadata_path(path))
    if not sidecar.is_file() or sidecar.stat().st_size > 65536:
        raise IngestionError("Annotation metadata sidecar is required and must fit 64 KiB")
    try:
        metadata = AnnotationMetadata.model_validate(
            json.loads(sidecar.read_text("utf-8"), object_pairs_hook=unique_object)
        )
    except (ValueError, UnicodeError):
        raise IngestionError("Invalid annotation metadata or taxonomy binding") from None
    allowed_ids, source_checksum = inventory(root, registry, metadata)
    if not schema_only and metadata.purpose != "ANNOTATION_SUBMISSION":
        raise IngestionError(
            "Strict validation rejects blank templates; submission context required"
        )
    keys, errors = set(), []
    counts = Counter()
    for ordinal, row in annotation_rows(path):
        counts["records"] += 1
        if counts["records"] > MAX_RECORDS:
            raise IngestionError("Annotation input exceeds maximum record count")
        code = None
        try:
            if row is None:
                raise ValueError
            value = (BlankAnnotation if schema_only else Annotation).model_validate(row)
            for field in (
                "source_id",
                "dataset_version",
                "dataset_type",
                "taxonomy_version",
                "taxonomy_checksum",
            ):
                entry = getattr(value, field)
                if entry is not None and entry != getattr(metadata, field):
                    code = "SOURCE_OR_VERSION_MISMATCH"
                    raise ValueError
            if not schema_only:
                if value.feedback_id not in allowed_ids:
                    code = "UNKNOWN_FEEDBACK_MEMBERSHIP"
                    raise ValueError
                if value.record_key in keys:
                    code = "DUPLICATE_ANNOTATION_KEY"
                    raise ValueError
                keys.add(value.record_key)
                counts[value.annotation_status] += 1
        except (ValidationError, ValueError, TypeError) as error:
            counts["invalid"] += 1
            if len(errors) < 100:
                detail = {"row": ordinal, "code": code or "INVALID_ANNOTATION"}
                if isinstance(error, ValidationError):
                    issues = error.errors(include_input=False, include_url=False)
                    detail["fields"] = sorted(
                        {
                            part
                            for issue in issues
                            for part in issue["loc"]
                            if isinstance(part, str) and part in COLUMNS
                        }
                    ) or ["record"]
                    detail["rules"] = sorted(
                        {
                            str(issue.get("ctx", {}).get("error"))
                            for issue in issues
                            if str(issue.get("ctx", {}).get("error")) in VALIDATION_RULES
                        }
                    )
                errors.append(detail)
        else:
            counts["valid"] += 1
    if metadata.dataset_type == "RESEARCH":
        # Recheck permission/review and the exact inventory snapshot before returning.
        if inventory(root, registry, metadata) != (allowed_ids, source_checksum):
            raise IngestionError("Research provenance changed during annotation validation")
    failed = bool(counts["invalid"] or not schema_only and not counts["records"])
    return {
        "status": "FAIL" if failed else "PASS",
        "validation_level": "SCHEMA_ONLY" if schema_only else "FULL",
        "taxonomy_version": VERSION,
        "taxonomy_checksum": CHECKSUM,
        "source_manifest_checksum": source_checksum,
        "dataset_type": metadata.dataset_type,
        "human_gold": False,
        "metrics_usage": "SOFTWARE_TEST_ONLY"
        if metadata.dataset_type != "RESEARCH"
        else "CONTRACT_VALIDATION_ONLY",
        "record_count": counts["records"],
        "valid_count": counts["valid"],
        "invalid_count": counts["invalid"],
        "status_counts": {
            state: counts[state]
            for state in ("SUBMITTED", "REQUIRES_REVIEW", "OUT_OF_SCOPE", "UNLABELABLE")
        },
        "errors": errors,
        "omitted_error_count": max(0, counts["invalid"] - len(errors)),
        "quality_failures": ["EMPTY_SUBMISSION"]
        if not schema_only and not counts["records"]
        else [],
    }
