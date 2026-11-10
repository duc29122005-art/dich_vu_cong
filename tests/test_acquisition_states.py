"""Temporary synthetic evidence only. Contact events never establish usage permission."""

import io
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
import test_acquisition

from pfa.annotation import pilot_store as store
from pfa.cli import main
from pfa.data import acquisition
from pfa.data.acquisition import events
from pfa.data.official_io import IngestionBlocked, IngestionError, write_json

authorized = test_acquisition.authorized
workspace = test_acquisition.workspace


def event(root, state, reference):
    value = dict(
        event_ref=reference,
        source_id=test_acquisition.test_official.SOURCE,
        state=state,
        reviewer_id="synthetic_test_reviewer",
        evidence_reference="synthetic_test_contact_evidence",
        reviewed_at=datetime.now(UTC).isoformat(),
        human_verified=True,
    )
    store.private_directory(events.request_path(root, reference).parent)
    write_json(events.request_path(root, reference), value)
    return value


def test_contact_lifecycle_does_not_grant_permission(workspace):
    root, registry = workspace
    test_acquisition.copy_request_materials(root)
    assert (
        acquisition.status(root, registry, test_acquisition.test_official.SOURCE)["contact_state"]
        == "DISCOVERED"
    )
    for index, state in enumerate(("CONTACT_PENDING", "REQUESTED", "PERMISSION_REVIEW")):
        reference = f"synthetic_event_{index}"
        event(root, state, reference)
        result = events.record(root, registry, test_acquisition.test_official.SOURCE, reference)
        assert result["usage_permission_granted"] is False
    result = acquisition.status(root, registry, test_acquisition.test_official.SOURCE)
    assert result["contact_state"] == "PERMISSION_REVIEW"
    assert result["workflow_state"] == "BLOCKED" and result["scope"] == []
    with pytest.raises(IngestionBlocked):
        acquisition.preflight(root, registry, test_acquisition.test_official.SOURCE)
    assert len(events.history(root, test_acquisition.test_official.SOURCE)) == 3


@pytest.mark.parametrize(
    "state", ["APPROVED_FOR_SCOPE", "READY_FOR_HANDOFF", "READY_FOR_STEP04", "REVOKED"]
)
def test_cannot_record_usage_states_as_contact_events(workspace, state):
    root, registry = workspace
    event(root, state, "fake_grant")
    with pytest.raises(ValueError):
        events.record(root, registry, test_acquisition.test_official.SOURCE, "fake_grant")


def test_invalid_transition_duplicate_and_audit_tampering(workspace):
    root, registry = workspace
    event(root, "REQUESTED", "skipped")
    with pytest.raises(IngestionError, match="transition"):
        events.record(root, registry, test_acquisition.test_official.SOURCE, "skipped")
    event(root, "CONTACT_PENDING", "contact")
    events.record(root, registry, test_acquisition.test_official.SOURCE, "contact")
    with pytest.raises(IngestionError):
        events.record(root, registry, test_acquisition.test_official.SOURCE, "contact")
    path = events.request_path(root, "contact")
    value = json.loads(path.read_text())
    value["reviewer_id"] = "tampered"
    path.write_text(json.dumps(value))
    with pytest.raises(IngestionBlocked):
        events.history(root, test_acquisition.test_official.SOURCE)


def test_receipt_state_and_verification_audit(authorized):
    root, registry, _ = authorized
    test_acquisition.copy_request_materials(root)
    assert (
        acquisition.status(root, registry, test_acquisition.test_official.SOURCE)["workflow_state"]
        == "APPROVED_FOR_SCOPE"
    )
    test_acquisition.handoff(root, authorized[2])
    assert (
        acquisition.status(root, registry, test_acquisition.test_official.SOURCE)["workflow_state"]
        == "READY_FOR_HANDOFF"
    )
    test_acquisition.receive_again_without_evidence(authorized)
    assert (
        acquisition.status(root, registry, test_acquisition.test_official.SOURCE)["workflow_state"]
        == "RECEIVED_QUARANTINED"
    )
    verified = acquisition.verify(root, registry, "test_handoff")
    assert verified["workflow_state"] == "READY_FOR_STEP04"
    snapshot = acquisition.status(root, registry, test_acquisition.test_official.SOURCE)
    assert snapshot["workflow_state"] == "READY_FOR_STEP04"
    assert not snapshot["payloads_read_or_verified_now"]
    assert acquisition.verify(root, registry, "test_handoff")["audit_ref"] == verified["audit_ref"]
    test_acquisition.test_official.decision(
        root, registry, reference="test_revoked", decision="REVOKED", allowed_scope=[]
    )
    assert (
        acquisition.status(root, registry, test_acquisition.test_official.SOURCE)["workflow_state"]
        == "REVOKED"
    )


