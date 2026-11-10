"""Invented offline integration/security cases; no citizen records or final test labels."""

import json
import logging
import secrets
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import func, select

from pfa.api.app_factory import create_app
from pfa.api.identity import Credential
from pfa.api.settings import ApiSettings
from pfa.cli import main
from pfa.data import corpus
from pfa.data.official_io import IngestionBlocked
from pfa.db.models import Feedback
from pfa.db.smoke import change, create, environment
from pfa.integration import commands, contracts, security_checks
from pfa.integration.fixtures import generate
from pfa.integration.observability import Metrics
from pfa.integration.smoke import smoke, smoke_postgres

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def system():
    with environment(ROOT, observability=True) as resources:
        (resources[3] / "configs/analytics_v1.yaml").write_bytes(
            (ROOT / "configs/analytics_v1.yaml").read_bytes()
        )
        yield resources


def test_complete_workflow(monkeypatch):
    def protected(*args, **kwargs):
        raise AssertionError("Protected evaluation path must never be entered")

    monkeypatch.setattr(corpus, "evaluation_data", protected)
    result = smoke(ROOT)
    assert result["status"] == "INTEGRATION_SMOKE_PASS_SYNTHETIC"
    assert result["analytics_total"] == 428
    assert result["known_negative_count"] == 250
    assert result["known_high_severity_count"] == 147
    assert result["prediction_nonpersistent"] and result["temporary_storage_cleaned"]
    assert result["test_holdout"] == "PROTECTED"
    assert result["research_readiness"] == "BLOCKED"


def test_fixtures_reproducible_and_labelled():
    rows, provenance = generate()
    again, repeated = generate()
    assert provenance == repeated and rows == again
    assert provenance["dataset_type"] == "SYNTHETIC" and not provenance["human_gold"]
    assert len({r.labels["topic"] for r in rows}) == 8
    assert sum(r.event_time is None for r in rows) == 12
    assert any(r.labels["severity"] is None for r in rows)
    assert rows[0].content == rows[1].content
    assert provenance["privacy_fixture_screened"] and provenance["invalid_rejected"] == 4


def test_cleanup_even_when_integration_fails(monkeypatch):
    from pfa.integration import smoke as module

    roots = []

    def failure(client, database, headers, root):
        roots.append(root)
        raise RuntimeError("synthetic failure")

    monkeypatch.setattr(module, "workflow", failure)
    result, code = commands.run(ROOT, "smoke")
    assert code == 2 and result["submitted_values_withheld"]
    assert roots and all(not p.exists() for p in roots)


@pytest.mark.parametrize(
    "body,expected",
    [
        ({}, 422),
        ({"text": ""}, 422),
        ({"text": "   "}, 422),
        ({"text": "\ud800"}, 422),
        ({"text": "x" * 4001}, 422),
        ({"text": "synthetic", "role": "ADMIN"}, 422),
        ({"text": "synthetic", "model_path": "../../private"}, 422),
        ({"text": "synthetic", "request_id": "../secret"}, 422),
    ],
)
def test_input_boundaries(system, body, expected, caplog):
    client, _, headers, _ = system
    caplog.set_level(logging.INFO, logger="pfa.api")
    response = client.post(
        "/api/v1/predict",
        headers={**headers["REVIEWER"], "Content-Type": "application/json"},
        content=json.dumps(body),
    )
    assert response.status_code == expected
    assert "model_path" not in response.text and "../secret" not in caplog.text
    assert headers["REVIEWER"]["X-API-Key"] not in caplog.text


@pytest.mark.parametrize("body", [b"{", b"\xff", b'{"text":"a","text":"b"}', b'{"text":NaN}'])
def test_malformed_json(system, body):
    client, _, headers, _ = system
    response = client.post(
        "/api/v1/predict",
        content=body,
        headers={**headers["ADMIN"], "Content-Type": "application/json"},
    )
    assert response.status_code == 400 and "MALFORMED_JSON" in response.text


def test_bounds_and_injection_nonpersistence(system):
    client, database, headers, _ = system
    text = "SYNTHETIC: '; DROP TABLE feedback; -- thủ tục giả lập"
    response = client.post("/api/v1/predict", headers=headers["REVIEWER"], json={"text": text})
    assert response.status_code == 200 and text not in response.text
    oversized = client.post(
        "/api/v1/predict/batch", headers=headers["REVIEWER"], json={"items": [{"text": text}] * 17}
    )
    assert oversized.status_code == 422
    body = client.post(
        "/api/v1/predict",
        headers={**headers["ADMIN"], "Content-Type": "application/json"},
        content=b"x" * 262145,
    )
    assert body.status_code == 413
    with database.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Feedback)) == 0


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/models/status",
        "/api/v1/analytics/summary",
        "/api/v1/reviews/queue",
        "/api/v1/operations/status",
    ],
)
def test_missing_invalid_and_revoked_credentials(system, path):
    client, _, headers, _ = system
    assert client.get(path).status_code == 401
    assert client.get(path, headers={"X-API-Key": secrets.token_urlsafe(48)}).status_code == 401
    key = headers["ADMIN"]
    client.app.state.settings.credentials[:] = [
        c for c in client.app.state.settings.credentials if c.role != "ADMIN"
    ]
    assert client.get(path, headers=key).status_code == 401


