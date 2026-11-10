"""Exercise real-source branches with STEP 04's isolated, invented approvals and records."""

import json

import pytest
import test_official
from test_official import KEY, SOURCE, commit, decision

from pfa.cli import main
from pfa.data import profiling
from pfa.data.official_io import IngestionBlocked, IngestionError

authorized = test_official.authorized
workspace = test_official.workspace


def test_verified_step04_input_and_lineage(authorized):
    root, registry, _ = authorized
    built = commit(authorized)
    report, path = profiling.run_audit(root, registry, SOURCE, KEY, built["dataset_version"])
    assert report.record_count == built["published_count"]
    assert report.source_manifest_reference == built["dataset_version"]
    assert report.source_manifest_checksum
    assert (path / "audit.json").is_file()
    assert not (root / "reports/dataset").joinpath("feedback.jsonl").exists()


def test_missing_manifest_after_permission(authorized):
    root, registry, _ = authorized
    with pytest.raises(IngestionError, match="NOT_AVAILABLE"):
        profiling.run_audit(root, registry, SOURCE, KEY, "of_" + "0" * 32)
    with pytest.raises(IngestionError, match="NOT_AVAILABLE"):
        profiling.run_audit(root, registry, SOURCE, KEY)


def test_cli_missing_authorized_dataset(authorized, capsys):
    assert main(["dataset", "profile", "--source", SOURCE]) == 4
    assert "NOT_AVAILABLE" in capsys.readouterr().out


def test_revocation_precedes_stored_data_access(authorized, monkeypatch):
    root, registry, _ = authorized
    built = commit(authorized)
    decision(root, registry, reference="revoked_test", decision="REVOKED", allowed_scope=[])

    def forbidden(*args, **kwargs):
        raise AssertionError("Revoked data must not be accessed")

    monkeypatch.setattr(profiling, "safe_path", forbidden)
    with pytest.raises(IngestionBlocked):
        profiling.run_audit(root, registry, SOURCE, KEY, built["dataset_version"])


@pytest.mark.parametrize("target", ["data", "manifest", "audit"])
def test_integrity_failures_prevent_report_creation(authorized, target):
    root, registry, _ = authorized
    built = commit(authorized)
    version = built["dataset_version"]
    if target == "data":
        path = root / "data/processed" / version / "feedback.jsonl"
        path.write_text("CORRUPTED")
    elif target == "manifest":
        path = root / "data/manifests" / version / "manifest.json"
        payload = json.loads(path.read_text())
        payload["output_checksum"] = "0" * 64
        path.write_text(json.dumps(payload))
    else:
        path = root / "configs/permission_evidence.json"
        payload = json.loads(path.read_text())
        payload["decisions"][0]["reviewer"] = "CHANGED_SYNTHETIC_REVIEWER"
        path.write_text(json.dumps(payload))
    with pytest.raises((ValueError, PermissionError)):
        profiling.run_audit(root, registry, SOURCE, KEY, version)
    assert not (root / "reports/dataset").exists()


def test_synthetic_manifest_cannot_enter_real_source_route(authorized):
    root, registry, _ = authorized
    built = commit(authorized)
    path = root / "data/manifests" / built["dataset_version"] / "manifest.json"
    data = json.loads(path.read_text())
    data.update(
        provenance="SYNTHETIC",
        source_id="synthetic_fixture",
        permission_reference=None,
        review_state="SIMULATED_SYNTHETIC",
    )
    path.write_text(json.dumps(data))
    with pytest.raises(IngestionError, match="provenance"):
        profiling.run_audit(root, registry, SOURCE, KEY, built["dataset_version"])
