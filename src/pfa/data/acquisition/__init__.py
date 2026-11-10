"""Evidence-bound local reception. No web scraper, sender or automatic publication."""

import csv
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from pfa.annotation import pilot_store as store
from pfa.annotation.approval import reviewed_time
from pfa.data import official
from pfa.data.acquisition import events
from pfa.data.acquisition.models import (
    MAX_BYTES,
    MAX_RECORDS,
    Candidate,
    Candidates,
    Handoff,
    Receipt,
)
from pfa.data.official_io import (
    IngestionBlocked,
    IngestionError,
    protect_directory,
    safe_path,
    write_json,
)
from pfa.data.permissions import Decision, current_decision, require_access
from pfa.data.registry import Registry, Scope


def candidates(root: Path, registry: Registry) -> Candidates:
    result = Candidates.model_validate(
        store.read_json(root / "configs/acquisition_candidates.yaml")
    )
    for item in result.candidates:
        source = registry.source(item.source_id)
        if source.source_url != item.source_url:
            raise IngestionError("Candidate source URL differs from governance registry")
    return result


def candidate(root: Path, registry: Registry, source_id: str) -> Candidate:
    registry.source(source_id)
    match = next(
        (item for item in candidates(root, registry).candidates if item.source_id == source_id),
        None,
    )
    if match is None:
        raise IngestionError("Source is not in the reviewed acquisition shortlist")
    return match


def authorize(
    root: Path,
    registry: Registry,
    source_id: str,
    approval_ref: str | None = None,
    scope: Scope = "internal_analysis",
) -> Decision:
    """Reuse STEP 02/04 checks, including expiry and exact source identity."""
    try:
        decision = current_decision(root, registry, source_id)
        rights = official.authorize(
            root,
            registry,
            source_id,
            approval_ref if approval_ref is not None else decision.approval_ref if decision else "",
        )
        require_access(root, registry, source_id, scope)
    except (ValueError, OSError):
        raise IngestionBlocked(
            "BLOCKED_PERMISSION: source approval, license, scope, expiry "
            "and consistent audit required"
        ) from None
    return rights


def preflight(
    root: Path, registry: Registry, source_id: str, scope: Scope = "internal_analysis"
) -> dict:
    rights = authorize(root, registry, source_id, scope=scope)
    return {
        "status": "PASS",
        "source_id": source_id,
        "scope": scope,
        "approval_ref": rights.approval_ref,
        "file_read": False,
        "notice": "Preflight only; verified supplier and transfer evidence still required",
    }