@pytest.mark.parametrize("role", ["ADMIN", "REVIEWER", "ANALYST"])
def test_rbac_and_role_escalation(system, role):
    client, _, headers, _ = system
    response = create(client, {**headers[role], "X-Role": "ADMIN"})
    assert response.status_code == (201 if role == "ADMIN" else 403)
    metrics = client.get("/api/v1/operations/status", headers=headers[role])
    assert metrics.status_code == (200 if role == "ADMIN" else 403)


def test_cross_source_idor_and_assigned_reviewer(system):
    client, _, headers, _ = system
    row = create(client, headers["ADMIN"]).json()
    identity = row["feedback_id"]
    outsider = Credential(
        actor_id="synthetic_outsider",
        role="REVIEWER",
        source_ids=["unapproved_source"],
        key=SecretStr(secrets.token_urlsafe(48)),
    )
    other = Credential(
        actor_id="synthetic_second",
        role="REVIEWER",
        source_ids=["synthetic_demo"],
        key=SecretStr(secrets.token_urlsafe(48)),
    )
    client.app.state.settings.credentials.extend([outsider, other])
    denied = {"X-API-Key": outsider.key.get_secret_value()}
    assert client.get(f"/api/v1/feedback/{identity}", headers=denied).status_code == 403
    assert change(client, denied, identity, "CLAIM", 1, "CLAIM").status_code == 403
    assert (
        client.get(
            "/api/v1/analytics/summary", headers=denied, params={"source_id": "synthetic_demo"}
        ).status_code
        == 403
    )
    assert change(client, headers["REVIEWER"], identity, "CLAIM", 1, "CLAIM").status_code == 200
    assert change(
        client, {"X-API-Key": other.key.get_secret_value()}, identity, "CONFIRM", 2, "CONFIRM_MODEL"
    ).status_code in {403, 409}
    invalid = client.get("/api/v1/feedback/not-a-uuid", headers=headers["ADMIN"])
    assert invalid.status_code == 422


@pytest.mark.parametrize(
    "extra",
    [
        {"source_id": "public_service_official"},
        {"is_synthetic": False},
        {"role": "ADMIN"},
        {"text_redacted": "invented"},
        {"is_gold": True},
    ],
)
def test_no_permission_or_research_elevation(system, extra):
    client, _, headers, _ = system
    assert create(client, headers["ADMIN"], **extra).status_code in {403, 422}


def test_small_cells_privacy_and_no_prediction_history_mutation(system, caplog):
    client, _, headers, root = system
    caplog.set_level(logging.INFO, logger="pfa.api")
    (root / "configs/analytics_v1.yaml").write_bytes(
        (ROOT / "configs/analytics_v1.yaml").read_bytes()
    )
    row = create(client, headers["ADMIN"]).json()
    for endpoint in ("summary", "topics", "trends", "alerts"):
        result = client.get("/api/v1/analytics/" + endpoint, headers=headers["ANALYST"])
        assert result.status_code == 200
        assert result.json()["status"] == "SUPPRESSED" and result.json()["total"] is None
        assert row["feedback_id"] not in result.text and "text_redacted" not in result.text
    history = f"/api/v1/reviews/{row['feedback_id']}/history"
    assert client.delete(history, headers=headers["ADMIN"]).status_code == 405
    assert client.patch(history, json={}, headers=headers["ADMIN"]).status_code == 405
    assert all(h["X-API-Key"] not in caplog.text for h in headers.values())
    assert row["feedback_id"] not in caplog.text


def test_operational_counters_concurrent():
    metrics = Metrics()
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: metrics.record(503, 2), range(100)))
    assert metrics.snapshot() == {
        "requests": 100,
        "request_errors": 100,
        "processing_failures": 100,
        "mean_latency_ms": 2,
        "max_latency_ms": 2,
    }