def test_cli_verification_hides_protected_payload_location(authorized, capsys):
    test_acquisition.receive(authorized)
    assert main(["dataset", "acquisition", "verify", "--receipt-id", "test_handoff"]) == 0
    value = json.loads(capsys.readouterr().out)
    assert "input" not in value
    assert "data/private" not in json.dumps(value) and "payload.csv" not in json.dumps(value)


def test_licensed_slot_is_not_registered_source():
    root = test_acquisition.ROOT
    registry = test_acquisition.load_registry(root / "configs/dataset_sources.yaml")
    slots = acquisition.candidates(root, registry).discovery_slots
    assert slots[0].slot_id == "licensed_open_feedback" and slots[0].source_id is None
    assert len(registry.sources) == 7
    with pytest.raises(ValueError):
        registry.source("licensed_open_feedback")


@pytest.mark.parametrize("reference", ["", "fabricated_approval"])
def test_empty_or_fabricated_permission_before_input_read(authorized, monkeypatch, reference):
    root, registry, path = authorized
    original = Path.open

    def guarded(file, *args, **kwargs):
        if file == path:
            pytest.fail("Invalid permission accessed input")
        return original(file, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded)
    with pytest.raises(IngestionBlocked):
        acquisition.receive(
            root, registry, test_acquisition.test_official.SOURCE, path, reference, "x"
        )


@pytest.mark.parametrize("problem", ["missing", "unsupported", "huge", "growing"])
def test_invalid_or_changing_input_cleanup(authorized, monkeypatch, problem):
    root, registry, path = authorized
    test_acquisition.handoff(root, path)
    if problem == "missing":
        path.unlink()
    elif problem == "unsupported":
        path = path.rename(path.with_suffix(".xlsx"))
    elif problem == "huge":
        with path.open("r+b") as stream:
            stream.truncate(acquisition.MAX_BYTES + 1)
    else:
        original = Path.open
        grown = path.read_bytes() + b"extra"

        def changed(file, *args, **kwargs):
            if file == path and args and args[0] == "rb":
                return io.BytesIO(grown)
            return original(file, *args, **kwargs)

        monkeypatch.setattr(Path, "open", changed)
    with pytest.raises(IngestionError):
        acquisition.receive(
            root,
            registry,
            test_acquisition.test_official.SOURCE,
            path,
            "test_approval",
            "test_handoff",
        )
    assert not acquisition.location(root, "test_handoff").exists()
    assert not list(acquisition.base(root).glob(".receive-*"))
    assert not (acquisition.base(root) / ".receive.lock").exists()


def test_verification_audit_corruption_fails_closed(authorized):
    root, registry, _ = authorized
    test_acquisition.receive(authorized)
    acquisition.verify(root, registry, "test_handoff")
    marker = next((acquisition.base(root) / "verification_audit").glob("*/*/verification.json"))
    value = json.loads(marker.read_text())
    assert datetime.fromisoformat(value["verified_at"]).tzinfo is not None
    value["states"] = ["PUBLISHED"]
    marker.write_text(json.dumps(value))
    with pytest.raises((ValueError, PermissionError)):
        acquisition.verify(root, registry, "test_handoff")
    test_acquisition.copy_request_materials(root)
    with pytest.raises((ValueError, PermissionError)):
        acquisition.status(root, registry, test_acquisition.test_official.SOURCE)


def test_receipt_never_grants_step04_publication(authorized, capsys):
    root, _, _ = authorized
    test_acquisition.receive(authorized)
    payload = acquisition.location(root, "test_handoff") / "payload.csv"
    assert (
        main(
            [
                "dataset",
                "official",
                "import",
                "--source",
                test_acquisition.test_official.SOURCE,
                "--input",
                str(payload),
                "--approval-ref",
                "test_approval",
                "--receipt-id",
                "test_handoff",
                "--mode",
                "commit",
            ]
        )
        == 3
    )
    assert "payload.csv" not in capsys.readouterr().out
    assert not list((root / "data/processed").glob("of_*"))
