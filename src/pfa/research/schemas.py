"""Privacy-minimized collection contracts. No identity, citizen text or free-text fields."""

from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from pfa.annotation.taxonomy import CHECKSUM, VERSION, Sentiment, Severity, Topic

Mode = Literal["SYNTHETIC_ENGINEERING_TEST", "HUMAN_FEASIBILITY_PILOT", "AUTHORIZED_RESEARCH"]
Condition = Literal["MANUAL_ONLY", "AI_ASSISTED"]
Order = Literal["AB", "BA"]
ID = Annotated[str, Field(pattern=r"^[a-zA-Z][a-zA-Z0-9_]{1,79}$")]
ParticipantID = Annotated[str, Field(pattern=r"^p_[a-f0-9]{16}$")]
SHA = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Status = Literal["COMPLETED", "INCOMPLETE", "ABANDONED"]


class Contract(BaseModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, hide_input_in_errors=True, allow_inf_nan=False
    )


class Labels(Contract):
    topic: Topic | None = None
    sentiment: Sentiment | None = None
    severity: Severity | Literal["unknown"] | None = None


class Case(Contract):
    case_id: ID
    group_id: ID
    source_id: ID
    source_version: ID
    mode: Mode
    role: Literal["DESCRIPTIVE", "EXPERIMENT_INDEPENDENT"]
    difficulty: Literal["easy", "medium", "hard"]
    basis: Literal["prediction", "reviewed", "adjudicated"]
    labels: Labels
    reference_gold_id: ID | None = None
    event_time: AwareDatetime | None = None
    agency: ID | None = None
    domain: ID | None = None
    label_provenance_ref: ID


class Participant(Contract):
    mode: Mode
    participant_id: ParticipantID
    consent_reference: ID
    eligibility_reference: ID


class ConsentEvent(Contract):
    mode: Mode
    consent_reference: ID
    participant_id: ParticipantID
    sequence: int = Field(ge=1)
    state: Literal["GRANTED", "WITHDRAWN", "DECLINED"]
    occurred_at: AwareDatetime
    evidence_reference: ID
    information_sheet_version: Literal["participant-info-1"]


class Assignment(Contract):
    experiment_id: ID
    assignment_id: ID
    participant_id: ParticipantID
    case_id: ID
    condition: Condition
    condition_order: Order
    period: Literal[1, 2]
    position: int = Field(ge=1)
    difficulty: Literal["easy", "medium", "hard"]


class Observation(Contract):
    mode: Mode
    experiment_id: ID
    assignment_id: ID
    participant_id: ParticipantID
    session_id: ID
    case_id: ID
    condition: Condition
    condition_order: Order
    model_version: ID | None = None
    model_versions: dict[Literal["topic", "sentiment", "severity"], ID] | None = None
    task_start_time: AwareDatetime
    task_end_time: AwareDatetime | None = None
    duration_seconds: float | None = Field(default=None, ge=0)
    completion_status: Status
    reviewer_topic: Topic | None = None
    reviewer_sentiment: Sentiment | None = None
    reviewer_severity: Severity | Literal["unknown"] | None = None
    reference_gold_id: ID | None = None
    ai_suggestion_shown: bool
    ai_suggestion: Labels | None = None
    ai_suggestion_accepted: bool | None = None
    override_flag: bool | None = None
    review_reason: Literal["CONFIRM", "CORRECT", "UNCERTAIN", "TIMEOUT", "WITHDRAWAL"]
    measurement_source: Literal["SYNTHETIC_FIXTURE", "INSTRUMENTED_CLOCK", "MANUAL_CLOCK"]
    consent_reference: ID
    protocol_version: Literal["research-protocol-1"]
    perceived_usefulness: int | None = Field(default=None, ge=1, le=5)
    perceived_workload: int | None = Field(default=None, ge=0, le=100)

    @model_validator(mode="after")
    def consistent(self):
        if (self.measurement_source == "SYNTHETIC_FIXTURE") != (
            self.mode == "SYNTHETIC_ENGINEERING_TEST"
        ):
            raise ValueError("Observation mode and measurement source mismatch")
        if self.task_end_time is None:
            if self.duration_seconds is not None or self.completion_status == "COMPLETED":
                raise ValueError("Measured end required for a completed duration")
        elif (
            self.duration_seconds is None
            or abs(
                (self.task_end_time - self.task_start_time).total_seconds() - self.duration_seconds
            )
            > 0.001
            or self.task_end_time < self.task_start_time
        ):
            raise ValueError("Duration must match recorded timezone-aware events")
        if self.completion_status == "COMPLETED" and (
            not self.reviewer_topic or not self.reviewer_sentiment or not self.reviewer_severity
        ):
            raise ValueError("Completed classification requires three responses")
        if self.condition == "MANUAL_ONLY" and any(
            value is not None and value is not False
            for value in (
                self.model_version,
                self.model_versions,
                self.ai_suggestion,
                self.ai_suggestion_accepted,
                self.override_flag,
                self.ai_suggestion_shown,
            )
        ):
            raise ValueError("Manual condition cannot contain AI assistance")
        if self.ai_suggestion_shown != (self.ai_suggestion is not None):
            raise ValueError("Shown suggestion and recorded content must agree")
        if self.ai_suggestion_shown and not self.model_version:
            raise ValueError("Model provenance required for displayed suggestions")
        if self.ai_suggestion_shown and (
            not self.model_versions
            or set(self.model_versions) != {"topic", "sentiment", "severity"}
            or self.model_versions["topic"] != self.model_version
        ):
            raise ValueError(
                "Three-task model provenance required; primary reference identifies topic"
            )
        if self.ai_suggestion_accepted is not None or self.override_flag is not None:
            if not self.ai_suggestion_shown or self.completion_status != "COMPLETED":
                raise ValueError("Acceptance requires completed assisted classification")
            same = self.ai_suggestion == Labels(
                topic=self.reviewer_topic,
                sentiment=self.reviewer_sentiment,
                severity=self.reviewer_severity,
            )
            if self.ai_suggestion_accepted != same or self.override_flag != (not same):
                raise ValueError("Acceptance and override must match recorded labels")
        return self


