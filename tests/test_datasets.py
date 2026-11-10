"""All records below are synthetic governance fixtures, never citizen data."""

import json
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from pfa.cli import main
from pfa.data.assessment import assess
from pfa.data.permissions import (
    Decision,
    current_decision,
    history,
    record_decision,
    require_access,
)
from pfa.data.registry import Registry, Source, load_registry

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    (tmp_path / "configs").mkdir()
    (tmp_path / "configs/dataset_sources.yaml").write_bytes(
        (ROOT / "configs/dataset_sources.yaml").read_bytes()
    )
    (tmp_path / "configs/permission_evidence.json").write_text('{"decisions": []}')
    (tmp_path / "configs/permission_history.jsonl").write_text("")
    monkeypatch.setenv("PFA_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("PFA_ENVIRONMENT", "test")
    monkeypatch.setenv("PFA_LOG_LEVEL", "INFO")
    return tmp_path, load_registry(tmp_path / "configs/dataset_sources.yaml")


def evidence(root, **changes):
    """Invented reviewer and record, used only in isolated test directories."""
    record = {
        "approval_ref": "synthetic_test_approval",
        "source_id": "synthetic_demo",
        "reviewer": "SYNTHETIC TEST REVIEWER",
        "evidence_reference": "synthetic_test_document",
        "decision_date": date.today().isoformat(),
        "decision": "APPROVED",
        "allowed_scope": ["software_tests"],
        "human_verified": True,
        "license_verified": True,
        "privacy_verified": True,
        "retention_policy": "SYNTHETIC: remove at test teardown",
    }
    record.update(changes)
    path = root / "configs/permission_evidence.json"
    records = json.loads(path.read_text())
    records["decisions"].append(record)
    path.write_text(json.dumps(records), encoding="utf-8")
    return record


def test_registry_loading(workspace):
    _, registry = workspace
    assert len(registry.sources) == 7
    assert all(source.last_verified == "UNKNOWN" for source in registry.sources)
    assert all(source.license_status == "UNKNOWN" for source in registry.sources)


@pytest.mark.parametrize(
    "change",
    [
        {"source_id": "../private"},
        {"permission_status": "YES"},
        {"dataset_role": "TRAINING"},
        {"allowed_training": "false"},
        {"source_name": ""},
        {"source_url": "file:///secret"},
        {"last_verified": "yesterday"},
        {"permission_status": "APPROVED"},
        {"allowed_processing": ["training"]},
        {"license_status": "VERIFIED", "evidence_references": []},
    ],
)
def test_invalid_source_schema(workspace, change):
    _, registry = workspace
    values = registry.sources[0].model_dump()
    values.update(change)
    with pytest.raises(ValidationError):
        Source.model_validate(values)


def test_required_license_and_duplicate_ids(workspace):
    _, registry = workspace
    values = registry.sources[0].model_dump()
    del values["license_status"]
    with pytest.raises(ValidationError):
        Source.model_validate(values)
    with pytest.raises(ValidationError, match="Duplicate source IDs"):
        Registry(sources=[registry.sources[0], registry.sources[0]])


def test_scoring_and_no_permissions(workspace):
    root, registry = workspace
    expected = {
        "uit_vsfc": 14,
        "public_service_official": 32,
        "authorized_agency_export": 30,
        "neu_esc": 14,
        "vn_mps_qa": 8,
        "sipas": 14,
        "synthetic_demo": 0,
    }
    for source_id, total in expected.items():
        result = assess(root, registry, source_id)
        assert result["weighted_total"] == total
        assert sum(item["weight"] for item in result["scores"].values()) == 100
        assert all(item["rationale"] for item in result["scores"].values())
        assert not result["permitted_scope"]
        assert result["recommendation"] != "APPROVED_FOR_SCOPE"
        for scope in ("training", "publication", "internal_analysis", "software_tests"):
            with pytest.raises(PermissionError):
                require_access(root, registry, source_id, scope)
    assert assess(root, registry, "sipas")["recommendation"] == "NOT_SUITABLE"


def test_cli_invalid_source_and_absent_evidence(workspace, capsys):
    assert main(["dataset", "assess", "--source", "missing"]) == 2
    assert (
        main(["dataset", "approve", "--source", "synthetic_demo", "--approval-ref", "missing"]) == 3
    )
    assert "FAIL" in capsys.readouterr().out


def test_reviewed_record_required_and_scoped(workspace):
    root, registry = workspace
    item = evidence(root)
    # Merely writing evidence does not activate it.
    with pytest.raises(PermissionError):
        require_access(root, registry, "synthetic_demo", "software_tests")
    assert (
        main(
            [
                "dataset",
                "approve",
                "--source",
                "synthetic_demo",
                "--approval-ref",
                item["approval_ref"],
            ]
        )
        == 0
    )
    require_access(root, registry, "synthetic_demo", "software_tests")
    with pytest.raises(PermissionError):
        require_access(root, registry, "synthetic_demo", "training")
    result = assess(root, registry, "synthetic_demo")
    assert result["recommendation"] == "APPROVED_FOR_SCOPE"
    assert result["permitted_scope"] == ["software_tests"]
    assert result["weighted_total"] == 30


def test_audit_revocation_and_duplicate_cleanup(workspace):
    root, registry = workspace
    item = evidence(root)
    record_decision(root, registry, "synthetic_demo", item["approval_ref"])
    with pytest.raises(ValueError):
        record_decision(root, registry, "synthetic_demo", item["approval_ref"])
    assert not (root / "configs/permission_history.lock").exists()
    evidence(root, approval_ref="synthetic_revocation", decision="REVOKED", allowed_scope=[])
    record_decision(root, registry, "synthetic_demo", "synthetic_revocation")
    assert len(history(root)) == 2
    assert assess(root, registry, "synthetic_demo")["recommendation"] == "BLOCKED"
    with pytest.raises(PermissionError):
        require_access(root, registry, "synthetic_demo", "software_tests")


@pytest.mark.parametrize(
    "changes",
    [
        {"human_verified": False},
        {"reviewer": "UNKNOWN"},
        {"license_verified": False},
        {"privacy_verified": False},
        {"allowed_scope": []},
        {"decision_date": "2999-01-01"},
        {"evidence_reference": ""},
        {"retention_policy": "UNKNOWN"},
    ],
)
def test_invalid_human_metadata(workspace, changes):
    root, _ = workspace
    record = evidence(root, **changes)
    with pytest.raises(ValidationError):
        Decision.model_validate(record)


def test_sensitive_evidence_not_printed_or_logged(workspace, capsys, caplog):
    root, _ = workspace
    evidence(root, human_verified=False, reviewer="PRIVATE-SENTINEL")
    assert (
        main(
            [
                "dataset",
                "approve",
                "--source",
                "synthetic_demo",
                "--approval-ref",
                "synthetic_test_approval",
            ]
        )
        == 2
    )
    output = capsys.readouterr()
    assert "PRIVATE-SENTINEL" not in output.out + output.err + caplog.text


def test_corrupt_and_changed_history_fail_closed(workspace):
    root, registry = workspace
    item = evidence(root)
    record_decision(root, registry, "synthetic_demo", item["approval_ref"])
    path = root / "configs/permission_evidence.json"
    path.write_text('{"decisions": []}')
    with pytest.raises(PermissionError):
        current_decision(root, registry, "synthetic_demo")
    (root / "configs/permission_history.jsonl").write_text("invalid json")
    with pytest.raises(ValueError):
        require_access(root, registry, "synthetic_demo", "software_tests")


def test_cli_sources_and_assess_are_read_only(workspace, capsys):
    root, _ = workspace
    assert main(["dataset", "sources"]) == 0
    assert "effective_scope=NONE" in capsys.readouterr().out
    assert main(["dataset", "assess", "--source", "uit_vsfc"]) == 0
    assert json.loads(capsys.readouterr().out)["recommendation"] == "PENDING_REVIEW"
    assert not history(root)


def test_writer_failure_releases_lock(workspace):
    root, registry = workspace
    evidence(root)
    with patch("pfa.data.permissions.os.fsync", side_effect=OSError):
        with pytest.raises(OSError):
            record_decision(root, registry, "synthetic_demo", "synthetic_test_approval")
    assert not (root / "configs/permission_history.lock").exists()
    assert history(root) == []


def test_pending_write_blocks_readers(workspace):
    root, registry = workspace
    (root / "configs/permission_history.lock").touch()
    with pytest.raises(PermissionError):
        require_access(root, registry, "synthetic_demo", "software_tests")


def test_sensitive_extra_field_names_are_redacted(workspace, capsys):
    root, _ = workspace
    evidence(root, **{"PRIVATE-SENTINEL": "secret"})
    assert (
        main(
            [
                "dataset",
                "approve",
                "--source",
                "synthetic_demo",
                "--approval-ref",
                "synthetic_test_approval",
            ]
        )
        == 2
    )
    assert "PRIVATE-SENTINEL" not in capsys.readouterr().out
