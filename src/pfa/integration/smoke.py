"""Compose existing services in disposable storage; never touches private project data."""

import io
import logging
from uuid import UUID

from pydantic import SecretStr
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from dashboard.api_client import Client, Settings
from dashboard.charts import distribution_rows, trend_rows
from pfa.analytics.fixtures import seed
from pfa.analytics.schemas import NOTICE, Report
from pfa.api.schemas import PredictionResponse
from pfa.data import corpus, official
from pfa.data.official_io import IngestionBlocked
from pfa.data.registry import load_registry
from pfa.db.models import Feedback, Prediction, ReviewEvent
from pfa.db.smoke import change, create, environment
from pfa.integration.fixtures import generate
from pfa.research.reporting import status as research_status


def workflow(client, database, headers, root):
    """Runs unchanged on SQLite and inside STEP13's owned PostgreSQL schema."""
    rows, provenance = generate()
    registry = load_registry(root / "configs/dataset_sources.yaml")
    assert registry.source("synthetic_demo").dataset_role == "SYNTHETIC"
    with database.sessions() as session:
        before = session.scalar(select(func.count()).select_from(Feedback))
    predicted = client.post(
        "/api/v1/predict", headers=headers["REVIEWER"], json={"text": rows[0].content}
    )
    assert predicted.status_code == 200
    result = PredictionResponse.model_validate(predicted.json())
    assert result.processing_mode == "DEMO_ONLY" and result.requires_review
    assert result.provenance.input_persisted is False
    assert result.provenance.administrative_decision_allowed is False
    for task in ("topic", "sentiment", "severity"):
        value = getattr(result.predictions, task)
        assert value.score is None and not value.calibrated
    batch = client.post(
        "/api/v1/predict/batch",
        headers=headers["ADMIN"],
        json={"items": [{"text": r.content} for r in rows[:8]]},
    )
    assert batch.status_code == 200
    with database.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Feedback)) == before
    created = [create(client, headers["ADMIN"], fixture_id=i) for i in range(8)]
    assert all(r.status_code == 201 for r in created)
    item = created[0].json()
    identity, original = item["feedback_id"], item["predictions"]
    assert item["is_synthetic"] and item["received_at"] is None
    assert item["provenance_reference"] == "SYNTHETIC_SOFTWARE_FIXTURE_V1"
    queue = client.get(
        "/api/v1/reviews/queue", headers=headers["REVIEWER"], params={"limit": 100}
    ).json()
    assert queue["total"] >= 8
    assert change(client, headers["REVIEWER"], identity, "CLAIM", 1, "CLAIM").status_code == 200
    labels = {"topic": "fees", "sentiment": "negative", "severity": "high"}
    correction = change(
        client, headers["REVIEWER"], identity, "CORRECT", 2, "CORRECTION", labels=labels
    )
    assert correction.status_code == 200
    assert correction.json()["predictions"] == original
    assert change(client, headers["REVIEWER"], identity, "CLAIM", 1, "CLAIM").status_code == 409
    assert change(client, headers["ANALYST"], identity, "CLAIM", 3, "CLAIM").status_code == 403
    history = client.get(f"/api/v1/reviews/{identity}/history", headers=headers["ADMIN"]).json()
    assert [e["action_type"] for e in history] == ["CREATE", "CLAIM", "CORRECT", "CONFLICT"]
    with database.sessions() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(Prediction)
                .where(Prediction.feedback_id == UUID(identity))
            )
            == 3
        )
        for table in (Prediction.__tablename__, ReviewEvent.__tablename__):
            try:
                session.execute(text(f"DELETE FROM {table}"))
                session.commit()
            except DBAPIError:
                session.rollback()
            else:
                raise AssertionError("Immutable history protection failed")
    dashboard = Client(Settings(api_key=SecretStr(headers["ANALYST"]["X-API-Key"])), http=client)
    reports = {
        name: dashboard.fetch(name, {}) for name in ("summary", "topics", "trends", "alerts")
    }
    assert reports["summary"].total == before + 8
    assert all(r.notice == NOTICE and r.processing_mode == "DEMO_ONLY" for r in reports.values())
    charts = distribution_rows(reports["topics"].distributions["topic"])
    series = trend_rows(reports["trends"].buckets)
    serialized = "".join(r.model_dump_json() for r in reports.values()) + str(charts) + str(series)
    assert "feedback_id" not in serialized and rows[0].content not in serialized
    assert client.get("/api/v1/analytics/summary").status_code == 401
    assert (
        client.get(
            "/api/v1/analytics/summary",
            headers=headers["ADMIN"],
            params={"source_id": "public_service_official"},
        ).status_code
        == 403
    )
    for action in (
        lambda: corpus.model_selection(root, registry, "nonexistent", "test"),
        lambda: official.authorize(root, registry, "public_service_official", "invented"),
    ):
        try:
            action()
        except (IngestionBlocked, ValueError):
            pass
        else:
            raise AssertionError("Research or permission gate bypassed")
    return {
        "fixture_records": len(rows),
        "invalid_rejected": provenance["invalid_rejected"],
        "fixture_provenance_sha256": provenance["normalized_sha256"],
        "prediction_nonpersistent": True,
        "explicit_feedback_created": 8,
        "analytics_total": reports["summary"].total,
        "immutable_predictions": True,
        "append_only_audit": True,
        "stale_write_http": 409,
        "analyst_write_http": 403,
        "dashboard_contract": "VERIFIED",
        "test_holdout": "PROTECTED",
    }


