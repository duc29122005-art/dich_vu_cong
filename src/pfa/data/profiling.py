"""Bounded, aggregate-only audits of trusted synthetic or verified STEP 04 data."""

import hashlib
import io
import json
import os
import re
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Iterable
from pathlib import Path
from tempfile import TemporaryDirectory

from pfa.data import official
from pfa.data.official_io import (
    IngestionBlocked,
    IngestionError,
    protect_directory,
    rows,
    safe_path,
)
from pfa.data.official_schema import Feedback, ImportOptions
from pfa.data.permissions import current_decision
from pfa.data.preprocessing import TRANSFORMATION_VERSION, transform_text
from pfa.data.privacy import AUDIT_VERSION, audit_screen
from pfa.data.quality import (
    ProfileContext,
    QualityConfig,
    QualityReport,
    markdown_summary,
    parse_timestamp,
    quality_gates,
)
from pfa.data.registry import Registry

PROFILING_VERSION = "profile-1"
# Public test-only key: never used for real records or claimed to protect real identities.
SYNTHETIC_KEY = hashlib.sha256(b"pfa-generated-synthetic-audit-only").digest()
TIME_STATES = (
    "MISSING",
    "INVALID",
    "AWARE_TO_UTC",
    "AMBIGUOUS_TIMEZONE",
    "INVALID_LOCAL_TIME",
    "CONFIGURED_TIMEZONE_TO_UTC",
)


def configuration_hash(config: QualityConfig) -> str:
    """Bind every processing policy and algorithm version without including secrets."""
    return hashlib.sha256(
        json.dumps(
            [
                config.model_dump(),
                PROFILING_VERSION,
                TRANSFORMATION_VERSION,
                AUDIT_VERSION,
            ],
            sort_keys=True,
        ).encode()
    ).hexdigest()