def status(root: Path, registry: Registry, source_id: str) -> dict:
    item = candidate(root, registry, source_id)
    contact_history = events.history(root, source_id)
    contact_state = contact_history[-1][0].state if contact_history else "DISCOVERED"
    workflow_state = "BLOCKED"
    try:
        rights = authorize(root, registry, source_id)
        reception = "PERMISSION_READY"
        workflow_state = "APPROVED_FOR_SCOPE"
    except (PermissionError, ValueError, OSError):
        reception = "BLOCKED_PERMISSION"
        rights = None
        try:
            decision = current_decision(root, registry, source_id)
            if decision and decision.decision in {"REVOKED", "DENIED"}:
                workflow_state = "REVOKED" if decision.decision == "REVOKED" else "REJECTED"
        except (PermissionError, ValueError, OSError):
            pass  # Inconsistent permission remains BLOCKED, never a positive state.
    receipt_states = []
    if rights is not None:
        handoffs = base(root) / "handoffs"
        if handoffs.exists():
            for path in sorted(handoffs.iterdir()):
                handoff = Handoff.model_validate(store.read_json(safe_path(path, root)))
                if handoff.source_id == source_id and handoff.approval_ref == rights.approval_ref:
                    workflow_state = "READY_FOR_HANDOFF"
        receipts = base(root) / "receipts"
        if receipts.exists():
            for path in sorted(receipts.iterdir()):
                receipt = Receipt.model_validate(
                    store.read_json(safe_path(path / "receipt.json", root))
                )
                if receipt.handoff.source_id != source_id:
                    continue
                state = "RECEIVED_QUARANTINED"
                if receipt.permission != rights or receipt.source_registry_checksum != store.digest(
                    registry.source(source_id).model_dump()
                ):
                    receipt_states.append(
                        {"receipt_id": receipt.receipt_id, "last_recorded_state": "BLOCKED"}
                    )
                    continue
                receipt_hash = store.file_checksum(safe_path(path / "receipt.json", root))
                marker_path = verification_path(root, receipt.receipt_id, receipt_hash)
                if marker_path.exists():
                    documents, _ = store.bundle(marker_path)
                    marker = documents.get("verification.json", {})
                    if (
                        marker.get("receipt_checksum") != receipt_hash
                        or marker.get("permission_checksum") != store.digest(rights.model_dump())
                        or marker.get("states") != ["VERIFIED_RECEIPT", "READY_FOR_STEP04"]
                    ):
                        raise IngestionError("Verification audit differs from received snapshot")
                    reviewed_time(marker.get("verified_at", ""))
                    state = "READY_FOR_STEP04"
                receipt_states.append(
                    {"receipt_id": receipt.receipt_id, "last_recorded_state": state}
                )
            if receipt_states:
                workflow_state = (
                    "READY_FOR_STEP04"
                    if any(
                        entry["last_recorded_state"] == "READY_FOR_STEP04"
                        for entry in receipt_states
                    )
                    else "RECEIVED_QUARANTINED"
                    if any(
                        entry["last_recorded_state"] == "RECEIVED_QUARANTINED"
                        for entry in receipt_states
                    )
                    else "BLOCKED"
                )
    return {
        "status": reception,
        "source_id": source_id,
        "candidate": item.model_dump(),
        "source_role": registry.source(source_id).dataset_role,
        "domain_fit": registry.source(source_id).domain_fit,
        "real_dataset": "NOT_ESTABLISHED",
        "step04_handoff": "REQUIRES_VERIFIED_RECEIPT",
        "contact_state": contact_state,
        "workflow_state": workflow_state,
        "receipt_states": receipt_states,
        "payloads_read_or_verified_now": False,
        "scope": rights.allowed_scope if rights else [],
        "discovery_checksum": store.digest(item.model_dump()),
        "notice": "Candidate metadata is research, not an approval or proof of received data",
    }


def request_pack(root: Path, registry: Registry, source_id: str, output: Path) -> dict:
    item = candidate(root, registry, source_id)
    if ".." in output.parts:
        raise IngestionError("Request output traversal is not allowed")
    output = safe_path(output if output.is_absolute() else root / output, root)
    # The existing bundle helper writes JSON only; publish document drafts locally.
    store.private_directory(output.parent)
    if output.exists():
        raise IngestionError("Request package exists; choose a new output directory")
    sources = {
        "DATA_REQUEST.md": root / "docs/DATA_REQUEST_TEMPLATE.md",
        "REQUEST_CHECKLIST.md": root / "docs/REAL_DATA_REQUEST_CHECKLIST.md",
        "DATA_TRANSFER_SPEC.md": root / "docs/DATA_TRANSFER_SPEC.md",
    }
    with TemporaryDirectory(prefix=".request-", dir=output.parent) as temporary:
        work = Path(temporary)
        protect_directory(work)
        for name, path in sources.items():
            (work / name).write_bytes(safe_path(path, root).read_bytes())
        write_json(work / "source.json", item.model_dump())
        write_json(
            work / "checksums.json",
            {file.name: official.file_digest(file) for file in sorted(work.iterdir())},
        )
        work.rename(output)
    return {
        "status": "DRAFT_REQUEST_PACKAGE_CREATED",
        "source_id": source_id,
        "sent": False,
        "approval_granted": False,
    }


def base(root: Path) -> Path:
    return safe_path(root / "data/private/acquisition", root)


def evidence_path(root: Path, handoff_id: str) -> Path:
    return safe_path(base(root) / "handoffs" / (store.identifier(handoff_id) + ".json"), root)


def location(root: Path, receipt_id: str) -> Path:
    return safe_path(base(root) / "receipts" / store.identifier(receipt_id), root)


def verification_path(root: Path, receipt_id: str, receipt_checksum: str) -> Path:
    return safe_path(
        base(root)
        / "verification_audit"
        / store.identifier(receipt_id)
        / ("verified_" + receipt_checksum),
        root,
    )


