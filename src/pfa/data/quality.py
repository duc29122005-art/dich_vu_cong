"""Typed profiling policy, quality gates, and aggregate-only report rendering."""

import re
from datetime import UTC, datetime, timedelta, timezone, tzinfo
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator, model_validator

from pfa.data.official_schema import Feedback
from pfa.data.registry import Identifier, Metadata, Text

QualityStatus = Literal["PASS", "WARN", "FAIL", "BLOCKED_PERMISSION", "NOT_AVAILABLE"]


def known_zone(value: str) -> tzinfo:
    """Accept explicit fixed offsets, UTC, or an installed IANA timezone."""
    if value == "UTC":
        return UTC
    match = re.fullmatch(r"([+-])(\d{2}):(\d{2})", value)
    if match:
        hours, minutes = int(match[2]), int(match[3])
        if hours >= 24 or minutes >= 60:
            raise ValueError("Invalid timezone offset")
        return timezone((1 if match[1] == "+" else -1) * timedelta(hours=hours, minutes=minutes))
    try:
        return ZoneInfo(value)
    except (ValueError, ZoneInfoNotFoundError):
        raise ValueError("Timezone is unknown or its IANA database is unavailable") from None


class QualityConfig(Metadata):
    max_records: int = Field(default=10000, gt=0, le=100000)
    max_input_bytes: int = Field(default=20 * 1024**2, gt=0, le=1024**3)
    max_text_length: int = Field(default=20000, gt=0, le=100000)
    short_text_chars: int = Field(default=10, ge=0)
    long_text_chars: int = Field(default=1000, gt=0)
    unicode_nfc: bool = True
    whitespace: bool = True
    controls: bool = True
    known_timezone: str | None = None
    max_invalid_fraction: float = Field(default=0.25, ge=0, le=1)
    missingness_warn_fraction: float = Field(default=0.5, ge=0, le=1)
    missingness_fail_fraction: float | None = Field(default=None, ge=0, le=1)
    duplicate_warn_fraction: float = Field(default=0.2, ge=0, le=1)
    duplicate_fail_fraction: float = Field(default=0.5, ge=0, le=1)
    near_duplicate_threshold: float = Field(default=0.85, gt=0, le=1)
    max_candidate_pairs: int = Field(default=10000, gt=0, le=100000)

    @field_validator("known_timezone")
    @classmethod
    def timezone_available(cls, value: str | None) -> str | None:
        if value is not None:
            known_zone(value)
        return value

    @model_validator(mode="after")
    def ordered_thresholds(self) -> "QualityConfig":
        if not self.short_text_chars < self.long_text_chars <= self.max_text_length:
            raise ValueError("Require short < long <= maximum text length")
        if self.duplicate_warn_fraction > self.duplicate_fail_fraction:
            raise ValueError("Duplicate warning threshold must not exceed failure threshold")
        if (
            self.missingness_fail_fraction is not None
            and self.missingness_warn_fraction > self.missingness_fail_fraction
        ):
            raise ValueError("Missingness warning threshold must not exceed failure threshold")
        return self


class ProfileContext(Metadata):
    dataset_source: Identifier
    dataset_version: Text
    dataset_type: Literal["SYNTHETIC", "BENCHMARK", "RESEARCH"]
    expected_record_source: Identifier
    source_manifest_reference: Text
    source_manifest_checksum: Text
    permission_verified: bool
    manifest_verified: bool
    human_reviewed: bool
    supported_format: bool = True


class QualityReport(Metadata):
    dataset_source: Identifier
    dataset_version: Text
    dataset_type: Literal["SYNTHETIC", "BENCHMARK", "RESEARCH"]
    record_count: int = Field(ge=0)
    valid_count: int = Field(ge=0)
    invalid_count: int = Field(ge=0)
    missing_values: dict[str, int]
    text_length_statistics: dict
    unicode_statistics: dict
    timestamp_coverage: dict
    agency_distribution: dict[str, int]
    domain_distribution: dict[str, int]
    processing_status_distribution: dict[str, int]
    duplicate_statistics: dict
    privacy_statistics: dict
    source_manifest_reference: Text
    source_manifest_checksum: Text
    transformation_version: Text
    processing_configuration_hash: Text
    transformation_statistics: dict
    quality_warnings: list[str]
    quality_failures: list[str]
    overall_quality_status: QualityStatus
    publication_eligible: bool

    @model_validator(mode="after")
    def accounting(self) -> "QualityReport":
        if self.record_count != self.valid_count + self.invalid_count:
            raise ValueError("Profiling record counts do not reconcile")
        if self.dataset_type != "RESEARCH" and self.publication_eligible:
            raise ValueError("Synthetic/benchmark reports cannot authorize research publication")
        return self


def parse_timestamp(value: object, configured_zone: str | None) -> tuple[datetime | None, str]:
    """Keep unknown timezones ambiguous; reject nonexistent/ambiguous local times."""
    try:
        parsed = Feedback.timestamp(value)
        if parsed is None:
            return None, "MISSING"
        if parsed.tzinfo is not None:
            return parsed.astimezone(UTC), "AWARE_TO_UTC"
        if configured_zone is None:
            return parsed, "AMBIGUOUS_TIMEZONE"
        zone = known_zone(configured_zone)
        candidates = [parsed.replace(tzinfo=zone, fold=fold) for fold in (0, 1)]
        valid = [
            item
            for item in candidates
            if item.astimezone(UTC).astimezone(zone).replace(tzinfo=None) == parsed
        ]
        if not valid or len({item.utcoffset() for item in valid}) > 1:
            return None, "INVALID_LOCAL_TIME"
        return valid[0].astimezone(UTC), "CONFIGURED_TIMEZONE_TO_UTC"
    except (ValueError, TypeError, OverflowError):
        return None, "INVALID"


