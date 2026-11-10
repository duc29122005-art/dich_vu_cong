"""Deterministic decision support, separate from usage authorization."""

from dataclasses import dataclass
from pathlib import Path

from pfa.data.permissions import current_decision, permitted_scopes
from pfa.data.registry import Registry


@dataclass(frozen=True)
class Score:
    points: int
    weight: int
    rationale: str


def assess(root: Path, registry: Registry, source_id: str) -> dict:
    """Score 0–5 per dimension; unknown evidence earns zero, never approval."""
    source = registry.source(source_id)
    scopes = permitted_scopes(root, registry, source)
    decision = current_decision(root, registry, source_id)
    domain = {"DIRECT": 5, "ADJACENT": 2, "INDIRECT": 1, "SYNTHETIC": 0, "UNKNOWN": 0}
    scores = {
        "domain_relevance": Score(
            domain[source.domain_fit],
            30,
            "Declared domain fit from project brief; not independently verified: "
            + source.domain_fit,
        ),
        "permission_privacy": Score(
            5 if scopes else 0,
            30,
            "Human-reviewed license, privacy, retention and scope evidence recorded."
            if scopes
            else "No effective reviewed permission; no positive credit.",
        ),
        "label_suitability": Score(
            0, 20, "No inspected label schema or label quality evidence; UNKNOWN."
        ),
        "coverage_metadata": Score(
            0, 10, "No verified sample counts, representativeness or coverage; UNKNOWN."
        ),
        "reproducibility": Score(
            1 if source.source_url != "UNKNOWN" else 0,
            10,
            "Brief supplies a source locator only; version/checksum/splits UNKNOWN."
            if source.source_url != "UNKNOWN"
            else "No versioned dataset locator; UNKNOWN.",
        ),
    }
    blockers = []
    if source.license_status == "UNKNOWN":
        blockers.append(
            "Registry license remains UNKNOWN; reviewer must verify scope-specific rights"
        )
    if not scopes:
        blockers.append("No permitted usage scope; dataset access is blocked")
    if source.pii_risk in {"UNKNOWN", "HIGH"} and not scopes:
        blockers.append("Privacy review and de-identification conditions required")
    if source.permission_status in {"DENIED", "REVOKED"} or (
        decision and decision.decision in {"DENIED", "REVOKED"}
    ):
        recommendation = "BLOCKED"
    elif source.dataset_role in {"REFERENCE", "AGGREGATE"}:
        recommendation = "NOT_SUITABLE"
        blockers.append("Not suitable as individual citizen-feedback classification labels")
    elif scopes:
        recommendation = "APPROVED_FOR_SCOPE"
    else:
        recommendation = "PENDING_REVIEW"
    return {
        "source_id": source_id,
        "scores": {
            name: {"points": item.points, "weight": item.weight, "rationale": item.rationale}
            for name, item in scores.items()
        },
        "weighted_total": sum(item.points * item.weight / 5 for item in scores.values()),
        "recommendation": recommendation,
        "permitted_scope": scopes,
        "blockers": blockers,
        "notice": "Decision support only; scores do not establish legal authorization.",
    }