def profile_records(
    records: Iterable[tuple[int, dict | None]],
    context: ProfileContext,
    key: bytes,
    config: QualityConfig | None = None,
) -> tuple[QualityReport, dict]:
    """Consume records once; retain bounded keyed indexes, numeric audits and lengths only."""
    config = config or QualityConfig()
    if len(key) < 32:
        raise IngestionError("A protected fingerprint key of at least 32 bytes is required")
    if context.dataset_type != "SYNTHETIC" and not context.permission_verified:
        raise IngestionBlocked("BLOCKED_PERMISSION: verified processing permission required")
    missing = Counter({name: 0 for name in Feedback.model_fields})
    absent = missing.copy()
    distributions = {field: Counter() for field in ("agency", "domain", "processing_status")}
    timestamps = {
        field: Counter({state: 0 for state in TIME_STATES})
        for field in ("created_at", "response_date")
    }
    dates = {field: [] for field in timestamps}
    unicode_counts, privacy, changes, totals = Counter(), Counter(), Counter(), Counter()
    lengths, audits, pairs = [], [], []
    indexes = {
        name: defaultdict(list)
        for name in ("source_record", "feedback_id", "normalized_text", "sanitized_content")
    }
    token_sets, inverted = {}, {}
    parent = {}

    def find(item: str) -> str:
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    def join(left: str, right: str) -> None:
        a, b = sorted((find(left), find(right)))
        parent[b] = a

    for ordinal, record in records:
        totals["records"] += 1
        if totals["records"] > config.max_records:
            raise IngestionError("Profiling exceeds configured maximum record count")
        ref = official.fingerprint(key, context.dataset_version, str(totals["records"]))
        audit = {"record_ref": ref, "ordinal": ordinal, "changes": {}, "warnings": []}
        audits.append(audit)
        if record is None:
            totals["invalid"] += 1
            totals["unparseable"] += 1
            audit["warnings"].append("UNPARSEABLE_RECORD")
            continue
        source = record.get("source_id")
        if source not in (None, "") and source != context.expected_record_source:
            raise IngestionError("Record source identity differs from the authorized provenance")
        for field in missing:
            absent[field] += field not in record
            value = record.get(field)
            missing[field] += value is None or isinstance(value, str) and not value.strip()
        for field, distribution in distributions.items():
            value = record.get(field)
            bucket = (
                "MISSING"
                if value is None or value == "" or (isinstance(value, str) and not value.strip())
                else "b_" + official.fingerprint(key, field, json.dumps(value, sort_keys=True))
            )
            distribution[bucket] += 1
        canonical = record.copy()
        for field in timestamps:
            parsed, state = parse_timestamp(record.get(field), config.known_timezone)
            timestamps[field][state] += 1
            audit["changes"][field] = state
            if parsed is not None and state != "AMBIGUOUS_TIMEZONE":
                dates[field].append(parsed.date().isoformat())
                canonical[field] = parsed
            if state in {"INVALID", "INVALID_LOCAL_TIME", "AMBIGUOUS_TIMEZONE"}:
                audit["warnings"].append(field.upper() + "_" + state)
        text = record.get("content")
        categories = Counter()
        normalized = sanitized = None
        try:
            if not isinstance(text, str):
                raise ValueError
            lengths.append(len(text))
            totals["empty"] += not text.strip()
            unicode_counts["non_nfc_count"] += unicodedata.normalize("NFC", text) != text
            unicode_counts["replacement_character_count"] += text.count("\ufffd")
            unicode_counts["control_character_count"] += sum(
                unicodedata.category(char) in {"Cc", "Cf", "Cs"} and not char.isspace()
                for char in text
            )
            try:
                text.encode("utf-8")
            except UnicodeError:
                unicode_counts["invalid_unicode_count"] += 1
                raise
            letters = [char for char in unicodedata.normalize("NFC", text) if char.isalpha()]
            has_marks = any(unicodedata.decomposition(char) or char in "đĐ" for char in letters)
            unicode_counts["diacritic_record_count"] += bool(has_marks)
            # ponytail: script/word cues only; replace with a validated detector when available.
            english = bool(re.search(r"\b(?:the|please|service|thank|hello)\b", text, re.I))
            foreign = any("LATIN" not in unicodedata.name(char, "") for char in letters)
            unicode_counts["mixed_language_candidates"] += bool(has_marks and english or foreign)
            unicode_counts["uncertain_language_candidates"] += not has_marks
            normalized, delta = transform_text(
                text,
                config.max_text_length,
                unicode_nfc=config.unicode_nfc,
                whitespace=config.whitespace,
                controls=config.controls,
            )
            changes.update(delta)
            audit["changes"]["content"] = delta
            unicode_counts["unsafe_controls_remaining"] += sum(
                unicodedata.category(char) in {"Cc", "Cf", "Cs"} and not char.isspace()
                for char in normalized
            )
            canonical["content"] = normalized
            sanitized = audit_screen(normalized, config.max_text_length).text
        except (ValueError, UnicodeError):
            audit["warnings"].append("INVALID_TEXT")
        for field in ("feedback_id", "content", "agency", "domain", "channel", "processing_status"):
            value = record.get(field)
            if isinstance(value, str) and value.strip():
                try:
                    result = audit_screen(value, config.max_text_length)
                    categories.update(result.counts)
                except (ValueError, UnicodeError):
                    audit["warnings"].append("PRIVACY_SCREENING_INCOMPLETE")
        privacy.update(categories)
        flagged = bool(categories) or "PRIVACY_SCREENING_INCOMPLETE" in audit["warnings"]
        totals["privacy_flagged"] += flagged
        audit["privacy_categories"] = dict(categories)
        audit["privacy_review_required"] = flagged
        try:
            Feedback.model_validate(canonical)
            if normalized is None or any(
                audit["changes"][field] in {"INVALID", "INVALID_LOCAL_TIME"} for field in timestamps
            ):
                raise ValueError
        except (ValueError, TypeError):
            totals["invalid"] += 1
            audit["warnings"].append("INVALID_SCHEMA_OR_VALUE")
            continue
        totals["valid"] += 1
        parent[ref] = ref
        values = {
            "source_record": json.dumps(record, sort_keys=True, default=str),
            "feedback_id": record["feedback_id"],
            "normalized_text": normalized,
            "sanitized_content": sanitized,
        }
        duplicate = False
        for name, value in values.items():
            digest = official.fingerprint(key, name, value)
            group = indexes[name][digest]
            if group:
                join(group[0], ref)
                if name != "normalized_text":
                    duplicate = True
            group.append(ref)
        totals["exact_duplicates"] += duplicate
        if not duplicate:
            tokens = {
                official.fingerprint(key, "token", word)
                for word in re.findall(r"\w+", sanitized.casefold())
            }
            new_pairs = official.deduplicate(
                tokens, ref, token_sets, inverted, config.near_duplicate_threshold
            )
            pairs.extend(new_pairs)
            if len(pairs) > config.max_candidate_pairs:
                raise IngestionError("Near-duplicate candidates exceed configured review limit")
            for left, right in new_pairs:
                join(left, right)
    ordered = sorted(lengths)
    duplicate_groups = {
        name: [members for _, members in sorted(index.items()) if len(members) > 1]
        for name, index in indexes.items()
    }
    lineage = [{"record_ref": ref, "group_id": "g_" + find(ref)} for ref in sorted(parent)]
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
    report = QualityReport(
        dataset_source=context.dataset_source,
        dataset_version=context.dataset_version,
        dataset_type=context.dataset_type,
        record_count=totals["records"],
        valid_count=totals["valid"],
        invalid_count=totals["invalid"],
        missing_values=dict(missing),
        text_length_statistics={
            "distribution": distribution,
            "observed_text_count": len(lengths),
            "empty_count": totals["empty"],
            "short_count": sum(n < config.short_text_chars for n in lengths),
            "long_count": sum(n > config.long_text_chars for n in lengths),
        },
        unicode_statistics={
            name: unicode_counts[name]
            for name in (
                "non_nfc_count",
                "replacement_character_count",
                "control_character_count",
                "invalid_unicode_count",
                "diacritic_record_count",
                "mixed_language_candidates",
                "uncertain_language_candidates",
                "unsafe_controls_remaining",
            )
        },
        timestamp_coverage={
            field: {
                **dict(counts),
                "min_date": min(dates[field], default=None),
                "max_date": max(dates[field], default=None),
            }
            for field, counts in timestamps.items()
        },
        agency_distribution=dict(distributions["agency"]),
        domain_distribution=dict(distributions["domain"]),
        processing_status_distribution=dict(distributions["processing_status"]),
        duplicate_statistics={
            "exact_duplicate_count": totals["exact_duplicates"],
            "unique_count": totals["valid"] - totals["exact_duplicates"],
            "near_duplicate_pair_count": len(pairs),
            "by_category": {
                name: sum(len(group) - 1 for group in groups)
                for name, groups in duplicate_groups.items()
            },
            "same_case_or_thread": "NOT_AVAILABLE",
        },
        privacy_statistics={
            "categories": dict(privacy),
            "flagged_record_count": totals["privacy_flagged"],
            "review_pending_count": totals["privacy_flagged"],
            "human_approved_anonymization": False,
        },
        source_manifest_reference=context.source_manifest_reference,
        source_manifest_checksum=context.source_manifest_checksum,
        transformation_version=TRANSFORMATION_VERSION,
        processing_configuration_hash=configuration_hash(config),
        transformation_statistics={
            "changes": dict(changes),
            "missing_fields": dict(absent),
            "unparseable_records": totals["unparseable"],
            "profiler_version": PROFILING_VERSION,
            "privacy_audit_version": AUDIT_VERSION,
        },
        quality_warnings=[],
        quality_failures=[],
        overall_quality_status="PASS",
        publication_eligible=False,
    )
    return quality_gates(report, context, config), {
        "dataset_type": context.dataset_type,
        "dataset_version": context.dataset_version,
        "transformation_version": TRANSFORMATION_VERSION,
        "processing_configuration_hash": configuration_hash(config),
        "record_audit": audits,
        "duplicate_groups": duplicate_groups,
        "near_duplicate_pairs": pairs,
        "split_group_lineage": lineage,
    }


