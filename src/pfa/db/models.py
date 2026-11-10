"""Synthetic review state with immutable prediction and audit history."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    event,
    inspect,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship
from sqlalchemy.types import TypeDecorator


def now():
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator):
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None:
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("Timezone-aware timestamp required")
            return value.astimezone(UTC)
        return None

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return (value.replace(tzinfo=UTC) if value.tzinfo is None else value).astimezone(UTC)


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(table_name)s_%(column_0_name)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


class SourceRegistry(Base):
    __tablename__ = "source_registry"
    source_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    registry_sha256: Mapped[str] = mapped_column(String(64))
    provenance_reference: Mapped[str] = mapped_column(String(100))
    source_kind: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)
    __table_args__ = (CheckConstraint("source_kind = 'SYNTHETIC'", name="synthetic_only"),)


class ModelVersion(Base):
    __tablename__ = "model_version"
    model_version_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    registry_reference: Mapped[str] = mapped_column(String(100))
    descriptor_sha256: Mapped[str] = mapped_column(String(64))
    task: Mapped[str] = mapped_column(String(16))
    inference_mode: Mapped[str] = mapped_column(String(24))
    family: Mapped[str] = mapped_column(String(24))
    taxonomy_version: Mapped[str] = mapped_column(String(16))
    taxonomy_checksum: Mapped[str] = mapped_column(String(64))
    preprocessing_version: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)
    __table_args__ = (
        UniqueConstraint("registry_reference", "task", "inference_mode"),
        UniqueConstraint("model_version_id", "task", "inference_mode"),
        CheckConstraint("task IN ('topic','sentiment','severity')", name="task"),
        CheckConstraint("inference_mode = 'DEMO_ONLY'", name="demo_only"),
    )


class Feedback(Base):
    __tablename__ = "feedback"
    feedback_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    source_id: Mapped[str] = mapped_column(
        ForeignKey("source_registry.source_id", ondelete="RESTRICT"), index=True
    )
    source_record_ref: Mapped[str | None] = mapped_column(String(100))
    text_redacted: Mapped[str] = mapped_column(Text)
    received_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    domain: Mapped[str | None] = mapped_column(String(100))
    agency: Mapped[str | None] = mapped_column(String(100))
    channel: Mapped[str | None] = mapped_column(String(64))
    processing_status: Mapped[str] = mapped_column(String(24), default="AWAITING_REVIEW")
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=True)
    provenance_reference: Mapped[str] = mapped_column(String(100))
    review_status: Mapped[str] = mapped_column(String(24), default="PENDING_REVIEW", index=True)
    assigned_actor_id: Mapped[str | None] = mapped_column(String(64), index=True)
    adjudicator_id: Mapped[str | None] = mapped_column(String(64))
    current_topic: Mapped[str | None] = mapped_column(String(32))
    current_sentiment: Mapped[str | None] = mapped_column(String(16))
    current_severity: Mapped[str | None] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now, index=True)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)
    version: Mapped[int] = mapped_column(Integer, default=1)
    predictions: Mapped[list["Prediction"]] = relationship(back_populates="feedback")
    events: Mapped[list["ReviewEvent"]] = relationship(back_populates="feedback")
    __table_args__ = (
        UniqueConstraint("source_id", "source_record_ref"),
        CheckConstraint("is_synthetic = true", name="synthetic_only"),
        CheckConstraint("version >= 1", name="version"),
        CheckConstraint("length(text_redacted) BETWEEN 1 AND 20000", name="text_length"),
        CheckConstraint(
            "review_status IN ('PENDING_REVIEW','IN_REVIEW','REVIEWED',"
            "'NEEDS_ADJUDICATION','ADJUDICATED')",
            name="review_status",
        ),
        CheckConstraint(
            "processing_status IN ('AWAITING_REVIEW','HUMAN_REVIEWED')", name="processing_status"
        ),
        CheckConstraint(
            "current_topic IS NULL OR current_topic IN ('delayed_processing','complex_procedure',"
            "'unclear_guidance','online_system_error','staff_attitude','fees',"
            "'unsatisfactory_result','other')",
            name="current_topic",
        ),
        CheckConstraint(
            "current_sentiment IS NULL OR current_sentiment IN ('negative','neutral','positive')",
            name="current_sentiment",
        ),
        CheckConstraint(
            "current_severity IS NULL OR current_severity IN ('low','medium','high','unknown')",
            name="current_severity",
        ),
    )


class Prediction(Base):
    __tablename__ = "prediction"
    prediction_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    feedback_id: Mapped[UUID] = mapped_column(
        ForeignKey("feedback.feedback_id", ondelete="RESTRICT"), index=True
    )
    model_version_id: Mapped[UUID] = mapped_column(Uuid)
    task: Mapped[str] = mapped_column(String(16))
    predicted_label: Mapped[str | None] = mapped_column(String(32))
    score: Mapped[float | None]
    score_type: Mapped[str] = mapped_column(String(40))
    calibrated: Mapped[bool] = mapped_column(Boolean)
    requires_review: Mapped[bool] = mapped_column(Boolean)
    review_reasons: Mapped[list] = mapped_column(JSON)
    inference_mode: Mapped[str] = mapped_column(String(24))
    provenance: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)
    feedback: Mapped[Feedback] = relationship(back_populates="predictions")
    __table_args__ = (
        ForeignKeyConstraint(
            ["model_version_id", "task", "inference_mode"],
            [
                "model_version.model_version_id",
                "model_version.task",
                "model_version.inference_mode",
            ],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("prediction_id", "feedback_id"),
        CheckConstraint(
            "inference_mode = 'DEMO_ONLY' AND calibrated = false "
            "AND score IS NULL AND requires_review = true",
            name="demo_review",
        ),
        CheckConstraint("score_type IN ('MOCK_NO_SCORE','UNAVAILABLE')", name="score_type"),
        CheckConstraint(
            "predicted_label IS NULL OR (task = 'topic' AND predicted_label IN ("
            "'delayed_processing','complex_procedure','unclear_guidance','online_system_error',"
            "'staff_attitude','fees','unsatisfactory_result','other')) "
            "OR (task = 'sentiment' AND predicted_label IN ('negative','neutral','positive')) "
            "OR (task = 'severity' AND predicted_label IN ('low','medium','high'))",
            name="labels",
        ),
    )


class ReviewEvent(Base):
    __tablename__ = "review_event"
    review_event_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    feedback_id: Mapped[UUID] = mapped_column(
        ForeignKey("feedback.feedback_id", ondelete="RESTRICT"), index=True
    )
    prediction_id: Mapped[UUID | None] = mapped_column(Uuid)
    operation_id: Mapped[UUID] = mapped_column(Uuid, unique=True)
    actor_reference: Mapped[str] = mapped_column(String(64))
    actor_role: Mapped[str] = mapped_column(String(16))
    action_type: Mapped[str] = mapped_column(String(24))
    reason_code: Mapped[str] = mapped_column(String(40))
    previous_labels: Mapped[dict | None] = mapped_column(JSON)
    proposed_labels: Mapped[dict | None] = mapped_column(JSON)
    review_version: Mapped[int | None] = mapped_column(Integer)
    attempted_version: Mapped[int | None] = mapped_column(Integer)
    adjudication_metadata: Mapped[dict | None] = mapped_column(JSON)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)
    feedback: Mapped[Feedback] = relationship(back_populates="events")
    __table_args__ = (
        UniqueConstraint("feedback_id", "review_version"),
        ForeignKeyConstraint(
            ["prediction_id", "feedback_id"],
            ["prediction.prediction_id", "prediction.feedback_id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("actor_role IN ('ADMIN','REVIEWER','ANALYST')", name="role"),
        CheckConstraint(
            "action_type IN ('CREATE','CLAIM','ASSIGN','CONFIRM','CORRECT',"
            "'ESCALATE','ADJUDICATE','CONFLICT')",
            name="action",
        ),
        CheckConstraint("review_version IS NULL OR review_version >= 1", name="version"),
    )


IMMUTABLE = (Prediction, ReviewEvent, SourceRegistry, ModelVersion)
MUTABLE_FEEDBACK = {
    "processing_status",
    "review_status",
    "assigned_actor_id",
    "adjudicator_id",
    "current_topic",
    "current_sentiment",
    "current_severity",
    "version",
    "updated_at",
}


@event.listens_for(Session, "before_flush")
def protect_history(session, context, instances):
    for item in session.dirty | session.deleted:
        if isinstance(item, IMMUTABLE):
            raise ValueError("Immutable persistence history")
        if isinstance(item, Feedback) and (
            item in session.deleted
            or any(
                column.key not in MUTABLE_FEEDBACK
                and inspect(item).attrs[column.key].history.has_changes()
                for column in Feedback.__table__.columns
            )
        ):
            raise ValueError("Immutable feedback provenance")
