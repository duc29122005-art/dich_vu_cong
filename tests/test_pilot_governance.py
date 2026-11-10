"""Simulated human decisions in isolated test roots; no actual project approvals."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
import test_official

from pfa.annotation import approval, pilot, pilot_smoke
from pfa.annotation import pilot_store as store
from pfa.annotation.taxonomy import CHECKSUM, VERSION
from pfa.cli import main
from pfa.data import official
from pfa.data.official_io import IngestionBlocked, IngestionError, write_json

ROOT = Path(__file__).resolve().parents[1]
authorized = test_official.authorized
workspace = test_official.workspace


def copy_instrument(root):
    (root / "configs").mkdir(exist_ok=True)
    (root / "docs").mkdir(exist_ok=True)
    for name in ("configs/taxonomy_v1.yaml", "docs/ANNOTATION_GUIDELINES.md"):
        (root / name).write_bytes((ROOT / name).read_bytes())


def decision(root, ref="test_taxonomy_approval", status="APPROVED", **changes):
    values = dict(
        decision_ref=ref,
        taxonomy_version=VERSION,
        taxonomy_checksum=CHECKSUM,
        handbook_checksum=official.file_digest(root / "docs/ANNOTATION_GUIDELINES.md"),
        reviewer_id="synthetic_test_reviewer",
        reviewer_role="research_owner",
        reviewed_at=datetime.now(UTC).isoformat(),
        decision=status,
        evidence_reference="synthetic_test_evidence",
        human_verified=True,
    )
    values.update(changes)
    store.private_directory(store.base(root) / "requests")
    write_json(approval.requests(root, ref), values)
    return values


def test_missing_approval_blocks_before_dataset_access(workspace, monkeypatch):
    root, registry = workspace
    copy_instrument(root)

    def forbidden(*args, **kwargs):
        raise AssertionError("No dataset access before taxonomy approval")

    monkeypatch.setattr(pilot, "inventory", forbidden)
    with pytest.raises(IngestionBlocked, match="TAXONOMY"):
        pilot.sample_pilot(root, registry, "authorized_agency_export")


def test_approval_history_rejection_supersession_and_evidence_binding(workspace):
    root, _ = workspace
    copy_instrument(root)
    decision(root)
    approval.record_taxonomy(root, "test_taxonomy_approval")
    assert approval.require_taxonomy(root)
    for status in ("REJECTED", "SUPERSEDED"):
        ref = "test_" + status.lower()
        decision(root, ref, status)
        approval.record_taxonomy(root, ref)
        with pytest.raises(IngestionBlocked):
            approval.require_taxonomy(root)
    assert len(approval.taxonomy_history(root)) == 3
    with pytest.raises(IngestionError, match="already recorded"):
        approval.record_taxonomy(root, "test_superseded")
    path = approval.requests(root, "test_taxonomy_approval")
    value = json.loads(path.read_text())
    value["reviewer_id"] = "modified_test_identity"
    path.write_text(json.dumps(value))
    with pytest.raises(IngestionBlocked, match="evidence differs"):
        approval.require_taxonomy(root)


@pytest.mark.parametrize("change", ["taxonomy", "handbook", "checksum", "human", "missing"])
def test_changed_instrument_and_missing_human_evidence(workspace, change):
    root, _ = workspace
    copy_instrument(root)
    if change == "missing":
        with pytest.raises(IngestionError, match="missing"):
            approval.record_taxonomy(root, "missing_decision")
        return
    values = {}
    if change == "checksum":
        values["taxonomy_checksum"] = "0" * 64
    elif change == "human":
        values["human_verified"] = False
    decision(root, **values)
    if change in {"checksum", "human"}:
        with pytest.raises(ValueError):
            approval.record_taxonomy(root, "test_taxonomy_approval")
        return
    approval.record_taxonomy(root, "test_taxonomy_approval")
    target = root / (
        "configs/taxonomy_v1.yaml" if change == "taxonomy" else "docs/ANNOTATION_GUIDELINES.md"
    )
    if change == "taxonomy":
        value = json.loads(target.read_text("utf-8"))
        value["tasks"][0]["labels"][0]["definition"] += " changed"
        target.write_text(json.dumps(value), encoding="utf-8")
    else:
        target.write_bytes(target.read_bytes() + b"\nChanged handbook\n")
    with pytest.raises((ValueError, IngestionBlocked)):
        approval.require_taxonomy(root)


def test_missing_permission_after_taxonomy_approval(workspace, monkeypatch):
    root, registry = workspace
    copy_instrument(root)
    decision(root)
    approval.record_taxonomy(root, "test_taxonomy_approval")

    def forbidden(*args, **kwargs):
        raise AssertionError("No dataset inventory without permission")

    monkeypatch.setattr(pilot, "inventory", forbidden)
    with pytest.raises(IngestionBlocked, match="PERMISSION"):
        pilot.sample_pilot(root, registry, "authorized_agency_export")


def test_revoked_permission_blocks_source_access(authorized, monkeypatch):
    root, registry, _ = authorized
    copy_instrument(root)
    decision(root)
    approval.record_taxonomy(root, "test_taxonomy_approval")
    test_official.decision(
        root, registry, reference="pilot_revoked", decision="REVOKED", allowed_scope=[]
    )
    monkeypatch.setattr(
        pilot, "inventory", lambda *args, **kwargs: pytest.fail("Unauthorized access")
    )
    with pytest.raises(IngestionBlocked):
        pilot.sample_pilot(root, registry, test_official.SOURCE)


def real_plan(authorized, monkeypatch, count=2):
    root, registry, _ = authorized
    built = test_official.commit(authorized)
    copy_instrument(root)
    decision(root)
    approval.record_taxonomy(root, "test_taxonomy_approval")
    with store.synthetic_session(root):
        synthetic = pilot_smoke.create_synthetic(root, ROOT)
    value = synthetic.plan.model_dump()
    value.update(
        plan_ref="test_real_plan",
        dataset_type="RESEARCH",
        human_verified=True,
        dataset_version=built["dataset_version"],
        source_id=test_official.SOURCE,
        target_count=count,
        evidence_reference="synthetic_test_plan_evidence",
    )
    write_json(approval.requests(root, "test_real_plan"), value)
    # This test supplies invented data/permissions and simulates account provisioning only.
    monkeypatch.setattr(pilot, "require_operator", lambda *args: None)
    return root, registry, built


def test_real_sampling_branch_uses_reviewed_data_and_pins_manifest(authorized, monkeypatch):
    root, registry, built = real_plan(authorized, monkeypatch)
    result = pilot.sample_pilot(
        root,
        registry,
        test_official.SOURCE,
        2,
        42,
        "test_pilot",
        "test_real_plan",
        test_official.KEY,
    )
    assert result["count"] == 2 and not result["human_gold"]
    manifest, _ = pilot.load_pilot(root, registry, "test_pilot")
    assert manifest.dataset_version == built["dataset_version"]
    path = root / "data/manifests" / built["dataset_version"] / "manifest.json"
    path.write_text("{}")
    with pytest.raises((ValueError, IngestionBlocked)):
        pilot.load_pilot(root, registry, "test_pilot")


def test_insufficient_real_sample_no_replacement(authorized, monkeypatch):
    root, registry, _ = real_plan(authorized, monkeypatch, count=200)
    with pytest.raises(IngestionError, match="Insufficient"):
        pilot.sample_pilot(
            root,
            registry,
            test_official.SOURCE,
            200,
            42,
            "test_pilot",
            "test_real_plan",
            test_official.KEY,
        )
    assert not (pilot.location(root, "test_pilot") / "definition").exists()


def test_account_roles_must_be_distinct(tmp_path):
    with store.synthetic_session(tmp_path):
        manifest = pilot_smoke.create_synthetic(tmp_path, ROOT)
    value = manifest.plan.model_dump()
    value["annotators"]["B"] = value["annotators"]["A"]
    with pytest.raises(ValueError):
        pilot.PilotPlan.model_validate(value)
    value = manifest.plan.model_dump()
    value.update(dataset_type="RESEARCH", human_verified=False)
    with pytest.raises(ValueError):
        pilot.PilotPlan.model_validate(value)


def test_cli_gate_and_missing_pilot_exit_codes(workspace, capsys):
    root, _ = workspace
    copy_instrument(root)
    assert main(["annotation", "sample-pilot", "--source", "authorized_agency_export"]) == 3
    assert "BLOCKED_TAXONOMY" in capsys.readouterr().out
    assert main(["annotation", "agreement", "--pilot", "missing_pilot"]) == 4
    capsys.readouterr()
    assert main(["annotation", "taxonomy", "record", "--decision-ref", "missing"]) == 4


def test_bounded_hash_and_atomic_bundle_cleanup(tmp_path, monkeypatch):
    path = tmp_path / "large_input"
    path.write_bytes(b"12345")
    with pytest.raises(IngestionError, match="size limit"):
        store.file_checksum(path, limit=4)

    def failure(*args, **kwargs):
        raise OSError("SYNTHETIC write failure")

    monkeypatch.setattr(store, "write_json", failure)
    target = tmp_path / "artifacts/version"
    with pytest.raises(OSError):
        store.publish(target, {"data.json": {"synthetic": True}})
    assert list(target.parent.iterdir()) == []