def test_operational_status_and_failure(system, monkeypatch):
    client, database, headers, _ = system
    create(client, headers["ADMIN"])
    client.get("/api/v1/models/status")
    payload = client.get("/api/v1/operations/status", headers=headers["ADMIN"]).json()
    assert payload["processing_mode"] == "DEMO_ONLY" and payload["model_loaded"]
    assert payload["review_queue_size_in_authorized_sources"] == 1
    assert payload["counters"]["request_errors"] >= 1
    assert "url" not in json.dumps(payload)
    monkeypatch.setattr(
        database, "sessions", lambda: (_ for _ in ()).throw(RuntimeError("private"))
    )
    unavailable = client.get("/api/v1/operations/status", headers=headers["ADMIN"])
    assert unavailable.status_code == 200
    assert unavailable.json()["database_health"] == "UNAVAILABLE"
    assert "private" not in unavailable.text


def test_missing_approved_model_and_credentials():
    settings = ApiSettings(
        mode="APPROVED_MODEL",
        environment="test",
        api_key=None,
        principals=None,
        observability_enabled=True,
    )
    with TestClient(create_app(settings, root=ROOT)) as client:
        assert client.get("/health/live").status_code == 200
        assert client.get("/health/ready").status_code == 503
        assert client.post("/api/v1/predict", json={"text": "invented"}).status_code == 503
    assert (
        "/api/v1/operations/status" not in create_app(ApiSettings(), root=ROOT).openapi()["paths"]
    )


def test_holdout_denied_before_any_artifact_read(monkeypatch, tmp_path):
    monkeypatch.setattr(
        corpus, "_authorized_manifest", lambda *args: pytest.fail("Dataset artifacts accessed")
    )
    with pytest.raises(IngestionBlocked):
        corpus.model_selection(tmp_path, None, "unknown", "test")


def test_workflow_all_missing_dates(system):
    from pfa.integration.smoke import workflow

    result = workflow(*system)
    assert result["analytics_total"] == 8 and result["prediction_nonpersistent"]


def test_no_startup_migrations(system, monkeypatch):
    from pfa.db import session

    client, database, _, root = system
    monkeypatch.setattr(session, "migrate", lambda *a: pytest.fail("Startup DDL forbidden"))
    app = create_app(client.app.state.settings, root=root, database_factory=lambda: database)
    with TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000)):
        assert app.state.database is database


def test_processing_failure_metrics_and_safe_error(system, monkeypatch, caplog):
    client, _, headers, _ = system
    caplog.set_level(logging.INFO, logger="pfa.api")
    with monkeypatch.context() as patch:
        patch.setattr(
            client.app.state.service.provider,
            "check",
            lambda: (_ for _ in ()).throw(RuntimeError("synthetic-private-marker")),
        )
        response = client.get("/api/v1/models/status", headers=headers["ADMIN"])
    assert response.status_code == 500
    assert "synthetic-private-marker" not in response.text + caplog.text
    result = client.get("/api/v1/operations/status", headers=headers["ADMIN"]).json()
    assert result["counters"]["processing_failures"] >= 1


def test_performance_arithmetic(monkeypatch):
    from pfa.integration import performance

    ticks = iter([0, 1, 2, 4, 5, 8])
    monkeypatch.setattr(performance, "perf_counter", lambda: next(ticks))
    result = performance.measure(lambda: None, samples=3, items=2)
    assert result["median_ms"] == 2000
    assert result["items_per_second"] == 1 and result["samples"] == 3


@pytest.mark.parametrize(
    "filename,content,rule",
    [
        ("model.pt", b"invented", "PRIVATE_ARTIFACT"),
        (".env", b"invented", "PRIVATE_ARTIFACT"),
        ("raw.csv", b"invented", "PRIVATE_ARTIFACT"),
        ("sample.txt", b"\xff", "BINARY_UNSCANNED"),
        ("sample.txt", ("-----BEGIN " + "PRIVATE KEY-----").encode(), "PRIVATE_KEY"),
        ("sample.txt", ("ghp_" + "A" * 40).encode(), "SERVICE_TOKEN"),
        ("sample.txt", ("postgresql://user:" + "invented@localhost/db").encode(), "CREDENTIAL_URL"),
        ("sample.txt", ('password="' + "invented-long-value" + '"').encode(), "LITERAL_SECRET"),
        ("sample.txt", ("invented-person@" + "unreserved-domain.vn").encode(), "SENSITIVE_SAMPLE"),
    ],
)
def test_scanner_redacts_values(tmp_path, filename, content, rule):
    (tmp_path / filename).write_bytes(content)
    found = security_checks.inspect_file(tmp_path, filename)
    assert any(f["rule"] == rule for f in found)
    assert content.decode("utf-8", errors="replace") not in json.dumps(found)


def test_scanner_rejects_populated_template(tmp_path):
    path = tmp_path / "templates/research/participants.csv"
    path.parent.mkdir(parents=True)
    path.write_text("header\nunauthorized\n")
    assert (
        security_checks.inspect_file(tmp_path, path.relative_to(tmp_path).as_posix())[0]["rule"]
        == "POPULATED_RESEARCH_TEMPLATE"
    )


