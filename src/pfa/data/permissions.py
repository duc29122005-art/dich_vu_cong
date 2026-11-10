"""Human-reviewed permission records and a fail-closed local audit trail."""

import json
import os
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from pfa.data.registry import Identifier, Metadata, Registry, Scope, Source, Text


class Decision(Metadata):
    """Non-sensitive metadata only; evidence itself stays in protected storage."""

    approval_ref: Identifier
    source_id: Identifier
    reviewer: Text
    evidence_reference: Identifier
    decision_date: Text
    decision: Literal["APPROVED", "DENIED", "REVOKED"]
    allowed_scope: list[Scope]
    human_verified: bool
    license_verified: bool
    privacy_verified: bool
    retention_policy: Text
    expires_on: Text | None = None

    @model_validator(mode="after")
    def verified_decision(self) -> "Decision":
        when = date.fromisoformat(self.decision_date)
        if self.decision_date != when.isoformat():
            raise ValueError("Decision date must use YYYY-MM-DD")
        if when > date.today():
            raise ValueError("Decision date cannot be in the future")
        if self.expires_on is not None:
            expiry = date.fromisoformat(self.expires_on)
            if self.expires_on != expiry.isoformat() or expiry < when:
                raise ValueError("Expiry must be an ISO date on or after the decision date")
        if not self.human_verified or self.reviewer.upper() == "UNKNOWN":
            raise ValueError("A responsible human must verify the decision")
        if len(set(self.allowed_scope)) != len(self.allowed_scope):
            raise ValueError("Duplicate usage scopes")
        if self.decision == "APPROVED":
            if not self.allowed_scope or not self.license_verified or not self.privacy_verified:
                raise ValueError("Approval requires scope, license, and privacy verification")
            if self.retention_policy.upper() == "UNKNOWN":
                raise ValueError("Approval requires a retention policy")
        elif self.allowed_scope:
            raise ValueError("Denied or revoked decisions cannot allow usage")
        return self


class EvidenceRegister(Metadata):
    decisions: list[Decision] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_references(self) -> "EvidenceRegister":
        refs = [item.approval_ref for item in self.decisions]
        if len(refs) != len(set(refs)):
            raise ValueError("Duplicate approval references")
        return self


def load_evidence(root: Path, registry: Registry) -> EvidenceRegister:
    """Require existing, validated human metadata, not just a CLI reference."""
    records = EvidenceRegister.model_validate(
        json.loads((root / "configs/permission_evidence.json").read_text(encoding="utf-8"))
    )
    for record in records.decisions:
        registry.source(record.source_id)
    return records


def history(root: Path) -> list[Decision]:
    """Fail on missing/corrupt history rather than silently discarding decisions."""
    path = root / "configs/permission_history.jsonl"
    records = [
        Decision.model_validate(json.loads(line))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    refs = [record.approval_ref for record in records]
    if len(refs) != len(set(refs)):
        raise ValueError("Duplicate history references")
    return records


def record_decision(root: Path, registry: Registry, source_id: str, approval_ref: str) -> Decision:
    """Append a verified snapshot under an exclusive local writer lock."""
    registry.source(source_id)
    evidence = load_evidence(root, registry)
    decision = next(
        (
            item
            for item in evidence.decisions
            if item.approval_ref == approval_ref and item.source_id == source_id
        ),
        None,
    )
    if decision is None:
        raise PermissionError("Existing verified evidence record required")
    lock = root / "configs/permission_history.lock"
    # ponytail: local exclusive lock; use transactional storage for multi-host writers.
    lock_stream = lock.open("x", encoding="utf-8")
    try:
        with lock_stream:
            records = history(root)
            if any(item.approval_ref == approval_ref for item in records):
                raise ValueError("Decision already recorded; use a new reference for changes")
            previous = [item for item in records if item.source_id == source_id]
            if previous and decision.decision_date < previous[-1].decision_date:
                raise ValueError("Decision predates current source decision")
            with (root / "configs/permission_history.jsonl").open("a+", encoding="utf-8") as stream:
                start = stream.tell()
                try:
                    stream.write(json.dumps(decision.model_dump()) + "\n")
                    stream.flush()
                    os.fsync(stream.fileno())
                except OSError:
                    stream.truncate(start)
                    stream.flush()
                    raise
    finally:
        lock.unlink()
    return decision


def current_decision(root: Path, registry: Registry, source_id: str) -> Decision | None:
    """Require the latest snapshot to still match its reviewed evidence record."""
    registry.source(source_id)
    if (root / "configs/permission_history.lock").exists():
        raise PermissionError("Permission journal is locked; review/retry required")
    evidence = load_evidence(root, registry)
    records = history(root)
    for record in records:
        registry.source(record.source_id)
    matching = [item for item in records if item.source_id == source_id]
    if not matching:
        return None
    latest = matching[-1]
    if latest not in evidence.decisions:
        raise PermissionError("Audit snapshot differs from reviewed evidence")
    return latest


def permitted_scopes(root: Path, registry: Registry, source: Source) -> list[Scope]:
    """Return only explicitly reviewed scopes; metadata alone grants nothing."""
    decision = current_decision(root, registry, source.source_id)
    if source.permission_status in {"DENIED", "REVOKED"}:
        return []
    if decision is None or decision.decision != "APPROVED":
        return []
    if decision.expires_on is not None and date.fromisoformat(decision.expires_on) < date.today():
        return []
    return decision.allowed_scope


def require_access(root: Path, registry: Registry, source_id: str, scope: Scope) -> None:
    """Gate future acquisition/processing code; no downloader is implemented."""
    source = registry.source(source_id)
    if scope not in permitted_scopes(root, registry, source):
        raise PermissionError("Requested dataset usage is not authorized")
