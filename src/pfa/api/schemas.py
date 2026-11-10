"""Versioned public contracts. No text field exists in any response or error."""

import unicodedata
from typing import Literal

from pydantic import Field, field_validator, model_validator

from pfa.annotation.taxonomy import CHECKSUM, VERSION, Sentiment, Severity, Topic
from pfa.data.registry import Metadata

API_VERSION = "1.0.0"
SCHEMA_VERSION = "prediction-schema-1"
TASK_LABELS = {"topic": Topic, "sentiment": Sentiment, "severity": Severity}
Mode = Literal["APPROVED_MODEL", "DEMO_ONLY"]


class PredictionRequest(Metadata):
    text: str = Field(min_length=1, max_length=20000)
    request_id: str | None = Field(default=None, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")

    @field_validator("text")
    @classmethod
    def valid_text(cls, text):
        try:
            text.encode("utf-8")
        except UnicodeError:
            raise ValueError("Invalid Unicode") from None
        if not text.strip() or not any(c.isalnum() for c in text):
            raise ValueError("Nonempty linguistic content required")
        if any(
            (unicodedata.category(c) in {"Cc", "Cf", "Cs"} and c not in "\n\r\t")
            or ord(c) & 0xFFFF in {0xFFFE, 0xFFFF}
            or c == "\ufffd"
            for c in text
        ):
            raise ValueError("Unsupported Unicode content")
        return text


class BatchRequest(Metadata):
    items: list[PredictionRequest] = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def unique_ids(self):
        ids = [item.request_id for item in self.items if item.request_id is not None]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate request identifiers")
        return self


class TaskPrediction(Metadata):
    available: bool
    label: str | None = None
    score: float | None = Field(default=None, allow_inf_nan=False)
    score_type: Literal[
        "UNAVAILABLE",
        "MOCK_NO_SCORE",
        "CALIBRATED_PROBABILITY",
        "UNCALIBRATED_DECISION_SCORE",
        "UNCALIBRATED_LOGIT",
    ] = "UNAVAILABLE"
    calibrated: bool = False
    model_version: str | None = None

    @model_validator(mode="after")
    def consistent(self):
        if not self.available and (
            self.label is not None
            or self.score is not None
            or self.calibrated
            or self.score_type != "UNAVAILABLE"
        ):
            raise ValueError("Unavailable task cannot carry predictions")
        if self.available and (self.label is None or self.model_version is None):
            raise ValueError("Available task requires label and version")
        if self.calibrated != (self.score_type == "CALIBRATED_PROBABILITY"):
            raise ValueError("Score semantics inconsistent")
        if self.calibrated and (self.score is None or not 0 <= self.score <= 1):
            raise ValueError("Invalid calibrated score")
        if self.score_type in {"MOCK_NO_SCORE", "UNAVAILABLE"} and self.score is not None:
            raise ValueError("Unavailable confidence must be null")
        return self


class Predictions(Metadata):
    topic: TaskPrediction
    sentiment: TaskPrediction
    severity: TaskPrediction

    @model_validator(mode="after")
    def labels(self):
        from typing import get_args

        for task, annotation in TASK_LABELS.items():
            prediction = getattr(self, task)
            if prediction.available and prediction.label not in get_args(annotation):
                raise ValueError("Prediction label not in frozen taxonomy")
        return self


class Provenance(Metadata):
    api_version: Literal[API_VERSION] = API_VERSION
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    taxonomy_checksum: Literal[CHECKSUM] = CHECKSUM
    preprocessing_version: Literal["conservative-1"] = "conservative-1"
    provider: Literal["MOCK_FIXTURE", "APPROVED_LOCAL_REGISTRY"]
    administrative_decision_allowed: Literal[False] = False
    input_persisted: Literal[False] = False


class PredictionResponse(Metadata):
    request_id: str
    processing_mode: Mode
    model_status: Literal["DEMO_ONLY", "APPROVED_MODEL", "PARTIAL", "INPUT_REVIEW_REQUIRED"]
    taxonomy_version: Literal[VERSION] = VERSION
    predictions: Predictions
    requires_review: bool
    review_reasons: list[str]
    provenance: Provenance
    warnings: list[str]

    @model_validator(mode="after")
    def demo_is_review_only(self):
        if self.processing_mode == "DEMO_ONLY" and (
            not self.requires_review
            or any(
                p.calibrated or p.score is not None
                for p in (
                    self.predictions.topic,
                    self.predictions.sentiment,
                    self.predictions.severity,
                )
            )
        ):
            raise ValueError("Demo predictions require review and cannot contain confidence")
        return self


class ErrorDetail(Metadata):
    code: str
    message: str
    request_id: str


class ErrorResponse(Metadata):
    error: ErrorDetail


class BatchItem(Metadata):
    request_id: str
    result: PredictionResponse | None = None
    error: ErrorDetail | None = None

    @model_validator(mode="after")
    def exactly_one(self):
        if (self.result is None) == (self.error is None):
            raise ValueError("Exactly one result or error required")
        return self


class BatchResponse(Metadata):
    processing_mode: Mode
    items: list[BatchItem]


class TaskStatus(Metadata):
    available: bool
    family: str | None = None
    model_version: str | None = None
    taxonomy_version: Literal[VERSION] = VERSION
    deployment_status: Literal["DEMO_ONLY", "APPROVED_MODEL", "UNAVAILABLE"]
    blocker: str | None = None


class ModelStatus(Metadata):
    processing_mode: Mode
    ready: bool
    tasks: dict[Literal["topic", "sentiment", "severity"], TaskStatus]


class Readiness(Metadata):
    status: Literal["READY", "UNAVAILABLE"]
    processing_mode: Mode
    prediction_ready: bool
    blockers: list[str]


class Liveness(Metadata):
    status: Literal["ALIVE"] = "ALIVE"


class VersionResponse(Metadata):
    api_version: Literal[API_VERSION] = API_VERSION
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    package_version: Literal["0.1.0"] = "0.1.0"
    processing_mode: Mode
