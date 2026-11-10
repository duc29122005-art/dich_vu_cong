"""Local immutable entries and hash-linked events; coordinator-managed human evidence."""

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import Field

from pfa.annotation import approval
from pfa.annotation import pilot_store as store
from pfa.data.official_io import IngestionBlocked, IngestionError
from pfa.data.registry import Metadata
from pfa.ml import model_adapters


class Authorization(Metadata):
    action: str
    target_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reviewer_id: str = Field(pattern=r"^[a-zA-Z][a-zA-Z0-9_]{1,79}$")
    reviewer_role: Literal[
        "research_supervisor", "data_steward", "independent_reviewer", "student_researcher"
    ]
    evidence_reference: str = Field(pattern=r"^[a-zA-Z][a-zA-Z0-9_]{2,79}$")
    reviewed_at: str
    expires_at: str
    decision: str
    human_verified: bool


def base(root: Path) -> Path:
    return store.safe_path(root / "data/private/model_registry", root)


def authorize(root: Path, reference: str | None, action: str, target: str) -> dict:
    if not reference or store.is_synthetic(root):
        raise IngestionBlocked("Existing explicit human authorization required")
    path = base(root) / "requests" / (store.identifier(reference) + ".json")
    try:
        evidence = Authorization.model_validate(store.read_json(path))
        approval.reviewed_time(evidence.reviewed_at)
        expiry = datetime.fromisoformat(evidence.expires_at)
    except (ValueError, OSError):
        raise IngestionBlocked("Human evidence missing or invalid") from None
    if (
        evidence.action != action
        or evidence.target_sha256 != target
        or evidence.decision != "APPROVED"
        or not evidence.human_verified
        or expiry.tzinfo is None
        or expiry <= datetime.now(UTC)
        or evidence.reviewer_id.lower() in {"unknown", "pending", "synthetic", "demo"}
        or evidence.evidence_reference.lower() in {"unknown", "pending", "synthetic", "demo"}
    ):
        raise IngestionBlocked("Human authorization expired, revoked or incompatible")
    return {**evidence.model_dump(), "reference": reference}


def namespace(root, demo):
    if demo:
        store.require_synthetic(root)
    return base(root) / ("demo" if demo else "research")


def register(root, registry, run_id, family, entry_id=None) -> dict:
    descriptor = model_adapters.describe(root, registry, run_id, family)
    demo = descriptor["dataset"]["dataset_type"] == "SYNTHETIC"
    identity = store.identifier(entry_id or (run_id + "_" + family))
    record = {
        "registry_version": "registry-1",
        "run_id": identity,
        "status": "DEMO_ONLY" if demo else "CANDIDATE",
        "model": descriptor,
        "registered_at": datetime.now(UTC).isoformat(),
        "approval_references": [],
        "evaluation_provenance": None,
    }
    store.publish(namespace(root, demo) / "entries" / identity, {"record.json": record})
    return record


def inspect(root, registry, run_id, demo=False):
    documents, _ = store.bundle(namespace(root, demo) / "entries" / store.identifier(run_id))
    record = documents["record.json"]
    current = model_adapters.describe(
        root, registry, record["model"]["artifact_run_id"], record["model"]["family"]
    )
    if (
        record["run_id"] != run_id
        or current != record["model"]
        or demo != (current["dataset"]["dataset_type"] == "SYNTHETIC")
    ):
        raise IngestionError("Registry artifact provenance or namespace mismatch")
    return record


def entries(root, registry, demo=False):
    path = namespace(root, demo) / "entries"
    return (
        [inspect(root, registry, item.name, demo) for item in sorted(path.iterdir())]
        if path.exists()
        else []
    )


def history(root, demo=False):
    path = namespace(root, demo) / "events"
    events, previous = [], None
    if path.exists():
        for item in sorted(path.iterdir()):
            if not re.fullmatch(r"event_[0-9]{8}", item.name):
                raise IngestionError("Unexpected registry history file")
            documents, checksum = store.bundle(item)
            event = documents["event.json"]
            if event["previous_sha256"] != previous or event["sequence"] != len(events) + 1:
                raise IngestionError("Registry history chain changed")
            events.append(event)
            previous = checksum
    return events, previous


def event(root, demo, action, record, evidence=None, evaluation=None):
    events, previous = history(root, demo)
    document = {
        "sequence": len(events) + 1,
        "previous_sha256": previous,
        "action": action,
        "run_id": record["run_id"],
        "task": record["model"]["task"],
        "record_sha256": store.digest(record),
        "authorization": evidence,
        "evaluation": evaluation,
        "at": datetime.now(UTC).isoformat(),
    }
    store.publish(
        namespace(root, demo) / "events" / f"event_{len(events) + 1:08d}", {"event.json": document}
    )
    return document


