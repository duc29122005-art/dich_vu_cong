"""Offline local release checks; all roles, cases and measurements are invented."""

import json
import secrets
import socket
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select
from streamlit.testing.v1 import AppTest

from dashboard.api_client import Client
from pfa.analytics.fixtures import seed
from pfa.analytics.schemas import NOTICE
from pfa.annotation import pilot_store as store
from pfa.api.settings import ApiSettings
from pfa.cli import main
from pfa.data.official_io import IngestionBlocked
from pfa.db.models import Feedback, Prediction, ReviewEvent
from pfa.release import audit, config, demo, manifest, preflight

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def credentials(monkeypatch):
    items = [
        {
            "actor_id": "demo_" + role.lower(),
            "role": role,
            "source_ids": ["synthetic_demo"],
            "can_view_text": role != "ANALYST",
            "key": secrets.token_urlsafe(48),
        }
        for role in ("ADMIN", "REVIEWER", "ANALYST")
    ]
    monkeypatch.setenv("PFA_ENVIRONMENT", "test")
    monkeypatch.setenv("PFA_API_MODE", "DEMO_ONLY")
    monkeypatch.setenv("PFA_API_PRINCIPALS", json.dumps(items))
    monkeypatch.setenv("PFA_DASHBOARD_API_KEY", items[2]["key"])
    monkeypatch.setenv("PFA_DASHBOARD_API_URL", "http://127.0.0.1:8000")
    return items


def test_config_and_pins():
    rules = config.load(ROOT)
    assert rules.classification == "TECHNICAL_DEMO_ONLY"
    assert len(preflight.locked(ROOT)) == 84
    assert preflight.workflow_check(ROOT).startswith("STATIC_CHECK_PASS")


@pytest.mark.parametrize(
    "field,value",
    [
        ("classification", "PRODUCTION"),
        ("model_mode", "APPROVED_MODEL"),
        ("bind_host", "0.0.0.0"),
        ("fixture_seed", -1),
        ("fixture_seed", True),
    ],
)
def test_closed_release_configuration(field, value):
    raw = config.load(ROOT).model_dump()
    raw[field] = value
    with pytest.raises(ValidationError):
        config.Release.model_validate(raw)


def test_preflight_isolated_and_explicit_service(credentials):
    isolated = preflight.preflight(ROOT, isolated=True)
    live = preflight.preflight(ROOT)
    assert isolated["status"] == live["status"] == "WARNING"
    assert all(c["status"] == "PASS" for c in live["checks"])
    assert not live["dependency_audit_executed"] and live["POSTGRES_HISTORICAL"].startswith(
        "VERIFIED"
    )


@pytest.mark.parametrize(
    "change", ["production", "approved", "missing", "source", "dashboard_admin", "no_reviewer_text"]
)
def test_service_preflight_denials(credentials, monkeypatch, change):
    if change == "production":
        monkeypatch.setenv("PFA_ENVIRONMENT", "production")
    elif change == "approved":
        monkeypatch.setenv("PFA_API_MODE", "APPROVED_MODEL")
    elif change == "missing":
        monkeypatch.delenv("PFA_API_PRINCIPALS")
    elif change == "source":
        credentials[0]["source_ids"] = ["public_service_official"]
        monkeypatch.setenv("PFA_API_PRINCIPALS", json.dumps(credentials))
    elif change == "dashboard_admin":
        monkeypatch.setenv("PFA_DASHBOARD_API_KEY", credentials[0]["key"])
    else:
        credentials[1]["can_view_text"] = False
        monkeypatch.setenv("PFA_API_PRINCIPALS", json.dumps(credentials))
    assert preflight.preflight(ROOT)["status"] == "BLOCKED"