def quality_gates(
    report: QualityReport, context: ProfileContext, config: QualityConfig
) -> QualityReport:
    """Operational thresholds are configurable; mandatory research safeguards are not."""
    warnings, failures = [], []
    n = report.record_count
    if not context.supported_format:
        failures.append("UNSUPPORTED_FORMAT")
    if not context.manifest_verified:
        failures.append("MANIFEST_INTEGRITY")
    invalid_fraction = report.invalid_count / n if n else 0
    if report.invalid_count:
        (failures if invalid_fraction > config.max_invalid_fraction else warnings).append(
            "INVALID_RECORDS"
        )
    for field in ("created_at", "agency", "domain", "processing_status"):
        fraction = report.missing_values.get(field, 0) / n if n else 0
        if (
            config.missingness_fail_fraction is not None
            and fraction > config.missingness_fail_fraction
        ):
            failures.append("MISSING_" + field.upper())
        elif fraction > config.missingness_warn_fraction:
            warnings.append("MISSING_" + field.upper())
    duplicates = report.duplicate_statistics["exact_duplicate_count"]
    fraction = duplicates / report.valid_count if report.valid_count else 0
    if fraction > config.duplicate_fail_fraction:
        failures.append("DUPLICATE_ANOMALY")
    elif fraction > config.duplicate_warn_fraction:
        warnings.append("DUPLICATE_ANOMALY")
    if report.duplicate_statistics["near_duplicate_pair_count"]:
        warnings.append("NEAR_DUPLICATES_REQUIRE_REVIEW")
    if any(
        item["INVALID"] + item["INVALID_LOCAL_TIME"] for item in report.timestamp_coverage.values()
    ):
        warnings.append("INVALID_TIMESTAMPS")
    if any(item["AMBIGUOUS_TIMEZONE"] for item in report.timestamp_coverage.values()):
        warnings.append("TIMEZONE_AMBIGUOUS")
    if (
        report.unicode_statistics["uncertain_language_candidates"]
        or report.unicode_statistics["mixed_language_candidates"]
    ):
        warnings.append("LANGUAGE_HEURISTIC_REQUIRES_REVIEW")
    if report.text_length_statistics["short_count"] or report.text_length_statistics["long_count"]:
        warnings.append("UNUSUAL_TEXT_LENGTH")
    if report.unicode_statistics["unsafe_controls_remaining"]:
        failures.append("UNSAFE_CONTROLS_REMAIN")
    if report.unicode_statistics["replacement_character_count"]:
        warnings.append("UNICODE_REQUIRES_REVIEW")
    if report.privacy_statistics["review_pending_count"]:
        (failures if context.dataset_type == "RESEARCH" else warnings).append(
            "UNRESOLVED_PRIVACY_REVIEW"
        )
    if context.dataset_type == "RESEARCH" and (
        not context.human_reviewed
        or report.invalid_count
        or report.timestamp_coverage["created_at"]["INVALID_LOCAL_TIME"]
        or report.timestamp_coverage["response_date"]["INVALID_LOCAL_TIME"]
    ):
        failures.append("MANDATORY_RESEARCH_VALIDATION")
    status: QualityStatus = "FAIL" if failures else "WARN" if warnings else "PASS"
    if not n:
        status = "NOT_AVAILABLE"
    if context.dataset_type != "SYNTHETIC" and not context.permission_verified:
        failures.append("PERMISSION_REQUIRED")
        status = "BLOCKED_PERMISSION"
    return report.model_copy(
        update={
            "quality_warnings": sorted(set(warnings)),
            "quality_failures": sorted(set(failures)),
            "overall_quality_status": status,
            "publication_eligible": bool(
                context.dataset_type == "RESEARCH"
                and context.permission_verified
                and context.manifest_verified
                and context.human_reviewed
                and not failures
                and n
            ),
        }
    )


def markdown_summary(report: QualityReport) -> str:
    """Fixed labels and numeric aggregates only; never render examples or metadata values."""
    return "\n".join(
        [
            "# Dataset quality audit",
            "",
            f"Dataset type: **{report.dataset_type}**",
            "Synthetic statistics are software tests, not research results."
            if report.dataset_type == "SYNTHETIC"
            else "Automated screening is not proof of anonymity or scientific suitability.",
            "",
            f"Quality status: **{report.overall_quality_status}**",
            "",
            "| Metric | Count |",
            "|---|---:|",
            f"| Input records | {report.record_count} |",
            f"| Valid records | {report.valid_count} |",
            f"| Invalid records | {report.invalid_count} |",
            f"| Exact duplicates | {report.duplicate_statistics['exact_duplicate_count']} |",
            "| Near-duplicate pairs | "
            f"{report.duplicate_statistics['near_duplicate_pair_count']} |",
            f"| Privacy-flagged records | {report.privacy_statistics['flagged_record_count']} |",
            f"| Privacy review pending | {report.privacy_statistics['review_pending_count']} |",
            "",
            "Warnings: " + (", ".join(report.quality_warnings) or "None"),
            "Failures: " + (", ".join(report.quality_failures) or "None"),
            "",
            "Language candidates are heuristic. No validated language detector is installed.",
            "No examples, raw identifiers or original text are included. STEP 04 gates apply.",
            "",
        ]
    )
