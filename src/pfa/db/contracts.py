"""Closed workflow requests: no arbitrary text, role, model path or free-form audit payload."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from pfa.annotation.taxonomy import Sentiment, Severity, Topic
from pfa.api.schemas import TaskPrediction
from pfa.data.registry import Identifier, Metadata

State = Literal["PENDING_REVIEW", "IN_REVIEW", "REVIEWED", "NEEDS_ADJUDICATION", "ADJUDICATED"]


class CreateFeedback(Metadata):
    fixture_id: int = Field(ge=0, lt=120)
    operation_id: UUID = Field(strict=False)
    source_id: Identifier = "synthetic_demo"
    is_synthetic: bool = True


class Labels(Metadata):
    topic: Topic
    sentiment: Sentiment
    severity: Severity | Literal["unknown"]


class Review(Metadata):
    operation_id: UUID = Field(strict=False)
    expected_version: int = Field(ge=1)
    action: Literal["CLAIM", "ASSIGN", "CONFIRM", "CORRECT", "ESCALATE", "ADJUDICATE"]
    reason_code: Literal[
        "CLAIM",
        "ASSIGN",
        "CONFIRM_MODEL",
        "CORRECTION",
        "INSUFFICIENT_EVIDENCE",
        "MULTIPLE_ISSUES",
        "OUT_OF_SCOPE",
        "UNLABELABLE",
        "ESCALATE_CONFLICT",
        "HUMAN_ADJUDICATION",
    ]
    labels: Labels | None = None
    prediction_id: UUID | None = Field(default=None, strict=False)
    assignee_id: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]{2,63}$")

    @model_validator(mode="after")
    def consistent(self):
        fixed = {"CLAIM": "CLAIM", "ASSIGN": "ASSIGN", "CONFIRM": "CONFIRM_MODEL"}
        if self.action in fixed and (
            self.reason_code != fixed[self.action] or self.labels is not None
        ):
            raise ValueError("Action requires its fixed reason and no labels")
        if (self.action == "ASSIGN") != (self.assignee_id is not None):
            raise ValueError("Only assignment accepts an assignee")
        if self.action in {"CORRECT", "ADJUDICATE"} and self.labels is None:
            raise ValueError("Complete decisions required")
        if self.action == "CORRECT" and self.reason_code not in {
            "CORRECTION",
            "INSUFFICIENT_EVIDENCE",
            "MULTIPLE_ISSUES",
        }:
            raise ValueError("Correction reason required")
        if self.action == "ADJUDICATE" and self.reason_code not in {
            "HUMAN_ADJUDICATION",
            "INSUFFICIENT_EVIDENCE",
        }:
            raise ValueError("Adjudication reason required")
        if self.action == "ESCALATE" and self.reason_code not in {
            "ESCALATE_CONFLICT",
            "INSUFFICIENT_EVIDENCE",
            "OUT_OF_SCOPE",
            "UNLABELABLE",
        }:
            raise ValueError("Escalation reason required")
        if (
            self.labels
            and self.labels.severity == "unknown"
            and self.reason_code != "INSUFFICIENT_EVIDENCE"
        ):
            raise ValueError("Unknown severity requires insufficient-evidence reason")
        return self


class FeedbackView(Metadata):
    feedback_id: str
    source_id: str
    source_record_ref: str | None
    text_redacted: str | None = None
    received_at: datetime | None
    domain: str | None
    agency: str | None
    channel: str | None
    processing_status: str
    is_synthetic: bool
    provenance_reference: str
    review_status: State
    assigned_actor_id: str | None
    current_labels: Labels | None
    version: int
    created_at: datetime
    updated_at: datetime
    processing_mode: Literal["DEMO_ONLY"] = "DEMO_ONLY"
    predictions: dict[str, "StoredPrediction"]


class StoredPrediction(TaskPrediction):
    prediction_id: str
    inference_mode: Literal["DEMO_ONLY"]
    requires_review: bool
    review_reasons: list[str]
    provenance: dict


class FeedbackPage(Metadata):
    items: list[FeedbackView]
    total: int
    limit: int
    offset: int


class AuditView(Metadata):
    review_event_id: str
    feedback_id: str
    prediction_id: str | None
    actor_reference: str
    actor_role: str
    action_type: str
    reason_code: str
    review_version: int | None
    attempted_version: int | None
    previous_labels: dict | None
    proposed_labels: dict | None
    adjudication_metadata: dict | None
    occurred_at: datetime
