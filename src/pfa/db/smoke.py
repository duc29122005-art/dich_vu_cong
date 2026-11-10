"""Invented fixtures only; SQLite verifies application behavior, not PostgreSQL."""

import io
import json
import logging
import secrets
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from pfa.annotation import pilot_store as store
from pfa.api.app_factory import create_app
from pfa.api.settings import ApiSettings
from pfa.db.models import Feedback, Prediction, ReviewEvent
from pfa.db.session import Database, DbSettings, migrate


@contextmanager
def environment(project_root: Path, *, postgres_url=None, schema=None, observability=False):
    """Internal isolated fixture capability. No CLI switch can enable real intake."""
    with TemporaryDirectory(prefix="pfa-db-synthetic-") as temporary:
        root = Path(temporary)
        (root / "configs").mkdir()
        for name in ("taxonomy_v1.yaml", "dataset_sources.yaml"):
            (root / "configs" / name).write_bytes((project_root / "configs" / name).read_bytes())
        store.private_directory(root / "data/private")
        credentials = []
        for role in ("ADMIN", "REVIEWER", "ANALYST"):
            credentials.append(
                {
                    "actor_id": "synthetic_" + role.lower(),
                    "role": role,
                    "source_ids": ["synthetic_demo"],
                    "can_view_text": role != "ANALYST",
                    "can_adjudicate": False,
                    "key": secrets.token_urlsafe(48),
                }
            )
        settings = ApiSettings(
            mode="DEMO_ONLY",
            environment="test",
            api_key=None,
            principals=SecretStr(json.dumps(credentials)),
            observability_enabled=observability,
        )
        url = postgres_url or "sqlite:///" + (root / "data/private/smoke.sqlite").as_posix()
        with store.synthetic_session(root):
            database = Database(
                root, DbSettings(mode="SYNTHETIC", url=SecretStr(url)), schema=schema
            )
            try:
                migrate(database)
                app = create_app(settings, root=root, database_factory=lambda: database)
                with TestClient(
                    app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000)
                ) as client:
                    assert app.state.database is database
                    headers = {c["role"]: {"X-API-Key": c["key"]} for c in credentials}
                    yield client, database, headers, root
                assert not app.state.service.provider.loaded
            finally:
                database.close()


def create(client, headers, fixture_id=0, **extra):
    return client.post(
        "/api/v1/feedback",
        headers=headers,
        json={
            "fixture_id": fixture_id,
            "operation_id": str(uuid4()),
            **extra,
        },
    )


def change(client, headers, identity, action, version, reason, **extra):
    return client.patch(
        f"/api/v1/reviews/{identity}",
        headers=headers,
        json={
            "operation_id": str(uuid4()),
            "expected_version": version,
            "action": action,
            "reason_code": reason,
            **extra,
        },
    )


def exercise(client, database, headers):
    """Same workflow runs on SQLite and explicitly configured isolated PostgreSQL."""
    assert client.post("/api/v1/feedback", json={}).status_code == 401
    assert create(client, headers["ANALYST"]).status_code == 403
    response = create(client, headers["ADMIN"])
    assert response.status_code == 201, response.text
    row = response.json()
    identity = row["feedback_id"]
    original = row["predictions"]
    assert row["received_at"] is None and row["is_synthetic"]
    assert len(original) == 3
    assert client.get("/api/v1/reviews/queue", headers=headers["REVIEWER"]).json()["total"] == 1
    assert change(client, headers["REVIEWER"], identity, "CLAIM", 1, "CLAIM").status_code == 200
    labels = {"topic": "fees", "sentiment": "negative", "severity": "high"}
    corrected = change(
        client, headers["REVIEWER"], identity, "CORRECT", 2, "CORRECTION", labels=labels
    )
    assert corrected.status_code == 200, corrected.text
    assert corrected.json()["current_labels"] == labels
    assert corrected.json()["predictions"] == original
    assert (
        change(
            client, headers["REVIEWER"], identity, "CORRECT", 2, "CORRECTION", labels=labels
        ).status_code
        == 409
    )
    history = client.get(f"/api/v1/reviews/{identity}/history", headers=headers["ADMIN"]).json()
    assert [e["action_type"] for e in history] == ["CREATE", "CLAIM", "CORRECT", "CONFLICT"]
    assert (
        client.get(f"/api/v1/reviews/{identity}/history", headers=headers["ANALYST"]).status_code
        == 403
    )
    assert (
        client.get("/api/v1/feedback?include_text=true", headers=headers["ANALYST"]).status_code
        == 403
    )
    with database.sessions() as session:
        feedback = session.scalar(select(Feedback))
        assert len(feedback.predictions) == 3 and len(feedback.events) == 4
        assert feedback.created_at.tzinfo is not None
        assert all(not p.calibrated and p.score is None for p in feedback.predictions)
        for table in (Prediction.__tablename__, ReviewEvent.__tablename__):
            try:
                session.execute(text(f"DELETE FROM {table}"))
                session.commit()
            except DBAPIError:
                session.rollback()
            else:
                raise AssertionError("Immutable history deletion accepted")
    return {
        "feedback_count": 1,
        "prediction_count": 3,
        "audit_event_count": 4,
        "stale_write_http": 409,
        "analyst_write_http": 403,
        "unauthenticated_http": 401,
    }


def smoke(project_root: Path):
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    logger = logging.getLogger("pfa.api")
    logger.addHandler(handler)
    try:
        with environment(project_root) as (client, database, headers, root):
            result = exercise(client, database, headers)
            with database.sessions() as session:
                submitted = session.scalar(select(Feedback.text_redacted))
            assert submitted not in stream.getvalue()
            assert all(h["X-API-Key"] not in stream.getvalue() for h in headers.values())
        return {
            "status": "DB_SMOKE_PASS_SYNTHETIC",
            "backend": "SQLite",
            **result,
            "POSTGRES_INTEGRATION": "NOT_VERIFIED",
            "REAL_DATA_PERSISTENCE": "BLOCKED",
            "test_holdout_accessed": False,
            "temporary_storage_cleaned": not root.exists(),
        }
    finally:
        logger.removeHandler(handler)
        handler.close()
