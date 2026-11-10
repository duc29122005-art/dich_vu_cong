"""STEP13 offline regressions. Synthetic identities do not establish independent validation."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
from sqlalchemy import delete, func, inspect, select, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError, OperationalError, StatementError

from pfa.api.app_factory import create_app
from pfa.api.identity import Principal, parse_credentials
from pfa.api.settings import ApiSettings
from pfa.cli import main
from pfa.data.official_io import IngestionBlocked
from pfa.db import contracts
from pfa.db.models import Feedback, ModelVersion, Prediction, ReviewEvent, SourceRegistry
from pfa.db.repository import Repository
from pfa.db.session import HEAD, Database, DbSettings, migrate
from pfa.db.smoke import change, create, environment, smoke

ROOT = Path(__file__).resolve().parents[1]
LABELS = {"topic": "fees", "sentiment": "negative", "severity": "high"}


@pytest.fixture
def system():
    with environment(ROOT) as value:
        yield value


def new(system, index=0):
    client, _, headers, _ = system
    response = create(client, headers["ADMIN"], index)
    assert response.status_code == 201, response.text
    return response.json()


def test_smoke():
    result = smoke(ROOT)
    assert result["status"] == "DB_SMOKE_PASS_SYNTHETIC"
    assert result["temporary_storage_cleaned"]
    assert result["POSTGRES_INTEGRATION"] == "NOT_VERIFIED"


def test_entities_and_migration(system):
    _, db, _, _ = system
    new(system)
    migrate(db)  # Already at head: no destructive recreation.
    db.validate()
    inspector = inspect(db.engine)
    assert set(inspector.get_table_names()) == set(Feedback.metadata.tables) | {"alembic_version"}
    with db.sessions() as session:
        row = session.scalar(select(Feedback))
        assert row.received_at is None and row.created_at.utcoffset().total_seconds() == 0
        assert len(row.predictions) == 3 and len(row.events) == 1
        assert session.scalar(select(func.count()).select_from(ModelVersion)) == 3
        assert session.scalar(select(func.count()).select_from(SourceRegistry)) == 1
        assert session.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == HEAD


@pytest.mark.parametrize("table", [Prediction, ReviewEvent, SourceRegistry, ModelVersion])
@pytest.mark.parametrize("operation", ["orm", "update", "delete"])
def test_history_immutable(system, table, operation):
    _, db, _, _ = system
    new(system)
    with db.sessions() as session:
        row = session.scalar(select(table))
        with pytest.raises((ValueError, DBAPIError)):
            if operation == "orm":
                session.delete(row)
                session.flush()
            elif operation == "update":
                column = next(iter(table.__table__.primary_key))
                session.execute(update(table).values({column.key: getattr(row, column.key)}))
            else:
                session.execute(delete(table))
        session.rollback()
        assert session.scalar(select(table)) is not None


@pytest.mark.parametrize(
    "values",
    [
        {"is_synthetic": False},
        {"source_id": "unauthorized"},
        {"text_redacted": "replacement"},
        {"version": 9},
    ],
)
def test_feedback_provenance_immutable(system, values):
    _, db, _, _ = system
    new(system)
    with db.sessions() as session, pytest.raises(DBAPIError):
        session.execute(update(Feedback).values(**values))


def test_foreign_key_and_label_constraints(system):
    _, db, _, _ = system
    new(system)
    with db.sessions() as session:
        existing = session.scalar(select(Prediction))
        values = {c.key: getattr(existing, c.key) for c in Prediction.__table__.columns}
        for invalid in (
            {"feedback_id": uuid4()},
            {"predicted_label": "invalid"},
            {"task": "sentiment" if existing.task == "topic" else "topic"},
            {"calibrated": True},
            {"score": 0.9},
            {"inference_mode": "APPROVED_MODEL"},
        ):
            with pytest.raises(IntegrityError):
                session.add(Prediction(**{**values, "prediction_id": uuid4(), **invalid}))
                session.flush()
            session.rollback()


@pytest.mark.parametrize("role", ["REVIEWER", "ANALYST"])
def test_write_roles(system, role):
    client, _, headers, _ = system
    assert create(client, headers[role]).status_code == 403


def test_authentication_and_no_role_header(system):
    client, _, headers, _ = system
    assert client.get("/api/v1/feedback").status_code == 401
    assert client.get("/api/v1/feedback", headers={"X-API-Key": "invalid"}).status_code == 401
    forged = {**headers["ANALYST"], "X-Role": "ADMIN"}
    assert create(client, forged).status_code == 403


@pytest.mark.parametrize(
    "extra,code",
    [
        ({"text_redacted": "invented"}, 422),
        ({"text": "secret@example.invalid"}, 422),
        ({"is_synthetic": False}, 403),
        ({"source_id": "public_service_official"}, 403),
        ({"role": "ADMIN"}, 422),
        ({"fixture_id": 120}, 422),
        ({"fixture_id": -1}, 422),
        ({"fixture_id": "0"}, 422),
    ],
)
def test_intake_boundary(system, extra, code):
    client, _, headers, _ = system
    result = create(client, headers["ADMIN"], **extra)
    assert result.status_code == code
    assert "secret@example.invalid" not in result.text


def test_source_gate_even_for_admin(system):
    _, db, _, root = system
    actor = Principal(
        actor_id="synthetic_admin",
        role="ADMIN",
        can_view_text=True,
        source_ids=["public_service_official"],
    )
    with db.sessions() as session, pytest.raises(HTTPException) as caught:
        Repository(root, session, actor).permit("public_service_official")
    assert caught.value.status_code == 403


def test_privacy_screen_blocks_fixture(system, monkeypatch):
    from pfa.data.privacy import Screening
    from pfa.db import repository

    client, db, headers, _ = system
    monkeypatch.setattr(
        repository, "audit_screen", lambda _: Screening("hidden", {"phone": 1}, False)
    )
    assert create(client, headers["ADMIN"]).status_code == 422
    with db.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Feedback)) == 0


def test_correct_separate_history_and_unknown(system):
    client, db, headers, _ = system
    row = new(system)
    identity = row["feedback_id"]
    assert change(client, headers["REVIEWER"], identity, "CLAIM", 1, "CLAIM").status_code == 200
    labels = {**LABELS, "severity": "unknown"}
    result = change(
        client, headers["REVIEWER"], identity, "CORRECT", 2, "INSUFFICIENT_EVIDENCE", labels=labels
    )
    assert result.status_code == 200 and result.json()["version"] == 3
    assert result.json()["current_labels"]["severity"] == "unknown"
    assert result.json()["predictions"] == row["predictions"]
    with db.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Prediction)) == 3


def test_confirm_and_invalid_transition(system):
    client, _, headers, _ = system
    identity = new(system)["feedback_id"]
    assert (
        change(client, headers["REVIEWER"], identity, "CONFIRM", 1, "CONFIRM_MODEL").status_code
        == 403
    )
    assert change(client, headers["REVIEWER"], identity, "CLAIM", 1, "CLAIM").status_code == 200
    assert change(client, headers["REVIEWER"], identity, "CLAIM", 2, "CLAIM").status_code == 409
    result = change(client, headers["REVIEWER"], identity, "CONFIRM", 2, "CONFIRM_MODEL")
    assert result.status_code == 200 and result.json()["review_status"] == "REVIEWED"


def test_assignment_and_adjudication_authorization(system):
    client, _, headers, _ = system
    identity = new(system)["feedback_id"]
    assert change(client, headers["ADMIN"], identity, "CLAIM", 1, "CLAIM").status_code == 403
    assert (
        change(
            client,
            headers["ADMIN"],
            identity,
            "ASSIGN",
            1,
            "ASSIGN",
            assignee_id="synthetic_analyst",
        ).status_code
        == 403
    )
    assert (
        change(
            client,
            headers["ADMIN"],
            identity,
            "ASSIGN",
            1,
            "ASSIGN",
            assignee_id="synthetic_reviewer",
        ).status_code
        == 200
    )
    assert (
        change(
            client, headers["REVIEWER"], identity, "ESCALATE", 2, "ESCALATE_CONFLICT"
        ).status_code
        == 200
    )
    assert (
        change(
            client,
            headers["REVIEWER"],
            identity,
            "ADJUDICATE",
            3,
            "HUMAN_ADJUDICATION",
            labels=LABELS,
        ).status_code
        == 403
    )


def test_designated_synthetic_adjudication(system):
    client, db, headers, root = system
    identity = new(system)["feedback_id"]
    change(client, headers["REVIEWER"], identity, "CLAIM", 1, "CLAIM")
    change(client, headers["REVIEWER"], identity, "ESCALATE", 2, "ESCALATE_CONFLICT")
    actor = Principal(
        actor_id="synthetic_adjudicator",
        role="REVIEWER",
        source_ids=["synthetic_demo"],
        can_view_text=True,
        can_adjudicate=True,
    )
    with db.sessions() as session:
        success, result = Repository(root, session, actor).review(
            UUID(identity),
            contracts.Review(
                operation_id=uuid4(),
                expected_version=3,
                action="ADJUDICATE",
                reason_code="HUMAN_ADJUDICATION",
                labels=contracts.Labels(**LABELS),
            ),
            [],
        )
        assert success and result.review_status == "ADJUDICATED"
    history = client.get(f"/api/v1/reviews/{identity}/history", headers=headers["ADMIN"]).json()
    assert history[-1]["adjudication_metadata"]["independent_human_validation"] is False


def test_stale_and_duplicate_operations(system):
    client, _, headers, _ = system
    identity = new(system)["feedback_id"]
    payload = {
        "operation_id": str(uuid4()),
        "expected_version": 1,
        "action": "CLAIM",
        "reason_code": "CLAIM",
    }
    assert (
        client.patch(
            f"/api/v1/reviews/{identity}", headers=headers["REVIEWER"], json=payload
        ).status_code
        == 200
    )
    assert (
        client.patch(
            f"/api/v1/reviews/{identity}", headers=headers["REVIEWER"], json=payload
        ).status_code
        == 409
    )
    assert (
        change(
            client, headers["REVIEWER"], identity, "CORRECT", 1, "CORRECTION", labels=LABELS
        ).status_code
        == 409
    )
    history = client.get(f"/api/v1/reviews/{identity}/history", headers=headers["ADMIN"]).json()
    assert len(history) == 3 and history[-1]["reason_code"] == "STALE_VERSION"


def test_concurrent_claims(system, monkeypatch):
    client, _, headers, _ = system
    identity = new(system)["feedback_id"]
    original, barrier = Repository.get, Barrier(2)

    def both_read(self, identifier, include_text=False):
        row = original(self, identifier, include_text)
        if include_text:
            barrier.wait(timeout=10)
        return row

    monkeypatch.setattr(Repository, "get", both_read)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _: (
                    change(client, headers["REVIEWER"], identity, "CLAIM", 1, "CLAIM").status_code
                ),
                range(2),
            )
        )
    assert sorted(results) == [200, 409]
    assert (
        client.get(f"/api/v1/feedback/{identity}", headers=headers["ADMIN"]).json()["version"] == 2
    )


def test_review_transaction_rollback(system, monkeypatch):
    client, db, headers, _ = system
    identity = new(system)["feedback_id"]

    def fail(*args, **kwargs):
        raise HTTPException(503, "SYNTHETIC_AUDIT_FAILURE")

    monkeypatch.setattr(Repository, "add_event", fail)
    assert change(client, headers["REVIEWER"], identity, "CLAIM", 1, "CLAIM").status_code == 503
    with db.sessions() as session:
        row = session.get(Feedback, UUID(identity))
        assert row.version == 1 and row.review_status == "PENDING_REVIEW"
        assert len(row.events) == 1


def test_pages_and_text_permissions(system):
    client, _, headers, _ = system
    row = new(system)
    new(system, 1)
    page = client.get("/api/v1/feedback?limit=1&offset=1", headers=headers["ANALYST"]).json()
    assert page["total"] == 2 and len(page["items"]) == 1
    assert page["items"][0]["text_redacted"] is None
    assert (
        client.get("/api/v1/feedback?include_text=true", headers=headers["ANALYST"]).status_code
        == 403
    )
    assert client.get("/api/v1/feedback?include_text=true", headers=headers["REVIEWER"]).json()[
        "items"
    ][0]["text_redacted"]
    assert (
        client.get("/api/v1/feedback?status=REVIEWED", headers=headers["ANALYST"]).json()["total"]
        == 0
    )
    assert client.get("/api/v1/feedback?limit=0", headers=headers["ADMIN"]).status_code == 422
    assert client.get("/api/v1/reviews/queue", headers=headers["ANALYST"]).status_code == 403
    assert (
        client.get(
            f"/api/v1/reviews/{row['feedback_id']}/history", headers=headers["REVIEWER"]
        ).status_code
        == 403
    )


def test_predict_does_not_persist(system):
    client, db, headers, _ = system
    assert (
        client.post(
            "/api/v1/predict", headers=headers["ADMIN"], json={"text": "SYNTHETIC: Hồ sơ giả định."}
        ).status_code
        == 200
    )
    with db.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Feedback)) == 0


def test_smoke_cannot_read_research_or_holdout(monkeypatch):
    from pfa.data import corpus

    def forbidden(*args, **kwargs):
        pytest.fail("Database smoke accessed governed research records")

    monkeypatch.setattr(corpus, "evaluation_data", forbidden)
    monkeypatch.setattr(corpus, "model_selection", forbidden)
    assert smoke(ROOT)["status"] == "DB_SMOKE_PASS_SYNTHETIC"


def test_history_guards_required(system):
    _, db, _, _ = system
    with db.engine.begin() as connection:
        connection.execute(text("DROP TRIGGER immutable_prediction_UPDATE"))
    with pytest.raises(IngestionBlocked, match="guards"):
        db.validate()


def test_legacy_key_grants_no_persistence_role(system):
    _, db, _, root = system
    settings = ApiSettings(
        mode="DEMO_ONLY", environment="test", api_key=SecretStr("x" * 48), principals=None
    )
    app = create_app(settings, root=root, database_factory=lambda: db)
    with TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50001)) as legacy:
        headers = {"X-API-Key": "x" * 48}
        assert legacy.get("/api/v1/models/status", headers=headers).status_code == 200
        assert legacy.get("/api/v1/feedback", headers=headers).status_code == 403
        assert create(legacy, headers).status_code == 403


def test_disabled_database_preserves_original_openapi(monkeypatch):
    monkeypatch.setenv("PFA_DB_MODE", "DISABLED")
    app = create_app(ApiSettings(api_key=None, principals=None), root=ROOT)
    assert len(app.openapi()["paths"]) == 7


def test_synthetic_registry_not_mutated(system):
    client, _, headers, root = system
    before = (root / "configs/dataset_sources.yaml").read_bytes()
    row = new(system)
    assert row["processing_mode"] == "DEMO_ONLY"
    assert all(
        p["inference_mode"] == "DEMO_ONLY"
        and p["requires_review"]
        and p["provenance"]["input_persisted"]
        for p in row["predictions"].values()
    )
    assert not (root / "data/private/model_registry").exists()
    assert (root / "configs/dataset_sources.yaml").read_bytes() == before
    assert (
        client.get("/api/v1/models/status", headers=headers["ADMIN"]).json()["processing_mode"]
        == "DEMO_ONLY"
    )


def test_safe_logs_errors_and_malformed_requests(system, caplog):
    client, _, headers, _ = system
    caplog.set_level("INFO", logger="pfa.api")
    secret = "never-log-this@example.invalid"
    response = create(client, headers["ADMIN"], text=secret)
    assert response.status_code == 422 and secret not in response.text
    assert (
        client.patch(
            "/api/v1/reviews/invalid",
            headers={**headers["ADMIN"], "Content-Type": "application/json"},
            content=b'{"a":1,"a":2}',
        ).status_code
        == 400
    )
    assert secret not in caplog.text
    assert all(h["X-API-Key"] not in caplog.text for h in headers.values())


@pytest.mark.parametrize("locked,expected", [(True, 409), (False, 503)])
def test_database_failure_errors_are_safe(system, monkeypatch, locked, expected):
    import sqlite3

    client, _, headers, _ = system
    sensitive = "never_print_database_credential"
    original = sqlite3.OperationalError(sensitive)
    if locked:
        original.sqlite_errorcode = sqlite3.SQLITE_BUSY

    def failure(*args, **kwargs):
        raise OperationalError(sensitive, {"secret": sensitive}, original)

    monkeypatch.setattr(Repository, "page", failure)
    result = client.get("/api/v1/feedback", headers=headers["ADMIN"])
    assert result.status_code == expected and sensitive not in result.text


def test_startup_never_migrates(system, monkeypatch):
    client, db, headers, root = system
    new(system)
    db.close()
    monkeypatch.setattr("pfa.db.session.migrate", lambda _: pytest.fail("Startup performs DDL"))
    app = create_app(client.app.state.settings, root=root, database_factory=lambda: db)
    with TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50001)) as restarted:
        assert restarted.get("/api/v1/feedback", headers=headers["ADMIN"]).json()["total"] == 1


def test_unmigrated_startup_fails_closed(system):
    client, db, headers, root = system
    with db.engine.begin() as connection:
        connection.execute(text("UPDATE alembic_version SET version_num='invalid'"))
    app = create_app(client.app.state.settings, root=root, database_factory=lambda: db)
    with TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50001)) as isolated:
        assert isolated.get("/health/live").status_code == 200
        assert isolated.get("/api/v1/feedback", headers=headers["ADMIN"]).status_code == 503


def test_naive_timestamp_rejected(system):
    _, db, _, _ = system
    new(system)
    with db.sessions() as session, pytest.raises(StatementError):
        session.execute(update(Feedback).values(updated_at=datetime(2025, 1, 1), version=2))


def test_invalid_principals():
    for value in ("{}", "[]", '[{"key":"short"}]'):
        with pytest.raises(ValueError):
            parse_credentials(SecretStr(value))


def test_configuration_errors_hide_credentials():
    marker = "never_print_secret"
    with pytest.raises(ValidationError) as caught:
        ApiSettings(principals=marker)
    assert marker not in str(caught.value)


def test_db_url_private_and_sqlite_capability(tmp_path):
    secret = "postgresql+psycopg://example:never_print@127.0.0.1/pfa_test"
    assert "never_print" not in repr(DbSettings(mode="SYNTHETIC", url=SecretStr(secret)))
    with pytest.raises(IngestionBlocked):
        Database(tmp_path, DbSettings(mode="SYNTHETIC", url=SecretStr("sqlite:///outside.db")))


@pytest.mark.parametrize(
    "action,code", [("status", 3), ("check-migrations", 3), ("smoke-postgres", 4)]
)
def test_cli_blocked(monkeypatch, capsys, action, code):
    monkeypatch.delenv("PFA_DB_MODE", raising=False)
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    assert main(["db", action]) == code
    assert "BLOCKED" in capsys.readouterr().out if action != "smoke-postgres" else True


def test_db_cli_smoke(capsys):
    assert main(["db", "smoke"]) == 0
    assert "DB_SMOKE_PASS_SYNTHETIC" in capsys.readouterr().out


@pytest.mark.parametrize(
    "values",
    [
        {
            "action": "CORRECT",
            "reason_code": "CORRECTION",
            "labels": {**LABELS, "severity": "unknown"},
        },
        {"action": "CLAIM", "reason_code": "CORRECTION"},
        {"action": "ASSIGN", "reason_code": "ASSIGN"},
        {"action": "ADJUDICATE", "reason_code": "HUMAN_ADJUDICATION"},
    ],
)
def test_strict_workflow_requests(values):
    with pytest.raises(ValidationError):
        contracts.Review.model_validate(
            {"operation_id": str(uuid4()), "expected_version": 1, **values}
        )
