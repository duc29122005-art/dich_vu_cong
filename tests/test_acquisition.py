"""Invented files and simulated permission decisions only; no network or real citizen data."""

import json
import os
import subprocess
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
import test_official

from pfa.annotation import pilot_store as store
from pfa.cli import main
from pfa.data import acquisition, official
from pfa.data.acquisition.models import Candidates, Receipt
from pfa.data.official_io import IngestionBlocked, IngestionError, write_json
from pfa.data.registry import load_registry

ROOT = Path(__file__).resolve().parents[1]
workspace = test_official.workspace
authorized = test_official.authorized


def handoff(root, path, identifier="test_handoff", **changes):
    values = dict(
        handoff_id=identifier,
        source_id=test_official.SOURCE,
        approval_ref="test_approval",
        source_export_ref="test_export",
        supplier_reference="synthetic_test_supplier",
        reviewer_id="synthetic_test_reviewer",
        evidence_reference="synthetic_test_evidence",
        transfer_method="APPROVED_SECURE_CHANNEL",
        expected_sha256=official.file_digest(path),
        expected_bytes=path.stat().st_size,
        file_format=path.suffix.lower(),
        reviewed_at=datetime.now(UTC).isoformat(),
        provenance="REAL_EXTERNAL",
        human_verified=True,
    )
    values.update(changes)
    store.private_directory(acquisition.evidence_path(root, identifier).parent)
    write_json(acquisition.evidence_path(root, identifier), values)
    return values


def receive(authorized, **changes):
    root, registry, path = authorized
    handoff(root, path, **changes)
    return acquisition.receive(
        root, registry, test_official.SOURCE, path, "test_approval", "test_handoff"
    )


def test_registry_and_unknown_facts():
    registry = load_registry(ROOT / "configs/dataset_sources.yaml")
    result = acquisition.candidates(ROOT, registry)
    assert result.candidates[0].source_id == "authorized_agency_export"
    assert all(item.expected_sample_count == "UNKNOWN" for item in result.candidates)
    assert all(item.permission_status == "PENDING" for item in result.candidates)
    values = result.model_dump()
    values["candidates"].append(values["candidates"][0])
    with pytest.raises(ValueError):
        Candidates.model_validate(values)


def test_permission_before_any_input_open(workspace, monkeypatch):
    root, registry = workspace
    original = Path.open

    def guarded(path, *args, **kwargs):
        if path.name == "DO_NOT_READ.csv":
            pytest.fail("Unauthorized input was opened")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded)
    with pytest.raises(IngestionBlocked):
        acquisition.receive(
            root,
            registry,
            test_official.SOURCE,
            root / "DO_NOT_READ.csv",
            "missing",
            "test_handoff",
        )
    assert not acquisition.base(root).exists()


@pytest.mark.parametrize(
    "problem", ["revoked", "expired", "evidence", "wrong_scope", "wrong_reference"]
)
def test_invalid_permission(authorized, problem):
    root, registry, path = authorized
    reference = "test_approval"
    if problem == "revoked":
        test_official.decision(
            root, registry, reference="test_revoked", decision="REVOKED", allowed_scope=[]
        )
    elif problem == "expired":
        test_official.decision(
            root,
            registry,
            reference="test_expired",
            expires_on=(date.today() - timedelta(days=1)).isoformat(),
        )
    elif problem == "evidence":
        evidence = root / "configs/permission_evidence.json"
        evidence.write_text('{"decisions": []}')
    elif problem == "wrong_scope":
        test_official.decision(
            root, registry, reference="test_training_only", allowed_scope=["training"]
        )
    else:
        reference = "wrong"
    with pytest.raises(IngestionBlocked):
        acquisition.receive(root, registry, test_official.SOURCE, path, reference, "not_present")


def test_missing_transfer_evidence_does_not_copy_input(authorized):
    root, registry, path = authorized
    with pytest.raises(IngestionError, match="NOT_AVAILABLE"):
        acquisition.receive(root, registry, test_official.SOURCE, path, "test_approval", "missing")
    assert not acquisition.location(root, "missing").exists()


