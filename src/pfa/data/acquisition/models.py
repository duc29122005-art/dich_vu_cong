"""Non-sensitive source research and protected handoff contracts."""

from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from pfa.annotation.approval import reviewed_time
from pfa.data.permissions import Decision
from pfa.data.registry import Identifier, Metadata, Text

Sha256 = Annotated[str, StringConstraints(strict=True, pattern=r"^[a-f0-9]{64}$")]
MAX_BYTES = 20 * 1024**2
MAX_RECORDS = 10000


class Candidate(Metadata):
    source_id: Identifier
    data_owner: Text
    source_url: Text
    contact_route: Text
    dataset_relevance: Text
    available_fields: list[Text] = Field(min_length=1)
    expected_sample_count: Text
    requested_sample_count: Text
    time_coverage: Text
    license_status: Literal["UNKNOWN", "VERIFIED"]
    permission_status: Literal["PENDING", "APPROVED", "DENIED", "REVOKED", "UNKNOWN"]
    pii_risk: Literal["UNKNOWN", "LOW", "MEDIUM", "HIGH"]
    acquisition_method: Text
    next_human_action: Text
    evidence_references: list[Text] = Field(min_length=1)
    contact_status: Literal["UNKNOWN", "UNVERIFIED", "VERIFIED"] = "UNKNOWN"
    data_format: Text = "UNKNOWN"
    terms_evidence_ref: Text = "UNKNOWN"
    reviewed_by: Text = "UNKNOWN"
    last_checked: Text = "UNKNOWN"


class DiscoverySlot(Metadata):
    slot_id: Literal["licensed_open_feedback"]
    source_id: None = None
    source_url: Literal["UNKNOWN"] = "UNKNOWN"
    verification: Literal["NOT_AVAILABLE"] = "NOT_AVAILABLE"
    next_action: Text


class Candidates(Metadata):
    research_date: Text
    method: Text
    candidates: list[Candidate]
    discovery_slots: list[DiscoverySlot] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique(self) -> "Candidates":
        if len({item.source_id for item in self.candidates}) != len(self.candidates):
            raise ValueError("Duplicate candidate source IDs")
        return self


class Handoff(Metadata):
    handoff_id: Identifier
    source_id: Identifier
    approval_ref: Identifier | None
    source_export_ref: Identifier
    source_manifest_ref: Identifier | None = None
    supplier_reference: Identifier
    reviewer_id: Identifier
    evidence_reference: Identifier
    transfer_method: Literal["APPROVED_SECURE_CHANNEL", "APPROVED_OFFLINE_MEDIA", "SYNTHETIC_LOCAL"]
    expected_sha256: Sha256
    expected_bytes: int = Field(gt=0, le=MAX_BYTES)
    file_format: Literal[".csv", ".jsonl"]
    reviewed_at: Text
    provenance: Literal["REAL_EXTERNAL", "SYNTHETIC"]
    human_verified: bool

    @model_validator(mode="after")
    def reviewed(self) -> "Handoff":
        reviewed_time(self.reviewed_at)
        if any(
            value.lower() in {"unknown", "pending"}
            for value in (
                self.source_export_ref,
                self.supplier_reference,
                self.reviewer_id,
                self.evidence_reference,
            )
        ):
            raise ValueError(
                "Verified supplier, human reviewer and protected transfer evidence required"
            )
        if self.provenance == "REAL_EXTERNAL":
            if (
                not self.human_verified
                or self.approval_ref is None
                or self.transfer_method == "SYNTHETIC_LOCAL"
            ):
                raise ValueError("Existing human-verified transfer and source approval required")
        elif (
            self.human_verified
            or self.approval_ref is not None
            or self.transfer_method != "SYNTHETIC_LOCAL"
            or self.source_id != "synthetic_demo"
        ):
            raise ValueError("Synthetic handoff must never impersonate real permission")
        return self


class Receipt(Metadata):
    format_version: Literal["acquisition-1"]
    receipt_id: Identifier
    handoff: Handoff
    handoff_checksum: Sha256
    permission: Decision | None
    source_registry_checksum: Sha256
    payload_sha256: Sha256
    payload_bytes: int = Field(gt=0, le=MAX_BYTES)
    record_count: int = Field(gt=0, le=MAX_RECORDS)
    received_at: Text
    storage_protection: Literal["WINDOWS_OWNER_SYSTEM_ACL", "POSIX_0700_0600"]
    state: Literal["RECEIVED_QUARANTINED"]

    @model_validator(mode="after")
    def bound(self) -> "Receipt":
        reviewed_time(self.received_at)
        if (self.receipt_id, self.payload_sha256, self.payload_bytes) != (
            self.handoff.handoff_id,
            self.handoff.expected_sha256,
            self.handoff.expected_bytes,
        ):
            raise ValueError("Receipt differs from verified transfer evidence")
        if self.handoff.provenance == "REAL_EXTERNAL":
            if self.permission is None or (
                self.permission.source_id,
                self.permission.approval_ref,
            ) != (self.handoff.source_id, self.handoff.approval_ref):
                raise ValueError("Receipt source and permission binding invalid")
        elif self.permission is not None:
            raise ValueError("Synthetic receipts cannot contain real permission")
        return self