def transport(path: Path) -> int:
    """Bounded UTF-8 container validation; schema/privacy remain mandatory STEP 04 gates."""

    def unique(pairs: list[tuple[str, object]]) -> dict:
        result = {}
        for key, value in pairs:
            if key in result:
                raise IngestionError("Duplicate JSONL keys")
            result[key] = value
        return result

    def nonfinite(value: str) -> None:
        raise IngestionError("Non-finite JSONL constants are invalid")

    count = 0
    try:
        if path.stat().st_size > MAX_BYTES:
            raise IngestionError("Input exceeds reception size limit")
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            if path.suffix == ".csv":
                reader = csv.reader(stream, strict=True)
                header = next(reader, [])
                if (
                    not header
                    or any(not name.strip() for name in header)
                    or len(set(header)) != len(header)
                ):
                    raise IngestionError("CSV header missing or duplicated")
                for row in reader:
                    if len(row) != len(header):
                        raise IngestionError("Malformed CSV record")
                    count += 1
                    if count > MAX_RECORDS:
                        raise IngestionError("Reception record limit exceeded")
            elif path.suffix == ".jsonl":
                for line in stream:
                    value = json.loads(line, object_pairs_hook=unique, parse_constant=nonfinite)
                    if not isinstance(value, dict) or not value:
                        raise IngestionError("JSONL records must be nonempty objects")
                    count += 1
                    if count > MAX_RECORDS:
                        raise IngestionError("Reception record limit exceeded")
            else:
                raise IngestionError("Only CSV and JSONL reception is supported")
    except (UnicodeError, csv.Error, json.JSONDecodeError):
        raise IngestionError("Invalid UTF-8 CSV/JSONL container") from None
    if not count:
        raise IngestionError("Empty reception file")
    return count


def receive(
    root: Path,
    registry: Registry,
    source_id: str,
    input_path: Path,
    approval_ref: str,
    handoff_id: str,
) -> dict:
    """Real entry point: authorization before inspecting any input file."""
    rights = authorize(root, registry, source_id, approval_ref)
    return _receive(root, registry, source_id, input_path, handoff_id, rights)


def _receive(
    root: Path,
    registry: Registry,
    source_id: str,
    input_path: Path,
    handoff_id: str,
    rights: Decision | None = None,
) -> dict:
    handoff = Handoff.model_validate(store.read_json(evidence_path(root, handoff_id)))
    synthetic = handoff.provenance == "SYNTHETIC"
    if synthetic:
        store.require_synthetic(root)
        if rights is not None:
            raise IngestionBlocked("Synthetic evidence cannot authorize real reception")
    elif rights is None or rights != authorize(root, registry, source_id, handoff.approval_ref):
        raise IngestionBlocked("Current matching permission required before reception")
    if (handoff.handoff_id, handoff.source_id) != (handoff_id, source_id):
        raise IngestionBlocked("Transfer evidence source or handoff identity mismatch")
    if ".." in input_path.parts:
        raise IngestionError("Input path traversal is not allowed")
    input_path = safe_path(input_path if input_path.is_absolute() else root / input_path)
    if not input_path.is_file() or input_path.suffix.lower() != handoff.file_format:
        raise IngestionError("Expected local CSV/JSONL file required")
    if input_path.stat().st_size != handoff.expected_bytes:
        raise IngestionError("Input size differs from authenticated transfer metadata")
    destination = location(root, handoff_id)
    store.private_directory(destination.parent)
    lock = base(root) / ".receive.lock"
    try:
        handle = lock.open("x")
    except FileExistsError:
        raise IngestionBlocked("Reception journal busy; review existing writer lock") from None
    try:
        with handle:
            if destination.exists():
                raise IngestionError("Immutable handoff ID already received")
            for path in sorted(destination.parent.iterdir()):
                previous = Receipt.model_validate(
                    store.read_json(safe_path(path / "receipt.json", root))
                )
                inventory = store.read_json(safe_path(path / "checksums.json", root), 65536)
                if not isinstance(inventory, dict) or inventory.get(
                    "receipt.json"
                ) != store.file_checksum(safe_path(path / "receipt.json", root)):
                    raise IngestionError("Existing receipt metadata integrity is inconsistent")
                if previous.handoff.source_id == source_id and (
                    previous.payload_sha256 == handoff.expected_sha256
                    or previous.handoff.source_export_ref == handoff.source_export_ref
                ):
                    raise IngestionError(
                        "Duplicate source export or payload; review previous receipt"
                    )
            with TemporaryDirectory(prefix=".receive-", dir=base(root)) as temporary:
                work = Path(temporary)
                protection = protect_directory(work)
                payload = work / ("payload" + handoff.file_format)
                checksum, size = hashlib.sha256(), 0
                with input_path.open("rb") as source, payload.open("xb") as target:
                    if os.name != "nt":
                        payload.chmod(0o600)
                    while block := source.read(65536):
                        size += len(block)
                        if size > MAX_BYTES or size > handoff.expected_bytes:
                            raise IngestionError("Input grew beyond authenticated size")
                        target.write(block)
                        checksum.update(block)
                    target.flush()
                    os.fsync(target.fileno())
                if (
                    size != handoff.expected_bytes
                    or checksum.hexdigest() != handoff.expected_sha256
                ):
                    raise IngestionError("Transfer SHA256 or size mismatch")
                count = transport(payload)
                receipt = Receipt(
                    format_version="acquisition-1",
                    receipt_id=handoff_id,
                    handoff=handoff,
                    handoff_checksum=store.digest(handoff.model_dump()),
                    permission=rights,
                    source_registry_checksum=store.digest(registry.source(source_id).model_dump()),
                    payload_sha256=checksum.hexdigest(),
                    payload_bytes=size,
                    record_count=count,
                    received_at=datetime.now(UTC).isoformat(),
                    storage_protection=protection,
                    state="RECEIVED_QUARANTINED",
                )
                write_json(work / "receipt.json", receipt.model_dump())
                write_json(
                    work / "checksums.json",
                    {
                        name: official.file_digest(work / name)
                        for name in (payload.name, "receipt.json")
                    },
                )
                if (
                    Handoff.model_validate(store.read_json(evidence_path(root, handoff_id)))
                    != handoff
                ):
                    raise IngestionBlocked("Human transfer evidence changed during reception")
                if (
                    not synthetic
                    and authorize(root, registry, source_id, handoff.approval_ref) != rights
                ):
                    raise IngestionBlocked("Permission changed during reception")
                work.rename(destination)
    finally:
        lock.unlink()
    return {
        "status": "RECEIVED_QUARANTINED",
        "receipt_id": handoff_id,
        "provenance": handoff.provenance,
        "record_count": count,
        "published": False,
        "privacy_cleared": False,
    }


