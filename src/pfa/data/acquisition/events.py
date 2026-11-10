"""Audited human contact milestones; usage approval remains exclusively in STEP 02."""

from pathlib import Path
from typing import Literal

from pydantic import model_validator

from pfa.annotation import pilot_store as store
from pfa.annotation.approval import reviewed_time
from pfa.data.official_io import IngestionBlocked, IngestionError, safe_path
from pfa.data.registry import Identifier, Metadata, Registry

State = Literal[
    "DISCOVERED",
    "CONTACT_PENDING",
    "REQUESTED",
    "PERMISSION_REVIEW",
    "APPROVED_FOR_SCOPE",
    "READY_FOR_HANDOFF",
    "RECEIVED_QUARANTINED",
    "VERIFIED_RECEIPT",
    "READY_FOR_STEP04",
    "REJECTED",
    "REVOKED",
    "BLOCKED",
    "NOT_AVAILABLE",
]


class ContactEvent(Metadata):
    event_ref: Identifier
    source_id: Identifier
    state: Literal["CONTACT_PENDING", "REQUESTED", "PERMISSION_REVIEW", "REJECTED", "NOT_AVAILABLE"]
    reviewer_id: Identifier
    evidence_reference: Identifier
    reviewed_at: str
    human_verified: Literal[True]

    @model_validator(mode="after")
    def verified(self) -> "ContactEvent":
        reviewed_time(self.reviewed_at)
        if any(
            value.lower() in {"unknown", "pending"}
            for value in (self.reviewer_id, self.evidence_reference)
        ):
            raise ValueError("Actual human contact evidence required")
        return self


def root_path(root: Path) -> Path:
    return safe_path(root / "data/private/acquisition/contact_audit", root)


def request_path(root: Path, reference: str) -> Path:
    return safe_path(root_path(root) / "requests" / (store.identifier(reference) + ".json"), root)


def history(root: Path, source_id: str) -> list[tuple[ContactEvent, str]]:
    path = safe_path(root_path(root) / store.identifier(source_id), root)
    result = []
    if not path.exists():
        return result
    for ordinal, directory in enumerate(sorted(path.iterdir()), 1):
        if directory.name != f"event_{ordinal:06d}":
            raise IngestionBlocked("Contact audit history is locked or inconsistent")
        documents, checksum = store.bundle(directory)
        record = documents.get("event.json", {})
        event = ContactEvent.model_validate(record.get("event"))
        if (
            event.source_id != source_id
            or event
            != ContactEvent.model_validate(store.read_json(request_path(root, event.event_ref)))
            or record.get("previous_checksum") != (result[-1][1] if result else None)
        ):
            raise IngestionBlocked("Contact audit evidence or history differs")
        if result and reviewed_time(event.reviewed_at) < reviewed_time(result[-1][0].reviewed_at):
            raise IngestionBlocked("Contact audit chronology invalid")
        if any(item.event_ref == event.event_ref for item, _ in result):
            raise IngestionBlocked("Repeated contact audit reference")
        result.append((event, checksum))
    return result


def record(root: Path, registry: Registry, source_id: str, event_ref: str) -> dict:
    registry.source(source_id)
    event = ContactEvent.model_validate(store.read_json(request_path(root, event_ref)))
    if (event.source_id, event.event_ref) != (source_id, event_ref):
        raise IngestionBlocked("Human contact event source/reference mismatch")
    previous = history(root, source_id)
    allowed = {
        "DISCOVERED": {"CONTACT_PENDING", "NOT_AVAILABLE", "REJECTED"},
        "CONTACT_PENDING": {"REQUESTED", "NOT_AVAILABLE", "REJECTED"},
        "REQUESTED": {"PERMISSION_REVIEW", "NOT_AVAILABLE", "REJECTED"},
        "PERMISSION_REVIEW": {"REQUESTED", "NOT_AVAILABLE", "REJECTED"},
        "REJECTED": {"CONTACT_PENDING"},
        "NOT_AVAILABLE": {"CONTACT_PENDING"},
    }
    before = previous[-1][0].state if previous else "DISCOVERED"
    if event.state not in allowed[before] or any(
        item.event_ref == event_ref for item, _ in previous
    ):
        raise IngestionError("Invalid contact milestone transition or duplicate reference")
    if previous and reviewed_time(event.reviewed_at) < reviewed_time(previous[-1][0].reviewed_at):
        raise IngestionError("Contact decision predates history")
    store.publish(
        root_path(root) / source_id / f"event_{len(previous) + 1:06d}",
        {
            "event.json": {
                "event": event.model_dump(),
                "previous_checksum": previous[-1][1] if previous else None,
            }
        },
    )
    return {
        "status": "HUMAN_CONTACT_EVENT_RECORDED",
        "state": event.state,
        "source_id": source_id,
        "usage_permission_granted": False,
    }