def research_approve(root, registry, run_id, evaluation_id, approval_ref):
    record = inspect(root, registry, run_id)
    documents, checksum = store.bundle(
        base(root) / "final_results" / store.identifier(evaluation_id)
    )
    report = documents["report.json"]
    if (
        report.get("dataset_type") != "RESEARCH"
        or report.get("status") != "COMPLETED"
        or run_id not in report.get("selected_by_task", {}).values()
        or run_id not in report.get("models", {})
        or not report["models"].get(run_id, {}).get("metrics")
        or report["models"][run_id]["descriptor_sha256"] != store.digest(record["model"])
    ):
        raise IngestionBlocked("Genuine final evaluation provenance required")
    target = store.digest({"record": store.digest(record), "evaluation": checksum})
    evidence = authorize(root, approval_ref, "RESEARCH_APPROVAL", target)
    return event(
        root,
        False,
        "RESEARCH_APPROVED",
        record,
        evidence,
        {"id": evaluation_id, "sha256": checksum, "approval_ref": approval_ref},
    )


def activate(root, registry, run_id, *, demo=False, approval_ref=None, rollback=False):
    record = inspect(root, registry, run_id, demo)
    events, _ = history(root, demo)
    previous = [e for e in events if e["run_id"] == run_id]
    if rollback and not any(e["action"] in {"ACTIVE", "ROLLBACK"} for e in previous):
        raise IngestionBlocked("Rollback target was never active")
    evidence = None
    if not demo:
        approved = [e for e in previous if e["action"] == "RESEARCH_APPROVED"]
        if not approved:
            raise IngestionBlocked(
                "Research approval and final evaluation required before promotion"
            )
        latest = approved[-1]
        documents, checksum = store.bundle(
            base(root) / "final_results" / latest["evaluation"]["id"]
        )
        if (
            checksum != latest["evaluation"]["sha256"]
            or documents["report.json"]["dataset_type"] != "RESEARCH"
        ):
            raise IngestionBlocked("Approved evaluation changed")
        research_target = store.digest({"record": store.digest(record), "evaluation": checksum})
        authorize(root, latest["evaluation"]["approval_ref"], "RESEARCH_APPROVAL", research_target)
        # Current human authorization must still be valid at promotion time.
        evidence = authorize(
            root,
            approval_ref,
            "ROLLBACK" if rollback else "PRODUCTION_PROMOTION",
            research_target,
        )
    return event(root, demo, "ROLLBACK" if rollback else "ACTIVE", record, evidence)


def active(root, registry, task, demo=False):
    events, _ = history(root, demo)
    eligible = [e for e in events if e["task"] == task and e["action"] in {"ACTIVE", "ROLLBACK"}]
    if not eligible:
        raise IngestionError("NOT_AVAILABLE: no active registered model")
    selected = eligible[-1]
    record = inspect(root, registry, selected["run_id"], demo)
    if selected["record_sha256"] != store.digest(record):
        raise IngestionError("Active registry binding changed")
    if not demo:
        evidence = selected["authorization"]
        approvals = [
            e
            for e in events
            if e["run_id"] == record["run_id"] and e["action"] == "RESEARCH_APPROVED"
        ]
        if not approvals:
            raise IngestionBlocked("Active model lacks research approval")
        provenance = approvals[-1]["evaluation"]
        _, checksum = store.bundle(base(root) / "final_results" / provenance["id"])
        if checksum != provenance["sha256"]:
            raise IngestionError("Active evaluation changed")
        authorize(
            root,
            provenance["approval_ref"],
            "RESEARCH_APPROVAL",
            store.digest({"record": store.digest(record), "evaluation": checksum}),
        )
        authorize(
            root,
            evidence["reference"],
            "ROLLBACK" if selected["action"] == "ROLLBACK" else "PRODUCTION_PROMOTION",
            store.digest({"record": store.digest(record), "evaluation": checksum}),
        )
    return record


def view(root, registry, run_id, demo=False):
    record = inspect(root, registry, run_id, demo)
    events, _ = history(root, demo)
    relevant = [e for e in events if e["run_id"] == run_id]
    if any(e["record_sha256"] != store.digest(record) for e in relevant):
        raise IngestionError("History record binding changed")
    state = relevant[-1]["action"] if relevant else record["status"]
    return {"record": record, "lifecycle_status": state, "history": relevant}


def unique_id(prefix):
    return prefix + "_" + uuid4().hex