def verify(root: Path, registry: Registry, receipt_id: str) -> dict:
    path = location(root, receipt_id)
    receipt = Receipt.model_validate(store.read_json(path / "receipt.json"))
    if receipt.handoff.provenance == "SYNTHETIC":
        store.require_synthetic(root)
    else:
        rights = authorize(root, registry, receipt.handoff.source_id, receipt.handoff.approval_ref)
        if rights != receipt.permission:
            raise IngestionBlocked("Receipt permission no longer matches current evidence")
    if receipt.receipt_id != receipt_id or receipt.source_registry_checksum != store.digest(
        registry.source(receipt.handoff.source_id).model_dump()
    ):
        raise IngestionError("Receipt source or registry snapshot mismatch")
    handoff = Handoff.model_validate(store.read_json(evidence_path(root, receipt_id)))
    if handoff != receipt.handoff or store.digest(handoff.model_dump()) != receipt.handoff_checksum:
        raise IngestionBlocked("Transfer evidence differs from immutable receipt")
    payload = safe_path(path / ("payload" + handoff.file_format), root)
    checksums = store.read_json(path / "checksums.json", 65536)
    expected = {payload.name, "receipt.json"}
    if (
        not isinstance(checksums, dict)
        or set(checksums) != expected
        or {item.name for item in path.iterdir()} != expected | {"checksums.json"}
    ):
        raise IngestionError("Acquisition file inventory mismatch")
    for name in expected:
        if store.file_checksum(safe_path(path / name, root), MAX_BYTES) != checksums[name]:
            raise IngestionError("Acquisition artifact checksum mismatch")
    if (
        payload.stat().st_size != receipt.payload_bytes
        or checksums[payload.name] != receipt.payload_sha256
    ):
        raise IngestionError("Payload differs from transfer SHA256 or size")
    if transport(payload) != receipt.record_count:
        raise IngestionError("Acquisition record count mismatch")
    synthetic = handoff.provenance == "SYNTHETIC"
    receipt_checksum = store.file_checksum(path / "receipt.json")
    marker_path = verification_path(root, receipt_id, receipt_checksum)
    marker = {
        "receipt_id": receipt_id,
        "receipt_checksum": receipt_checksum,
        "payload_checksum": receipt.payload_sha256,
        "permission_checksum": store.digest(receipt.permission.model_dump())
        if receipt.permission
        else None,
        "states": ["VERIFIED_RECEIPT", "READY_FOR_STEP04"]
        if not synthetic
        else ["VERIFIED_SYNTHETIC"],
        "provenance": handoff.provenance,
    }
    if marker_path.exists():
        documents, _ = store.bundle(marker_path)
        existing = documents.get("verification.json", {}).copy()
        reviewed_time(existing.pop("verified_at", ""))
        if set(documents) != {"verification.json"} or existing != marker:
            raise IngestionError("Verification audit changed")
    else:
        marker["verified_at"] = datetime.now(UTC).isoformat()
        store.publish(marker_path, {"verification.json": marker})
    return {
        "status": "VERIFIED_SYNTHETIC" if synthetic else "VERIFIED",
        "receipt_id": receipt_id,
        "source_id": handoff.source_id,
        "record_count": receipt.record_count,
        "provenance": handoff.provenance,
        "step04_handoff": "SYNTHETIC_ONLY" if synthetic else "READY",
        "published": False,
        "privacy_cleared": False,
        "input": str(payload.relative_to(root)),
        "approval_ref": handoff.approval_ref,
        "workflow_state": "SYNTHETIC_ONLY" if synthetic else "READY_FOR_STEP04",
        "audit_ref": "verified_" + receipt_checksum,
    }