@pytest.mark.parametrize(
    "changes",
    [
        {"human_verified": False},
        {"source_id": "public_service_official"},
        {"approval_ref": "wrong"},
        {"expected_sha256": "0" * 64},
        {"expected_bytes": 1},
        {"file_format": ".jsonl"},
        {"evidence_reference": "unknown"},
        {"reviewed_at": "2025-01-01T00:00:00"},
    ],
)
def test_invalid_handoff(authorized, changes):
    root, registry, path = authorized
    handoff(root, path, **changes)
    with pytest.raises((ValueError, PermissionError)):
        acquisition.receive(
            root, registry, test_official.SOURCE, path, "test_approval", "test_handoff"
        )
    assert not acquisition.location(root, "test_handoff").exists()
    assert not (acquisition.base(root) / ".receive.lock").exists()


def test_receive_verify_and_step04_preview(authorized):
    root, registry, _ = authorized
    result = receive(authorized)
    assert result["record_count"] == 10 and not result["published"]
    verified = acquisition.verify(root, registry, "test_handoff")
    assert verified["step04_handoff"] == "READY" and not verified["privacy_cleared"]
    preview = official.ingest(
        root,
        registry,
        verified["source_id"],
        root / verified["input"],
        verified["approval_ref"],
        test_official.KEY,
    )
    assert preview["status"] == "PREVIEW"
    assert (
        not list((root / "data/processed").glob("of_*"))
        if (root / "data/processed").exists()
        else True
    )