def test_scanner_reserved_placeholder_and_path_escape(tmp_path):
    (tmp_path / "example.txt").write_text("Invented contact: fixture@example.invalid")
    assert security_checks.inspect_file(tmp_path, "example.txt") == []
    with pytest.raises((ValueError, IngestionBlocked)):
        security_checks.inspect_file(tmp_path, "../outside")


def test_scanner_exclusion_changes_fail_closed(tmp_path, monkeypatch):
    target = tmp_path / "example.txt"
    target.write_text('password="' + "invented-long-value" + '"')
    finding = security_checks.inspect_file(tmp_path, "example.txt")[0]
    config = contracts.load(ROOT).model_dump()
    config["reviewed_exclusions"] = [{k: finding[k] for k in ("path", "rule", "line_sha256")}]
    config["reviewed_exclusions"][0]["reason"] = "Reviewed invented test placeholder only."
    (tmp_path / "configs").mkdir()
    (tmp_path / "configs/integration_v1.yaml").write_text(json.dumps(config))
    monkeypatch.setattr(
        security_checks.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=0, stdout=b"example.txt\0"),
    )
    assert security_checks.scan(tmp_path)["status"] == "SECURITY_SCAN_PASS"
    target.write_text('password="' + "different-long-value" + '"')
    assert security_checks.scan(tmp_path)["status"] == "SECURITY_SCAN_FAIL"


def test_pinned_synthetic_csv_cannot_hide_new_data(tmp_path):
    path = tmp_path / "tests/fixtures/public_service_feedback_synthetic.csv"
    path.parent.mkdir(parents=True)
    path.write_text("arbitrary data\n")
    assert (
        security_checks.inspect_file(tmp_path, path.relative_to(tmp_path).as_posix())[0]["rule"]
        == "SYNTHETIC_FIXTURE_TAMPERED"
    )


def test_repository_scan_and_config():
    result = security_checks.scan(ROOT)
    assert result["status"] == "SECURITY_SCAN_PASS", result["findings"]
    assert result["candidate_files"] >= result["tracked_files"]
    assert contracts.load(ROOT).source_id == "synthetic_demo"


@pytest.mark.parametrize("action", ["smoke-postgres", "dependency-check"])
def test_unavailable_commands(monkeypatch, capsys, action):
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    monkeypatch.setattr(security_checks.shutil, "which", lambda _: None)
    assert main(["integration", action]) == 4
    assert "NOT_" in capsys.readouterr().out


@pytest.mark.parametrize(
    "url",
    [
        "sqlite:///arbitrary.db",
        "postgresql://localhost/pfa_test",
        "postgresql+psycopg://remote/pfa_test",
        "postgresql+psycopg://localhost/production",
    ],
)
def test_unsafe_postgres_targets_never_connect(monkeypatch, url):
    from pfa.db import postgres

    monkeypatch.setenv("TEST_DATABASE_URL", url)
    monkeypatch.setattr(postgres, "create_engine", lambda *a, **k: pytest.fail("Unsafe connection"))
    result, code = smoke_postgres(ROOT)
    assert code == 2 and result["POSTGRES_INTEGRATION"] == "NOT_VERIFIED"


@pytest.mark.parametrize(
    "action,status",
    [("smoke", "INTEGRATION_SMOKE_PASS_SYNTHETIC"), ("security-check", "SECURITY_SCAN_PASS")],
)
def test_cli_success(action, status, capsys):
    assert main(["integration", action]) == 0
    assert status in capsys.readouterr().out


def test_dependency_tool_failure_and_advisories(monkeypatch):
    monkeypatch.setattr(security_checks.shutil, "which", lambda _: "pip-audit")
    monkeypatch.setattr(
        security_checks.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=2, stdout=b"", stderr=b"credential"),
    )
    result, code = security_checks.dependencies()
    assert code == 4 and "credential" not in str(result)
    payload = {"dependencies": [{"name": "invented", "version": "0", "vulns": [{"id": "TEST-1"}]}]}
    monkeypatch.setattr(
        security_checks.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=1, stdout=json.dumps(payload)),
    )
    result, code = security_checks.dependencies()
    assert code == 2 and result["status"] == "DEPENDENCY_VULNERABILITIES_FOUND"


def test_ci_configuration_safety():
    import yaml

    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    assert workflow["permissions"] == {"contents": "read"}
    assert set(workflow["jobs"]) == {"offline", "postgres"}
    text = (ROOT / ".github/workflows/ci.yml").read_text()
    assert "pull_request_target" not in text and "secrets." not in text
    assert "upload-artifact" not in text and "integration smoke-postgres" in text
    assert "HF_HUB_OFFLINE" in text and "requirements-ci.lock" in text
    assert "DROP DATABASE" not in text