def test_missing_dependency_blocks_without_echoing_environment(monkeypatch):
    original = preflight.metadata.version

    def missing(name):
        if name == "fastapi":
            raise preflight.metadata.PackageNotFoundError(name)
        return original(name)

    monkeypatch.setattr(preflight.metadata, "version", missing)
    result = preflight.preflight(ROOT, isolated=True)
    assert result["status"] == "BLOCKED"
    detail = next(c["detail"] for c in result["checks"] if c["check"] == "dependencies")
    assert any(d["package"] == "fastapi" and d["installed"] is None for d in detail["dependencies"])


def test_demo_auth_health_dashboard_and_cleanup(credentials, monkeypatch):
    settings = ApiSettings(environment="test", observability_enabled=True)
    with demo.application(ROOT, settings) as (app, database, temporary, fixtures):
        with TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000)) as client:
            assert fixtures["records"] == 420
            assert client.get("/api/v1/models/status").status_code == 401
            auth = {"X-API-Key": credentials[0]["key"]}
            assert (
                client.get("/api/v1/operations/status", headers=auth).json()["database_health"]
                == "AVAILABLE"
            )
            original = Client.fetch

            def local(self, endpoint, filters):
                self.http = client
                return original(self, endpoint, filters)

            monkeypatch.setattr(Client, "fetch", local)
            view = AppTest.from_file(str(ROOT / "dashboard/app.py"), default_timeout=25).run()
            assert not view.exception and view.metric[0].value == "420"
            assert any(NOTICE in w.value for w in view.warning)
    assert not temporary.exists() and not app.state.service.provider.loaded


def test_seed_reproducibility_and_no_duplicate_setup(credentials):
    settings = ApiSettings(environment="test")
    ids = []
    for value in (17, 17, 18):
        with demo.application(ROOT, settings, identifier_seed=value) as (_, database, _, _):
            with database.sessions() as session:
                ids.append(
                    tuple(
                        tuple(session.scalars(select(table).order_by(table)))
                        for table in (
                            Feedback.feedback_id,
                            Prediction.prediction_id,
                            ReviewEvent.review_event_id,
                        )
                    )
                )
            with pytest.raises(IngestionBlocked):
                seed(database, identifier_seed=value)
    assert ids[0] == ids[1] and ids[0] != ids[2]


def test_demo_cleanup_on_failure(credentials):
    temporary = None
    with pytest.raises(RuntimeError):
        with demo.application(ROOT, ApiSettings(environment="test")) as (_, _, temporary, _):
            raise RuntimeError("invented failure")
    assert temporary is not None and not temporary.exists()


@pytest.mark.parametrize("port", [0, 80, 65536, True])
def test_invalid_ports(port):
    assert not demo.available(port)


def test_occupied_port_without_server():
    with socket.socket() as occupied:
        occupied.bind(("127.0.0.1", 0))
        assert not demo.available(occupied.getsockname()[1])


def test_dashboard_child_receives_no_admin_or_db_secrets(credentials, monkeypatch):
    monkeypatch.setattr(preflight, "preflight", lambda *a, **k: {"status": "WARNING"})
    monkeypatch.setenv("PFA_DB_URL", "synthetic-marker")
    monkeypatch.setenv("TEST_DATABASE_URL", "synthetic-marker")
    monkeypatch.setattr(demo, "available", lambda _: True)
    captured = {}

    def run(args, **kwargs):
        captured.update(kwargs)
        assert "--server.address=127.0.0.1" in args
        assert all(c["key"] not in str(args) for c in credentials)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(demo.subprocess, "run", run)
    assert demo.serve_dashboard(ROOT, 8501) == 0
    assert captured["env"]["PFA_DASHBOARD_API_KEY"] == credentials[2]["key"]
    assert not any(
        k in captured["env"] for k in ("PFA_API_PRINCIPALS", "PFA_DB_URL", "TEST_DATABASE_URL")
    )


