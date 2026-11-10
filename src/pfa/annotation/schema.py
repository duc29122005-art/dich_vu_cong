"""Independent annotation records; workflow states never become supervised labels."""

from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import StringConstraints, field_validator, model_validator

from pfa.annotation.taxonomy import CHECKSUM, VERSION, Sentiment, Status, Topic
from pfa.data.official_schema import Feedback
from pfa.data.privacy import audit_screen
from pfa.data.registry import Identifier, Metadata

FeedbackID = Annotated[str, StringConstraints(strict=True, pattern=r"^f_[a-f0-9]{32}$")]
DatasetVersion = Annotated[str, StringConstraints(strict=True, pattern=r"^of_[a-f0-9]{32}$")]
AnnotatorID = Annotated[str, StringConstraints(strict=True, pattern=r"^ann_[a-f0-9]{16}$")]
Reason = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=2000)]
VALIDATION_RULES = {
    "DRAFT_NOT_SUBMITTED",
    "EXCLUDED_RECORD_HAS_LABELS_OR_ISSUES",
    "LABEL_JUSTIFICATION_MISMATCH",
    "UNKNOWN_SEVERITY_REQUIRES_REASON",
    "INCOMPLETE_SUPERVISED_LABELS",
    "UNRESOLVED_REVIEW_REASON",
    "REVIEW_REASON_REQUIRED",
    "UNSAFE_REASON",
    "INVALID_ANNOTATION_TIMESTAMP",
    "NONBLANK_SINGLE_LINE_REASON_REQUIRED",
}


class BlankAnnotation(Metadata):
    feedback_id: FeedbackID | None = None
    dataset_version: DatasetVersion | None = None
    taxonomy_version: Literal[VERSION] | None = None
    taxonomy_checksum: Literal[CHECKSUM] | None = None
    source_id: Identifier | None = None
    dataset_type: Literal["SYNTHETIC", "RESEARCH"] | None = None
    annotator_id: AnnotatorID | None = None
    topic_label: Topic | None = None
    sentiment_label: Sentiment | None = None
    severity_label: Literal["low", "medium", "high", "unknown"] | None = None
    multiple_issues: bool | None = None
    annotation_status: Status | None = None
    topic_justification: Reason | None = None
    sentiment_justification: Reason | None = None
    severity_justification: Reason | None = None
    review_reason: Reason | None = None
    annotated_at: datetime | None = None

    @field_validator("annotated_at", mode="before")
    @classmethod
    def timestamp(cls, value: object) -> datetime | None:
        result = Feedback.timestamp(value)
        if result is not None and (result.tzinfo is None or result > datetime.now(UTC)):
            raise ValueError("INVALID_ANNOTATION_TIMESTAMP")
        return result

    @field_validator(
        "topic_justification", "sentiment_justification", "severity_justification", "review_reason"
    )
    @classmethod
    def safe_reason(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if not value.strip() or any(ord(char) < 32 for char in value):
            raise ValueError("NONBLANK_SINGLE_LINE_REASON_REQUIRED")
        if audit_screen(value, 2000).counts:
            raise ValueError("UNSAFE_REASON")
        return value  # Preserve human text exactly; never silently repair it.


class Annotation(BlankAnnotation):
    feedback_id: FeedbackID
    dataset_version: DatasetVersion
    taxonomy_version: Literal[VERSION]
    taxonomy_checksum: Literal[CHECKSUM]
    source_id: Identifier
    dataset_type: Literal["SYNTHETIC", "RESEARCH"]
    annotator_id: AnnotatorID
    multiple_issues: bool
    annotation_status: Status
    annotated_at: datetime

    @model_validator(mode="after")
    def coherent_submission(self) -> "Annotation":
        status = self.annotation_status
        if status == "DRAFT":
            raise ValueError("DRAFT_NOT_SUBMITTED")
        labels = (self.topic_label, self.sentiment_label, self.severity_label)
        reasons = (
            self.topic_justification,
            self.sentiment_justification,
            self.severity_justification,
        )
        if status in {"OUT_OF_SCOPE", "UNLABELABLE"}:
            if any(labels) or any(reasons) or not self.review_reason or self.multiple_issues:
                raise ValueError("EXCLUDED_RECORD_HAS_LABELS_OR_ISSUES")
            return self
        if any((label is None) != (reason is None) for label, reason in zip(labels, reasons)):
            raise ValueError("LABEL_JUSTIFICATION_MISMATCH")
        if self.severity_label == "unknown" and not self.review_reason:
            raise ValueError("UNKNOWN_SEVERITY_REQUIRES_REASON")
        if status == "SUBMITTED":
            if not all(labels) or self.severity_label not in ("low", "medium", "high"):
                raise ValueError("INCOMPLETE_SUPERVISED_LABELS")
            if self.review_reason is not None:
                raise ValueError("UNRESOLVED_REVIEW_REASON")
        elif status == "REQUIRES_REVIEW" and not self.review_reason:
            raise ValueError("REVIEW_REASON_REQUIRED")
        return self

    @property
    def record_key(self) -> tuple[str, str, str, str]:
        """Separate annotators and taxonomy/dataset versions; no upsert or overwrite."""
        return (self.dataset_version, self.feedback_id, self.taxonomy_version, self.annotator_id)


class AnnotationMetadata(Metadata):
    format_version: Literal["annotation-1"]
    purpose: Literal["BLANK_TEMPLATE", "ANNOTATION_SUBMISSION"]
    taxonomy_version: Literal[VERSION]
    taxonomy_checksum: Literal[CHECKSUM]
    dataset_type: Literal["TEMPLATE", "SYNTHETIC", "RESEARCH"]
    source_id: Identifier | None
    dataset_version: DatasetVersion | None
    columns: list[str]
    human_gold: Literal[False]

    @model_validator(mode="after")
    def context(self) -> "AnnotationMetadata":
        if self.columns != list(BlankAnnotation.model_fields):
            raise ValueError("Exact versioned column order required in metadata")
        blank = self.purpose == "BLANK_TEMPLATE"
        if blank != (self.dataset_type == "TEMPLATE"):
            raise ValueError("Template metadata must remain separate from dataset submissions")
        if blank and (self.source_id is not None or self.dataset_version is not None):
            raise ValueError("Blank templates contain no invented dataset provenance")
        if not blank and (self.source_id is None or self.dataset_version is None):
            raise ValueError("Submission provenance required")
        return self