def test_jsonl_reception(authorized):
    root, registry, path = authorized
    path = path.with_suffix(".jsonl")
    path.write_text(
        json.dumps(
            {
                "feedback_id": "SYNTHETIC",
                "content": "SYNTHETIC: Chưa có hướng dẫn rõ ràng.",
                "created_at": None,
                "source_id": test_official.SOURCE,
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    handoff(root, path)
    assert (
        acquisition.receive(
            root, registry, test_official.SOURCE, path, "test_approval", "test_handoff"
        )["record_count"]
        == 1
    )
    assert acquisition.verify(root, registry, "test_handoff")["record_count"] == 1


@pytest.mark.parametrize(
    "suffix,payload",
    [
        (".csv", b"a,a\n1,2\n"),
        (".csv", b"a,b\n1\n"),
        (".csv", b"a\n\xff\n"),
        (".csv", b"a\n"),
        (".jsonl", b"{bad}\n"),
        (".jsonl", b'{"a":1,"a":2}\n'),
        (".jsonl", b"[]\n"),
        (".jsonl", b'{"a": NaN}\n'),
        (".jsonl", b"\n"),
    ],
)
def test_invalid_containers_are_not_published(authorized, suffix, payload):
    root, registry, original = authorized
    path = original.with_suffix(suffix)
    path.write_bytes(payload)
    handoff(root, path)
    with pytest.raises(IngestionError):
        acquisition.receive(
            root, registry, test_official.SOURCE, path, "test_approval", "test_handoff"
        )
    assert not acquisition.location(root, "test_handoff").exists()


def test_corruption_revocation_and_changed_evidence(authorized):
    root, registry, _ = authorized
    receive(authorized)
    path = acquisition.location(root, "test_handoff") / "payload.csv"
    original = path.read_bytes()
    path.write_bytes(original + b"\n")
    with pytest.raises(IngestionError, match="checksum"):
        acquisition.verify(root, registry, "test_handoff")
    path.write_bytes(original)
    evidence = acquisition.evidence_path(root, "test_handoff")
    values = json.loads(evidence.read_text())
    values["supplier_reference"] = "changed"
    evidence.write_text(json.dumps(values))
    with pytest.raises(IngestionBlocked, match="evidence"):
        acquisition.verify(root, registry, "test_handoff")
    test_official.decision(
        root, registry, reference="test_revoked", decision="REVOKED", allowed_scope=[]
    )
    with pytest.raises(IngestionBlocked):
        acquisition.verify(root, registry, "test_handoff")


def test_duplicate_handoff_export_and_payload(authorized):
    root, registry, path = authorized
    receive(authorized)
    with pytest.raises(IngestionError, match="already received"):
        acquisition.receive(
            root, registry, test_official.SOURCE, path, "test_approval", "test_handoff"
        )
    handoff(root, path, identifier="second")
    with pytest.raises(IngestionError, match="Duplicate"):
        acquisition.receive(root, registry, test_official.SOURCE, path, "test_approval", "second")


def test_path_traversal_symlink_and_protected_storage(authorized, monkeypatch):
    root, registry, path = authorized
    handoff(root, path)
    with pytest.raises(IngestionError, match="traversal"):
        acquisition.receive(
            root,
            registry,
            test_official.SOURCE,
            path.parent / ".." / path.parent.name / path.name,
            "test_approval",
            "test_handoff",
        )
    with pytest.raises(IngestionError):
        acquisition.location(root, "../outside")
    original = Path.lstat

    def reparse(value, *args, **kwargs):
        info = original(value, *args, **kwargs)
        if value == path:
            from types import SimpleNamespace

            return SimpleNamespace(st_mode=info.st_mode, st_file_attributes=0x400)
        return info

    with monkeypatch.context() as patch:
        patch.setattr(Path, "lstat", reparse)
        with pytest.raises(IngestionError, match="reparse"):
            acquisition.receive(
                root, registry, test_official.SOURCE, path, "test_approval", "test_handoff"
            )
    result = receive_again_without_evidence(authorized)
    receipt = Receipt.model_validate(
        store.read_json(acquisition.location(root, "test_handoff") / "receipt.json")
    )
    assert result["status"] == "RECEIVED_QUARANTINED"
    assert receipt.storage_protection == (
        "WINDOWS_OWNER_SYSTEM_ACL" if os.name == "nt" else "POSIX_0700_0600"
    )


def receive_again_without_evidence(authorized):
    root, registry, path = authorized
    return acquisition.receive(
        root, registry, test_official.SOURCE, path, "test_approval", "test_handoff"
    )


def test_atomic_failure_cleanup(authorized, monkeypatch):
    root, registry, path = authorized
    handoff(root, path)

    def fail(*args, **kwargs):
        raise OSError("SYNTHETIC disk failure")

    monkeypatch.setattr(acquisition, "write_json", fail)
    with pytest.raises(OSError):
        receive_again_without_evidence(authorized)
    assert not acquisition.location(root, "test_handoff").exists()
    assert not (acquisition.base(root) / ".receive.lock").exists()
    assert not list(acquisition.base(root).glob(".receive-*"))


def test_cli_no_pii_in_errors_or_reports(authorized, capsys, caplog):
    root, registry, path = authorized
    path.write_text("content\nPRIVATE_SENTINEL person@example.invalid\n")
    handoff(root, path, expected_sha256="0" * 64)
    assert (
        main(
            [
                "dataset",
                "acquisition",
                "receive",
                "--source",
                test_official.SOURCE,
                "--input",
                str(path),
                "--approval-ref",
                "test_approval",
                "--handoff-id",
                "test_handoff",
            ]
        )
        == 2
    )
    output = capsys.readouterr().out + caplog.text
    assert "PRIVATE_SENTINEL" not in output and "person@example.invalid" not in output


def test_smoke_cli_and_git_exclusions(monkeypatch, capsys):
    monkeypatch.setenv("PFA_PROJECT_ROOT", str(ROOT))
    assert main(["dataset", "acquisition", "smoke"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "ACQUISITION_SMOKE_PASS_SYNTHETIC"
    assert result["temporary_storage_cleaned"] and result["unauthorized_reception_blocked"]
    assert result["step04_preview"] == "PREVIEW" and not result["published"]
    command = [
        "git",
        "-c",
        "safe.directory=" + ROOT.as_posix(),
        "check-ignore",
        "data/private/acquisition/receipts/test/payload.csv",
        "data/private/acquisition/receipts/test/receipt.json",
        "data/private/acquisition/handoffs/test.json",
    ]
    assert subprocess.run(command, cwd=ROOT, capture_output=True).returncode == 0


def copy_request_materials(root):
    (root / "configs/acquisition_candidates.yaml").write_bytes(
        (ROOT / "configs/acquisition_candidates.yaml").read_bytes()
    )
    (root / "docs").mkdir(exist_ok=True)
    for name in (
        "DATA_REQUEST_TEMPLATE.md",
        "REAL_DATA_REQUEST_CHECKLIST.md",
        "DATA_TRANSFER_SPEC.md",
    ):
        (root / "docs" / name).write_bytes((ROOT / "docs" / name).read_bytes())


def test_status_preflight_request_pack_cli(workspace, capsys):
    root, registry = workspace
    copy_request_materials(root)
    assert main(["dataset", "acquisition", "status", "--source", test_official.SOURCE]) == 3
    assert json.loads(capsys.readouterr().out)["status"] == "BLOCKED_PERMISSION"
    assert main(["dataset", "acquisition", "preflight", "--source", test_official.SOURCE]) == 3
    capsys.readouterr()
    output = root / "reports/request_v1"
    assert (
        main(
            [
                "dataset",
                "acquisition",
                "request-pack",
                "--source",
                test_official.SOURCE,
                "--output",
                str(output),
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert not result["sent"] and not result["approval_granted"]
    assert set(path.name for path in output.iterdir()) == {
        "DATA_REQUEST.md",
        "REQUEST_CHECKLIST.md",
        "DATA_TRANSFER_SPEC.md",
        "source.json",
        "checksums.json",
    }
    before = (output / "DATA_REQUEST.md").read_bytes()
    with pytest.raises(IngestionError, match="exists"):
        acquisition.request_pack(root, registry, test_official.SOURCE, output)
    assert (output / "DATA_REQUEST.md").read_bytes() == before
    with pytest.raises(IngestionError):
        acquisition.request_pack(root, registry, test_official.SOURCE, root / ".." / "escape")


def test_preflight_scope_no_payload_reads(authorized, monkeypatch):
    root, registry, _ = authorized
    monkeypatch.setattr(acquisition, "transport", lambda *args: pytest.fail("Preflight read input"))
    assert acquisition.preflight(root, registry, test_official.SOURCE)["file_read"] is False
    with pytest.raises(IngestionBlocked):
        acquisition.preflight(root, registry, test_official.SOURCE, "training")


def test_cli_official_receipt_binding(authorized, capsys):
    root, _, _ = authorized
    receive(authorized)
    path = acquisition.location(root, "test_handoff") / "payload.csv"
    args = [
        "dataset",
        "official",
        "import",
        "--source",
        test_official.SOURCE,
        "--input",
        str(path),
        "--approval-ref",
        "test_approval",
        "--receipt-id",
        "test_handoff",
        "--mode",
        "preview",
    ]
    assert main(args) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "PREVIEW"
    args[args.index(str(path))] = str(root / "data/private/other.csv")
    assert main(args) == 3


def test_verify_revoked_before_payload_read(authorized, monkeypatch):
    root, registry, _ = authorized
    receive(authorized)
    test_official.decision(
        root, registry, reference="test_revoked", decision="REVOKED", allowed_scope=[]
    )
    original = Path.open

    def guarded(path, *args, **kwargs):
        if path.name == "payload.csv":
            pytest.fail("Revoked payload accessed")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded)
    with pytest.raises(IngestionBlocked):
        acquisition.verify(root, registry, "test_handoff")


def test_mid_reception_revocation_cleans_staging(authorized, monkeypatch):
    root, registry, path = authorized
    handoff(root, path)
    original = acquisition.transport

    def revoke(payload):
        count = original(payload)
        test_official.decision(
            root, registry, reference="test_revoked", decision="REVOKED", allowed_scope=[]
        )
        return count

    monkeypatch.setattr(acquisition, "transport", revoke)
    with pytest.raises(IngestionBlocked):
        receive_again_without_evidence(authorized)
    assert not acquisition.location(root, "test_handoff").exists()
    assert not list(acquisition.base(root).glob(".receive-*"))


def test_csv_bom_and_unknown_source(authorized):
    root, registry, path = authorized
    path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())
    receive(authorized)
    assert acquisition.verify(root, registry, "test_handoff")["record_count"] == 10
    with pytest.raises(IngestionBlocked):
        acquisition.receive(root, registry, "unknown", path, "test_approval", "other")


def test_prior_receipt_corruption_blocks_new_reception(authorized):
    root, registry, path = authorized
    receive(authorized)
    prior = acquisition.location(root, "test_handoff") / "receipt.json"
    value = json.loads(prior.read_text())
    value["handoff"]["supplier_reference"] = "tampered"
    prior.write_text(json.dumps(value))
    handoff(root, path, identifier="second")
    with pytest.raises(IngestionError, match="integrity"):
        acquisition.receive(root, registry, test_official.SOURCE, path, "test_approval", "second")