def test_manifest_inventory_integrity_and_privacy():
    built = manifest.build(ROOT)
    assert manifest.verify(ROOT, built)["status"] == "RELEASE_MANIFEST_VERIFIED"
    files = built["content"]["artifacts"]
    assert not any(
        p.startswith(("data/", "reports/")) or p.endswith((".pt", ".pkl", ".dump")) for p in files
    )
    assert ".env" not in files and "docs/STEP17_VERIFICATION.md" not in files
    assert not built["packaged_archive"] and built["content"]["model_provenance"]["requires_review"]
    built["content"]["model_provenance"]["trained"] = True
    built["content_sha256"] = store.digest(built["content"])
    with pytest.raises(ValueError):
        manifest.verify(ROOT, built)


def test_manifest_drift_and_arbitrary_paths_rejected():
    built = manifest.build(ROOT)
    built["content"]["artifacts"]["../private"] = "0" * 64
    built["content_sha256"] = store.digest(built["content"])
    with pytest.raises(ValueError):
        manifest.verify(ROOT, built)
    with pytest.raises((ValueError, IngestionBlocked)):
        manifest.publish(ROOT, Path("../outside"))


@pytest.mark.parametrize(
    "outcome,expected", [("pass", 0), ("findings", 2), ("skipped", 4), ("network", 4), ("empty", 4)]
)
def test_explicit_audit_result_states(monkeypatch, outcome, expected):
    monkeypatch.setattr(audit.importlib.util, "find_spec", lambda _: object())
    monkeypatch.setattr(audit, "locked", lambda _: {"torch": "2.15.0+cpu"})
    monkeypatch.setattr(audit, "installed_version", lambda _: "test-checker")

    def result(args, **kwargs):
        requirements = Path(args[args.index("-r") + 1]).read_text()
        assert requirements == "torch==2.15.0\n"
        if outcome == "network":
            raise OSError("must-not-echo")
        entry = {"name": "torch", "version": "2.15.0", "vulns": []}
        if outcome == "findings":
            entry["vulns"] = [{"id": "TEST-ADVISORY", "fix_versions": ["2.16.0"]}]
        elif outcome == "skipped":
            entry["skip_reason"] = "invented"
        return SimpleNamespace(
            returncode=1 if outcome == "findings" else 0,
            stdout=json.dumps({"dependencies": [] if outcome == "empty" else [entry]}),
        )

    monkeypatch.setattr(audit.subprocess, "run", result)
    report, code = audit.run(ROOT)
    assert code == expected and "must-not-echo" not in str(report)
    assert report["audited_pins"][0]["version"].endswith("+cpu")


def test_audit_unavailable_never_passes(monkeypatch):
    monkeypatch.setattr(audit.importlib.util, "find_spec", lambda _: None)
    report, code = audit.run(ROOT)
    assert code == 4 and report["status"] == "AUDIT_NOT_AVAILABLE" and not report["executed"]


def test_release_cli_exits_and_safe_errors(monkeypatch, capsys):
    assert main(["release", "preflight", "--isolated"]) == 0
    assert "WARNING" in capsys.readouterr().out
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    assert main(["release", "postgres-check"]) == 4
    assert "NOT_VERIFIED" in capsys.readouterr().out
    assert main(["release", "verify", "--manifest", "../unsafe"]) == 2
    assert "../unsafe" not in capsys.readouterr().out


def test_release_smoke_offline():
    from pfa.release.smoke import smoke

    value = smoke(ROOT)
    assert value["status"] == "RELEASE_SMOKE_PASS_TECHNICAL_DEMO"
    assert value["integration_records"] == 428 and value["launch_fixture_records"] == 420
    assert value["temporary_storage_cleaned"] and value["research_results"] == "NOT_AVAILABLE"


def test_research_templates_and_matrix_do_not_claim_results():
    for rq in range(1, 5):
        text = (ROOT / f"docs/research/RQ{rq}_RESULTS_TEMPLATE.md").read_text("utf-8")
        assert "PENDING" in text and "BLOCKED_ON_" in text
    matrix = (ROOT / "docs/RESEARCH_READINESS_MATRIX.md").read_text("utf-8")
    assert "Required evidence" in matrix and "Verification instructions" in matrix
    assert "| PASS |" not in matrix
