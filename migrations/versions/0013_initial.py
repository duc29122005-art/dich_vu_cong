"""Initial synthetic review persistence"""

import sqlalchemy as sa
from alembic import op

revision = "0013_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "model_version",
        sa.Column("model_version_id", sa.Uuid(), nullable=False),
        sa.Column("registry_reference", sa.String(length=100), nullable=False),
        sa.Column("descriptor_sha256", sa.String(length=64), nullable=False),
        sa.Column("task", sa.String(length=16), nullable=False),
        sa.Column("inference_mode", sa.String(length=24), nullable=False),
        sa.Column("family", sa.String(length=24), nullable=False),
        sa.Column("taxonomy_version", sa.String(length=16), nullable=False),
        sa.Column("taxonomy_checksum", sa.String(length=64), nullable=False),
        sa.Column("preprocessing_version", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("inference_mode = 'DEMO_ONLY'", name=op.f("ck_model_version_demo_only")),
        sa.CheckConstraint(
            "task IN ('topic','sentiment','severity')", name=op.f("ck_model_version_task")
        ),
        sa.PrimaryKeyConstraint("model_version_id", name=op.f("pk_model_version")),
        sa.UniqueConstraint(
            "model_version_id",
            "task",
            "inference_mode",
            name=op.f("uq_model_version_model_version_id"),
        ),
        sa.UniqueConstraint(
            "registry_reference",
            "task",
            "inference_mode",
            name=op.f("uq_model_version_registry_reference"),
        ),
    )
    op.create_table(
        "source_registry",
        sa.Column("source_id", sa.String(length=64), nullable=False),
        sa.Column("registry_sha256", sa.String(length=64), nullable=False),
        sa.Column("provenance_reference", sa.String(length=100), nullable=False),
        sa.Column("source_kind", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "source_kind = 'SYNTHETIC'", name=op.f("ck_source_registry_synthetic_only")
        ),
        sa.PrimaryKeyConstraint("source_id", name=op.f("pk_source_registry")),
    )
    op.create_table(
        "feedback",
        sa.Column("feedback_id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.String(length=64), nullable=False),
        sa.Column("source_record_ref", sa.String(length=100), nullable=True),
        sa.Column("text_redacted", sa.Text(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("domain", sa.String(length=100), nullable=True),
        sa.Column("agency", sa.String(length=100), nullable=True),
        sa.Column("channel", sa.String(length=64), nullable=True),
        sa.Column("processing_status", sa.String(length=24), nullable=False),
        sa.Column("is_synthetic", sa.Boolean(), nullable=False),
        sa.Column("provenance_reference", sa.String(length=100), nullable=False),
        sa.Column("review_status", sa.String(length=24), nullable=False),
        sa.Column("assigned_actor_id", sa.String(length=64), nullable=True),
        sa.Column("adjudicator_id", sa.String(length=64), nullable=True),
        sa.Column("current_topic", sa.String(length=32), nullable=True),
        sa.Column("current_sentiment", sa.String(length=16), nullable=True),
        sa.Column("current_severity", sa.String(length=16), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "current_sentiment IS NULL OR current_sentiment IN ('negative','neutral','positive')",
            name=op.f("ck_feedback_current_sentiment"),
        ),
        sa.CheckConstraint(
            "current_severity IS NULL OR current_severity IN ('low','medium','high','unknown')",
            name=op.f("ck_feedback_current_severity"),
        ),
        sa.CheckConstraint(
            "current_topic IS NULL OR current_topic IN ('delayed_processing','complex_procedure',"
            "'unclear_guidance','online_system_error','staff_attitude','fees',"
            "'unsatisfactory_result','other')",
            name=op.f("ck_feedback_current_topic"),
        ),
        sa.CheckConstraint(
            "processing_status IN ('AWAITING_REVIEW','HUMAN_REVIEWED')",
            name=op.f("ck_feedback_processing_status"),
        ),
        sa.CheckConstraint(
            "review_status IN ('PENDING_REVIEW','IN_REVIEW','REVIEWED',"
            "'NEEDS_ADJUDICATION','ADJUDICATED')",
            name=op.f("ck_feedback_review_status"),
        ),
        sa.CheckConstraint("is_synthetic = true", name=op.f("ck_feedback_synthetic_only")),
        sa.CheckConstraint(
            "length(text_redacted) BETWEEN 1 AND 20000", name=op.f("ck_feedback_text_length")
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_feedback_version")),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["source_registry.source_id"],
            name=op.f("fk_feedback_source_id_source_registry"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("feedback_id", name=op.f("pk_feedback")),
        sa.UniqueConstraint("source_id", "source_record_ref", name=op.f("uq_feedback_source_id")),
    )
    op.create_index(
        op.f("ix_feedback_assigned_actor_id"), "feedback", ["assigned_actor_id"], unique=False
    )
    op.create_index(op.f("ix_feedback_created_at"), "feedback", ["created_at"], unique=False)
    op.create_index(op.f("ix_feedback_review_status"), "feedback", ["review_status"], unique=False)
    op.create_index(op.f("ix_feedback_source_id"), "feedback", ["source_id"], unique=False)
    op.create_table(
        "prediction",
        sa.Column("prediction_id", sa.Uuid(), nullable=False),
        sa.Column("feedback_id", sa.Uuid(), nullable=False),
        sa.Column("model_version_id", sa.Uuid(), nullable=False),
        sa.Column("task", sa.String(length=16), nullable=False),
        sa.Column("predicted_label", sa.String(length=32), nullable=True),
        sa.Column("score", sa.Double(), nullable=True),
        sa.Column("score_type", sa.String(length=40), nullable=False),
        sa.Column("calibrated", sa.Boolean(), nullable=False),
        sa.Column("requires_review", sa.Boolean(), nullable=False),
        sa.Column("review_reasons", sa.JSON(), nullable=False),
        sa.Column("inference_mode", sa.String(length=24), nullable=False),
        sa.Column("provenance", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "inference_mode = 'DEMO_ONLY' AND calibrated = false "
            "AND score IS NULL AND requires_review = true",
            name=op.f("ck_prediction_demo_review"),
        ),
        sa.CheckConstraint(
            "predicted_label IS NULL OR (task = 'topic' AND predicted_label IN ("
            "'delayed_processing','complex_procedure','unclear_guidance','online_system_error',"
            "'staff_attitude','fees','unsatisfactory_result','other')) "
            "OR (task = 'sentiment' AND predicted_label IN ('negative','neutral','positive')) "
            "OR (task = 'severity' AND predicted_label IN ('low','medium','high'))",
            name=op.f("ck_prediction_labels"),
        ),
        sa.CheckConstraint(
            "score_type IN ('MOCK_NO_SCORE','UNAVAILABLE')", name=op.f("ck_prediction_score_type")
        ),
        sa.ForeignKeyConstraint(
            ["feedback_id"],
            ["feedback.feedback_id"],
            name=op.f("fk_prediction_feedback_id_feedback"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["model_version_id", "task", "inference_mode"],
            [
                "model_version.model_version_id",
                "model_version.task",
                "model_version.inference_mode",
            ],
            name=op.f("fk_prediction_model_version_id_model_version"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("prediction_id", name=op.f("pk_prediction")),
        sa.UniqueConstraint(
            "prediction_id", "feedback_id", name=op.f("uq_prediction_prediction_id")
        ),
    )
    op.create_index(op.f("ix_prediction_feedback_id"), "prediction", ["feedback_id"], unique=False)
    op.create_table(
        "review_event",
        sa.Column("review_event_id", sa.Uuid(), nullable=False),
        sa.Column("feedback_id", sa.Uuid(), nullable=False),
        sa.Column("prediction_id", sa.Uuid(), nullable=True),
        sa.Column("operation_id", sa.Uuid(), nullable=False),
        sa.Column("actor_reference", sa.String(length=64), nullable=False),
        sa.Column("actor_role", sa.String(length=16), nullable=False),
        sa.Column("action_type", sa.String(length=24), nullable=False),
        sa.Column("reason_code", sa.String(length=40), nullable=False),
        sa.Column("previous_labels", sa.JSON(), nullable=True),
        sa.Column("proposed_labels", sa.JSON(), nullable=True),
        sa.Column("review_version", sa.Integer(), nullable=True),
        sa.Column("attempted_version", sa.Integer(), nullable=True),
        sa.Column("adjudication_metadata", sa.JSON(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "action_type IN ('CREATE','CLAIM','ASSIGN','CONFIRM','CORRECT',"
            "'ESCALATE','ADJUDICATE','CONFLICT')",
            name=op.f("ck_review_event_action"),
        ),
        sa.CheckConstraint(
            "actor_role IN ('ADMIN','REVIEWER','ANALYST')", name=op.f("ck_review_event_role")
        ),
        sa.CheckConstraint(
            "review_version IS NULL OR review_version >= 1", name=op.f("ck_review_event_version")
        ),
        sa.ForeignKeyConstraint(
            ["feedback_id"],
            ["feedback.feedback_id"],
            name=op.f("fk_review_event_feedback_id_feedback"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["prediction_id", "feedback_id"],
            ["prediction.prediction_id", "prediction.feedback_id"],
            name=op.f("fk_review_event_prediction_id_prediction"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("review_event_id", name=op.f("pk_review_event")),
        sa.UniqueConstraint(
            "feedback_id", "review_version", name=op.f("uq_review_event_feedback_id")
        ),
        sa.UniqueConstraint("operation_id", name=op.f("uq_review_event_operation_id")),
    )
    op.create_index(
        op.f("ix_review_event_feedback_id"), "review_event", ["feedback_id"], unique=False
    )
    immutable = ("prediction", "review_event", "source_registry", "model_version")
    mutable = (
        "processing_status",
        "review_status",
        "assigned_actor_id",
        "adjudicator_id",
        "current_topic",
        "current_sentiment",
        "current_severity",
        "version",
        "updated_at",
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute("""CREATE FUNCTION pfa_immutable_history() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'immutable persistence history'; END; $$""")
        for table in immutable:
            op.execute(
                f"CREATE TRIGGER immutable_history BEFORE UPDATE OR DELETE ON {table} "
                "FOR EACH ROW EXECUTE FUNCTION pfa_immutable_history()"
            )
        fields = ",".join("'" + field + "'" for field in mutable)
        op.execute(f"""CREATE FUNCTION pfa_feedback_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'immutable feedback provenance'; END IF;
          IF (to_jsonb(OLD) - ARRAY[{fields}]) IS DISTINCT FROM
             (to_jsonb(NEW) - ARRAY[{fields}]) OR NEW.version <> OLD.version + 1
          THEN RAISE EXCEPTION 'immutable feedback provenance or stale version'; END IF;
          RETURN NEW;
        END; $$""")
        op.execute(
            "CREATE TRIGGER immutable_feedback BEFORE UPDATE OR DELETE ON feedback "
            "FOR EACH ROW EXECUTE FUNCTION pfa_feedback_guard()"
        )
    elif op.get_bind().dialect.name == "sqlite":
        for table in (*immutable, "feedback"):
            for action in ("DELETE", "UPDATE"):
                if table == "feedback" and action == "UPDATE":
                    continue
                op.execute(
                    f"CREATE TRIGGER immutable_{table}_{action} BEFORE {action} ON {table} "
                    "BEGIN SELECT RAISE(ABORT, 'immutable persistence history'); END"
                )
        columns = (
            "feedback_id",
            "source_id",
            "source_record_ref",
            "text_redacted",
            "received_at",
            "domain",
            "agency",
            "channel",
            "is_synthetic",
            "provenance_reference",
            "created_at",
        )
        conditions = " OR ".join(f"NEW.{field} IS NOT OLD.{field}" for field in columns)
        op.execute(
            "CREATE TRIGGER immutable_feedback_UPDATE BEFORE UPDATE ON feedback WHEN "
            f"{conditions} OR NEW.version <> OLD.version + 1 "
            "BEGIN SELECT RAISE(ABORT, 'immutable feedback provenance or stale version'); END"
        )
    else:
        raise RuntimeError("Unsupported database backend")


def downgrade():
    raise RuntimeError("Destructive downgrade disabled; reviewed restore required")