def save_reports(root: Path, report: QualityReport, audit: dict) -> Path:
    """Publish an immutable aggregate bundle by directory rename; never overwrite."""
    documents = {"quality_report.json": report.model_dump(mode="json"), "audit.json": audit}
    encoded = {
        name: json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True) + "\n"
        for name, value in documents.items()
    }
    encoded["summary.md"] = markdown_summary(report)
    digest = hashlib.sha256(json.dumps(encoded, sort_keys=True).encode()).hexdigest()
    boundary = safe_path(root / "reports/dataset", root)
    boundary.mkdir(parents=True, exist_ok=True)
    target = safe_path(boundary / ("q_" + digest), boundary)
    if target.exists():
        if any(
            not safe_path(target / name, target).is_file()
            or (target / name).read_text(encoding="utf-8") != value
            for name, value in encoded.items()
        ):
            raise IngestionError("Existing immutable report bundle failed integrity validation")
        return target
    with TemporaryDirectory(prefix=".audit-", dir=boundary) as temporary:
        work = Path(temporary)
        protect_directory(work)
        for name, value in encoded.items():
            with (work / name).open("x", encoding="utf-8", newline="\n") as stream:
                if os.name != "nt":
                    (work / name).chmod(0o600)
                stream.write(value)
                stream.flush()
                os.fsync(stream.fileno())
        work.rename(target)
    return target