class Usability(Contract):
    mode: Mode
    participant_id: ParticipantID
    consent_reference: ID
    task_id: Literal["denominator", "missing_dates", "alert_support", "basis"]
    answer_code: Literal["A", "B", "C"] | None = None
    completion_status: Status
    task_start_time: AwareDatetime
    task_end_time: AwareDatetime | None = None
    duration_seconds: float | None = Field(default=None, ge=0)
    dashboard_version: ID

    @model_validator(mode="after")
    def clock(self):
        if self.completion_status == "COMPLETED" and (
            self.answer_code is None or self.task_end_time is None
        ):
            raise ValueError("Completed usability task requires answer and end event")
        if self.task_end_time is None:
            if self.duration_seconds is not None:
                raise ValueError("Unobserved end cannot have a duration")
        elif (
            self.duration_seconds is None
            or self.task_end_time < self.task_start_time
            or abs(
                (self.task_end_time - self.task_start_time).total_seconds() - self.duration_seconds
            )
            > 0.001
        ):
            raise ValueError("Invalid usability duration")
        return self


class Questionnaire(Contract):
    mode: Mode
    participant_id: ParticipantID
    consent_reference: ID
    collected_at: AwareDatetime
    perceived_usefulness: int | None = Field(default=None, ge=1, le=5)
    perceived_workload: int | None = Field(default=None, ge=0, le=100)


class GoldReference(Contract):
    mode: Mode
    reference_gold_id: ID
    case_id: ID
    pilot_id: ID
    adjudicated_sha256: SHA


class Deviation(Contract):
    mode: Mode
    experiment_id: ID
    assignment_id: ID | None = None
    code: Literal["MISSING", "WITHDRAWAL", "CLOCK_ERROR", "PROTOCOL_DEVIATION", "EXCLUDED"]
    evidence_reference: ID
    recorded_at: AwareDatetime


class Request(Contract):
    """Control metadata only; checked before the observations bundle is opened."""

    mode: Mode
    experiment_id: ID
    protocol_version: Literal["research-protocol-1"]
    protocol_sha256: SHA
    taxonomy_version: Literal[VERSION]
    taxonomy_checksum: Literal[CHECKSUM]
    source_id: ID
    dataset_version: ID | None = None
    payload_id: ID
    payload_sha256: SHA
    authorization_ref: ID | None = None
    collection_authorization_ref: ID | None = None
    rq2_evaluation_id: ID | None = None
    allocation_ref: ID | None = None
    includes_human_participants: bool = False
    ethics_authorization_ref: ID | None = None
    participant_access_ref: ID | None = None
    assistance_models: dict[Literal["topic", "sentiment", "severity"], ID] | None = None
    case_membership: list[ID] = Field(default_factory=list, max_length=5000)


class NumericalCheck(Contract):
    metric: Literal["total", "topic_count", "negative_share", "high_severity_share", "daily_count"]
    expected: float | None
    observed: float | None
    tolerance: float = Field(default=1e-9, ge=0, le=1e-6)
    reference: ID


class AlertWindow(Contract):
    window_id: ID
    eligible: bool
    triggered: bool
    reference_event: bool | None
    reference: ID | None

    @model_validator(mode="after")
    def reference_required(self):
        if self.reference_event is not None and self.reference is None:
            raise ValueError("Independently documented reference event required")
        return self


class Payload(Contract):
    cases: list[Case] = Field(default_factory=list, max_length=5000)
    participants: list[Participant] = Field(default_factory=list, max_length=1000)
    consent_events: list[ConsentEvent] = Field(default_factory=list, max_length=5000)
    observations: list[Observation] = Field(default_factory=list, max_length=20000)
    usability: list[Usability] = Field(default_factory=list, max_length=4000)
    questionnaires: list[Questionnaire] = Field(default_factory=list, max_length=1000)
    gold_references: list[GoldReference] = Field(default_factory=list, max_length=5000)
    deviations: list[Deviation] = Field(default_factory=list, max_length=20000)
    numerical_checks: list[NumericalCheck] = Field(default_factory=list, max_length=5000)
    alert_windows: list[AlertWindow] = Field(default_factory=list, max_length=5000)


TEMPLATES = {
    "participants": Participant,
    "assignments": Assignment,
    "manual_observations": Observation,
    "assisted_observations": Observation,
    "dashboard_tasks": Usability,
    "questionnaire": Questionnaire,
    "gold_references": GoldReference,
    "deviations": Deviation,
    "consent_events": ConsentEvent,
}
