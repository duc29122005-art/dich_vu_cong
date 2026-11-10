"""Bounded metadata-only SQL queries. Source rights precede reads; text is never selected."""

from dataclasses import dataclass, field
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import func, select

from pfa.annotation import pilot_store as store
from pfa.annotation.taxonomy import CHECKSUM, VERSION
from pfa.db.models import Feedback, ModelVersion, Prediction, ReviewEvent, SourceRegistry
from pfa.db.repository import Repository


@dataclass
class Row:
    event_time: datetime | None
    agency: str | None
    domain: str | None
    state: str
    human: dict[str, str | None]
    ai: dict[str, str | None] = field(default_factory=dict)
    reference_ai: dict[str, str | None] = field(default_factory=dict)
    models: dict[str, tuple[str, str]] = field(default_factory=dict)
    requires_review: bool = False


def read(repo: Repository, filters, config):
    # Each HTTP request gets a fresh session. Keep all metadata queries in one snapshot.
    if not repo.session.in_transaction():
        if repo.session.get_bind().dialect.name == "postgresql":
            repo.session.connection(
                execution_options={
                    "isolation_level": "REPEATABLE READ",
                    "postgresql_readonly": True,
                }
            )
        else:
            repo.session.connection().exec_driver_sql("BEGIN")
    sources = [filters.source_id] if filters.source_id else repo.actor.source_ids
    verified = set()
    for identity in sources:
        source = repo.permit(identity)
        cached = repo.session.get(SourceRegistry, identity)
        if cached and (
            cached.source_kind != "SYNTHETIC"
            or cached.registry_sha256 != store.digest(source.model_dump())
        ):
            raise HTTPException(403, "SOURCE_PROVENANCE_CHANGED")
        if cached:
            verified.add(identity)
    fields = [
        Feedback.feedback_id,
        Feedback.source_id,
        Feedback.is_synthetic,
        Feedback.received_at,
        Feedback.agency,
        Feedback.domain,
        Feedback.review_status,
        Feedback.current_topic,
        Feedback.current_sentiment,
        Feedback.current_severity,
    ]
    # ponytail: default ceiling is 5,000 metadata rows; use SQL aggregation above this limit.
    records = repo.session.execute(
        select(*fields)
        .where(Feedback.source_id.in_(sources))
        .order_by(Feedback.feedback_id)
        .limit(config.max_records + 1)
    ).all()
    if len(records) > config.max_records:
        raise HTTPException(503, "ANALYTICS_CAPACITY_EXCEEDED")
    result = {}
    for row in records:
        if not row.is_synthetic or row.source_id not in verified:
            raise HTTPException(403, "REAL_ANALYTICS_BLOCKED")
        result[row.feedback_id] = Row(
            row.received_at,
            row.agency,
            row.domain,
            row.review_status,
            dict(
                topic=row.current_topic,
                sentiment=row.current_sentiment,
                severity=row.current_severity,
            ),
        )
    if not result:
        return []
    ids = list(result)
    decisions = (
        select(
            ReviewEvent.feedback_id,
            ReviewEvent.occurred_at,
            func.row_number()
            .over(partition_by=ReviewEvent.feedback_id, order_by=ReviewEvent.review_version.desc())
            .label("position"),
        )
        .where(
            ReviewEvent.feedback_id.in_(ids),
            ReviewEvent.action_type.in_(["CONFIRM", "CORRECT", "ADJUDICATE"]),
        )
        .subquery()
    )
    for historical in (False, True):
        statement = (
            select(
                Prediction.feedback_id,
                Prediction.task,
                Prediction.predicted_label,
                Prediction.requires_review,
                Prediction.inference_mode,
                ModelVersion.family,
                ModelVersion.registry_reference,
                ModelVersion.taxonomy_version,
                ModelVersion.taxonomy_checksum,
                func.row_number()
                .over(
                    partition_by=[Prediction.feedback_id, Prediction.task],
                    order_by=[Prediction.created_at.desc(), Prediction.prediction_id.desc()],
                )
                .label("position"),
            )
            .join(ModelVersion, Prediction.model_version_id == ModelVersion.model_version_id)
            .where(Prediction.feedback_id.in_(ids))
        )
        if historical:
            statement = statement.join(
                decisions, decisions.c.feedback_id == Prediction.feedback_id
            ).where(decisions.c.position == 1, Prediction.created_at <= decisions.c.occurred_at)
        ranked = statement.subquery()
        for prediction in repo.session.execute(
            select(ranked).where(ranked.c.position == 1)
        ).mappings():
            if (
                prediction["inference_mode"] != "DEMO_ONLY"
                or prediction["taxonomy_version"] != VERSION
                or prediction["taxonomy_checksum"] != CHECKSUM
            ):
                raise HTTPException(403, "MODEL_OR_TAXONOMY_INCOMPATIBLE")
            row = result[prediction["feedback_id"]]
            target = row.reference_ai if historical else row.ai
            target[prediction["task"]] = prediction["predicted_label"]
            if not historical:
                row.models[prediction["task"]] = (
                    prediction["family"],
                    prediction["registry_reference"],
                )
                row.requires_review |= prediction["requires_review"]
    for row in result.values():
        row.requires_review |= any(
            row.ai.get(task) is None for task in ("topic", "sentiment", "severity")
        )
    return list(result.values())
