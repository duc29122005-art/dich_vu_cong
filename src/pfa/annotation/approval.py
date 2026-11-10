"""Human taxonomy checkpoint. Flags never replace an existing verified decision record."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import model_validator

from pfa.annotation import pilot_store as store
from pfa.annotation.taxonomy import CHECKSUM, VERSION, load_taxonomy
from pfa.data.official import file_digest
from pfa.data.official_io import IngestionBlocked, IngestionError, safe_path
from pfa.data.registry import Identifier, Metadata


def reviewed_time(value: str) -> datetime:
    try:
        result = datetime.fromisoformat(value)
        if result.tzinfo is None or result > datetime.now(UTC):
            raise ValueError
    except (ValueError, TypeError):
        raise ValueError("A nonfuture timezone-aware human decision date is required") from None
    return result


class TaxonomyDecision(Metadata):
    decision_ref: Identifier
    taxonomy_version: Literal[VERSION]
    taxonomy_checksum: Literal[CHECKSUM]
    handbook_checksum: str
    reviewer_id: Identifier
    reviewer_role: Literal["research_owner", "domain_reviewer"]
    reviewed_at: str
    decision: Literal["APPROVED", "REJECTED", "SUPERSEDED"]
    evidence_reference: Identifier
    human_verified: bool

    @model_validator(mode="after")
    def human(self) -> "TaxonomyDecision":
        reviewed_time(self.reviewed_at)
        if not self.human_verified or self.reviewer_id in {"unknown", "pending"}:
            raise ValueError("Existing human verification required")
        if self.evidence_reference in {"unknown", "pending"}:
            raise ValueError("Protected approval evidence reference required")
        return self


def requests(root: Path, reference: str) -> Path:
    return safe_path(store.base(root) / "requests" / (store.identifier(reference) + ".json"), root)


def taxonomy_history(root: Path) -> list[tuple[TaxonomyDecision, str]]:
    history = safe_path(store.base(root) / "taxonomy_history", root)
    if not history.exists():
        return []
    previous, results = None, []
    for index, path in enumerate(sorted(history.iterdir()), 1):
        if path.name.startswith(".") or path.name != f"decision_{index:06d}":
            raise IngestionBlocked("Taxonomy audit history is locked or inconsistent")
        documents, checksum = store.bundle(path)
        event = documents.get("decision.json", {})
        decision = TaxonomyDecision.model_validate(event.get("decision"))
        if event.get("previous_checksum") != previous or any(
            decision.decision_ref == item.decision_ref for item, _ in results
        ):
            raise IngestionBlocked("Taxonomy audit chain is inconsistent")
        if results and reviewed_time(decision.reviewed_at) < reviewed_time(
            results[-1][0].reviewed_at
        ):
            raise IngestionBlocked("Taxonomy decisions must be chronological")
        current_request = TaxonomyDecision.model_validate(
            store.read_json(requests(root, decision.decision_ref))
        )
        if current_request != decision:
            raise IngestionBlocked("Taxonomy evidence differs from the recorded human decision")
        results.append((decision, checksum))
        previous = checksum
    return results


def record_taxonomy(root: Path, reference: str) -> dict:
    load_taxonomy(root)
    decision = TaxonomyDecision.model_validate(store.read_json(requests(root, reference)))
    if decision.decision_ref != reference or decision.handbook_checksum != file_digest(
        safe_path(root / "docs/ANNOTATION_GUIDELINES.md", root)
    ):
        raise IngestionBlocked("Decision must reference the exact current taxonomy and handbook")
    history = taxonomy_history(root)
    if any(item.decision_ref == reference for item, _ in history):
        raise IngestionError("Taxonomy decision already recorded")
    if history and reviewed_time(decision.reviewed_at) < reviewed_time(history[-1][0].reviewed_at):
        raise IngestionError("Decision predates current taxonomy history")
    store.publish(
        store.base(root) / "taxonomy_history" / f"decision_{len(history) + 1:06d}",
        {
            "decision.json": {
                "decision": decision.model_dump(),
                "previous_checksum": history[-1][1] if history else None,
            }
        },
    )
    return {
        "status": "HUMAN_DECISION_RECORDED",
        "decision": decision.decision,
        "taxonomy_version": VERSION,
        "taxonomy_checksum": CHECKSUM,
    }


def require_taxonomy(root: Path) -> str:
    load_taxonomy(root)
    history = taxonomy_history(root)
    if not history or history[-1][0].decision != "APPROVED":
        raise IngestionBlocked("BLOCKED_TAXONOMY: current human taxonomy approval required")
    decision, checksum = history[-1]
    if decision.handbook_checksum != file_digest(root / "docs/ANNOTATION_GUIDELINES.md"):
        raise IngestionBlocked("BLOCKED_TAXONOMY: approved handbook has changed")
    return checksum