def smoke(project_root: Path, registry: Registry) -> dict:
    """Offline synthetic receipt through STEP 04 preview; no real permission records."""
    with TemporaryDirectory(prefix="pfa-acquisition-synthetic-") as temporary:
        root = Path(temporary)
        with store.synthetic_session(root):
            (root / "configs").mkdir()
            write_json(root / "configs/permission_evidence.json", {"decisions": []})
            (root / "configs/permission_history.jsonl").write_text("")
            path = root / "data/synthetic/input.csv"
            store.private_directory(path.parent)
            fixture = project_root / "tests/fixtures/public_service_feedback_synthetic.csv"
            if official.file_digest(fixture) != official.SYNTHETIC_FIXTURE_SHA256:
                raise IngestionBlocked("Bundled synthetic fixture checksum changed")
            path.write_bytes(
                (project_root / "tests/fixtures/public_service_feedback_synthetic.csv").read_bytes()
            )
            handoff = Handoff(
                handoff_id="synthetic_handoff",
                source_id="synthetic_demo",
                approval_ref=None,
                source_export_ref="synthetic_export",
                supplier_reference="synthetic_no_supplier",
                reviewer_id="synthetic_simulation",
                evidence_reference="synthetic_no_approval",
                transfer_method="SYNTHETIC_LOCAL",
                expected_sha256=official.file_digest(path),
                expected_bytes=path.stat().st_size,
                file_format=".csv",
                reviewed_at=datetime.now(UTC).isoformat(),
                provenance="SYNTHETIC",
                human_verified=False,
            )
            store.private_directory(evidence_path(root, handoff.handoff_id).parent)
            write_json(evidence_path(root, handoff.handoff_id), handoff.model_dump())
            received = _receive(root, registry, "synthetic_demo", path, handoff.handoff_id)
            verified = verify(root, registry, handoff.handoff_id)
            # Existing STEP 04 synthetic boundary is retained; never label this real ingestion.
            staged = root / "data/synthetic/received.csv"
            staged.write_bytes((root / verified["input"]).read_bytes())
            from pfa.data.official_schema import ImportOptions
            from pfa.data.profiling import SYNTHETIC_KEY

            preview = official._ingest(
                root,
                registry,
                "synthetic_fixture",
                staged,
                None,
                SYNTHETIC_KEY,
                "preview",
                ImportOptions(),
                None,
                synthetic=True,
            )
            try:
                receive(root, registry, "authorized_agency_export", path, "missing", "blocked")
            except PermissionError:
                blocked = True
            else:
                raise IngestionError("Unauthorized reception was not blocked")
            result = {
                "status": "ACQUISITION_SMOKE_PASS_SYNTHETIC",
                "record_count": received["record_count"],
                "receipt_verified": True,
                "unauthorized_reception_blocked": blocked,
                "step04_preview": preview["status"],
                "published": False,
                "real_approvals_created": False,
            }
    result["temporary_storage_cleaned"] = not root.exists()
    return result