def run_audit(
    root: Path,
    registry: Registry,
    source_id: str,
    key: bytes | None = None,
    dataset_version: str | None = None,
    config_path: Path | None = None,
) -> tuple[QualityReport, Path]:
    """Permission first; synthetic means the checksum-bound bundled fixture only."""
    manifest = None
    if source_id == "synthetic_demo":
        if dataset_version is not None:
            raise IngestionError("Synthetic audits use only the bundled fixture version")
        payload = official.synthetic_fixture_bytes()
        checksum = hashlib.sha256(payload).hexdigest()
        context = ProfileContext(
            dataset_source=source_id,
            dataset_version="synthetic_" + checksum,
            dataset_type="SYNTHETIC",
            expected_record_source="synthetic_fixture",
            source_manifest_reference="bundled_synthetic_fixture",
            source_manifest_checksum=checksum,
            permission_verified=False,
            manifest_verified=True,
            human_reviewed=False,
        )
        key = SYNTHETIC_KEY
    else:
        decision = current_decision(root, registry, source_id)
        official.authorize(root, registry, source_id, decision.approval_ref if decision else "")
        if not dataset_version:
            raise IngestionError("NOT_AVAILABLE: specify a verified STEP 04 dataset version")
        if not re.fullmatch(official.VERSION_PATTERN, dataset_version):
            raise IngestionError("Invalid STEP 04 dataset version")
        manifest_path = safe_path(root / "data/manifests" / dataset_version / "manifest.json", root)
        if not manifest_path.is_file():
            raise IngestionError("NOT_AVAILABLE: verified STEP 04 manifest required")
        manifest = official.OfficialManifest.model_validate_json(manifest_path.read_bytes())
        if manifest.source_id != source_id or manifest.provenance != "REAL_EXTERNAL":
            raise IngestionError("Manifest source/provenance does not match requested real source")
        official.verify(root, registry, dataset_version)
        checksum = official.file_digest(manifest_path)
        context = ProfileContext(
            dataset_source=source_id,
            dataset_version=dataset_version,
            dataset_type="RESEARCH",
            expected_record_source=source_id,
            source_manifest_reference=dataset_version,
            source_manifest_checksum=checksum,
            permission_verified=True,
            manifest_verified=True,
            human_reviewed=True,
        )
        if key is None or len(key) < 32:
            raise IngestionError("Set a protected fingerprint key before profiling real data")
    config = (
        QualityConfig()
        if config_path is None
        else QualityConfig.model_validate_json(safe_path(config_path).read_bytes())
    )
    options = ImportOptions(
        max_records=config.max_records,
        max_input_bytes=config.max_input_bytes,
        max_text_length=config.max_text_length,
    )
    if manifest is None:
        with io.BytesIO(payload) as stream:
            report, audit = profile_records(rows(stream, ".csv", options), context, key, config)
    else:
        path = safe_path(root / "data/processed" / dataset_version / "feedback.jsonl", root)
        with path.open("rb") as stream:
            report, audit = profile_records(rows(stream, ".jsonl", options), context, key, config)
        official.verify(root, registry, dataset_version)
        if official.file_digest(manifest_path) != checksum:
            raise IngestionError("Manifest changed during profiling")
    return report, save_reports(root, report, audit)