def smoke(project_root):
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    logger = logging.getLogger("pfa.api")
    previous = logger.level
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    try:
        readiness = research_status(project_root)
        assert readiness["RQ1"] == "BLOCKED_ON_RESEARCH_DATA"
        assert readiness["RQ4"] == "BLOCKED_ON_EXPERIMENT"
        with environment(project_root, observability=True) as (client, database, headers, root):
            (root / "configs/analytics_v1.yaml").write_bytes(
                (project_root / "configs/analytics_v1.yaml").read_bytes()
            )
            seed(database)
            result = workflow(client, database, headers, root)
            summary = Report.model_validate(
                client.get("/api/v1/analytics/summary", headers=headers["ANALYST"]).json()
            )
            assert summary.total == 428
            assert summary.metrics["negative_share"].numerator == 250
            assert summary.metrics["high_severity_share"].numerator == 147
            assert summary.metrics["missing_event_time_in_filter_scope"].numerator == 28
            series = Report.model_validate(
                client.get(
                    "/api/v1/analytics/trends",
                    params={"start": "2025-01-06", "end": "2025-01-13"},
                    headers=headers["ANALYST"],
                ).json()
            )
            assert [b.count for b in series.buckets] == [40] * 7 + [120]
            small = client.get(
                "/api/v1/analytics/summary",
                headers=headers["ANALYST"],
                params={"basis": "reviewed", "review_status": "REVIEWED", "severity": "high"},
            )
            assert small.status_code == 200
            operations = client.get("/api/v1/operations/status", headers=headers["ADMIN"])
            assert operations.status_code == 200
            assert operations.json()["database_health"] == "AVAILABLE"
            with database.sessions() as session:
                texts = session.scalars(select(Feedback.text_redacted)).all()
            logged = stream.getvalue()
            assert all(t not in logged for t in texts)
            assert all(h["X-API-Key"] not in logged for h in headers.values())
        assert not root.exists()
        return {
            "status": "INTEGRATION_SMOKE_PASS_SYNTHETIC",
            "processing_mode": "DEMO_ONLY",
            "backend": "SQLite",
            **result,
            "known_negative_count": 250,
            "known_high_severity_count": 147,
            "research_readiness": "BLOCKED",
            "raw_text_logged": False,
            "temporary_storage_cleaned": True,
            "POSTGRES_INTEGRATION": "NOT_VERIFIED",
        }
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous)
        handler.close()


def smoke_postgres(project_root):
    from pfa.db.postgres import smoke as postgres_smoke

    temporary_root = None

    def composed(client, database, headers, root):
        nonlocal temporary_root
        temporary_root = root
        (root / "configs/analytics_v1.yaml").write_bytes(
            (project_root / "configs/analytics_v1.yaml").read_bytes()
        )
        return workflow(client, database, headers, root)

    result, code = postgres_smoke(project_root, workflow=composed)
    if code == 0:
        if temporary_root is None or temporary_root.exists():
            raise ValueError("Temporary PostgreSQL fixture storage cleanup failed")
        result["status"] = "INTEGRATION_POSTGRES_PASS_SYNTHETIC"
        result["temporary_storage_cleaned"] = True
        result["owned_schema_cleanup"] = "VERIFIED"
    return result, code
