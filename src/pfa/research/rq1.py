"""Case-level descriptive topic analysis; never a citizen-population estimate."""

from collections import Counter

from pfa.annotation.agreement import TASKS
from pfa.data.official_io import IngestionError
from pfa.research.statistics import ratio


def analyze(cases, basis):
    if len({c.case_id for c in cases}) != len(cases):
        raise IngestionError("RQ1 duplicate cases rejected")
    if any(c.basis != basis for c in cases):
        raise IngestionError("RQ1 label bases cannot be mixed")
    total = len(cases)
    counts = Counter(c.labels.topic for c in cases)
    known = sum(counts[t] for t in TASKS["topic"])
    dates = [c.event_time for c in cases if c.event_time is not None]
    partitions = {}
    for field in ("source_id", "agency", "domain"):
        # Metadata is a protected local research table, not a public dashboard export.
        partitions[field] = [
            {"code": code, **ratio(count, total)}
            for code, count in sorted(
                Counter(getattr(c, field) or "missing" for c in cases).items()
            )
        ]
    return {
        "status": "DESCRIPTIVE" if cases else "INSUFFICIENT_EVIDENCE",
        "basis": basis,
        "total_eligible_cases": total,
        "topics": [
            {
                "label": t,
                **ratio(counts[t], total),
                "known_label_share": counts[t] / known if known else None,
            }
            for t in TASKS["topic"]
        ],
        "coverage": ratio(known, total),
        "missing_labels": ratio(total - known, total),
        "partitions": partitions,
        "missing_event_time": ratio(total - len(dates), total),
        "time_min": min(dates).isoformat() if dates else None,
        "time_max": max(dates).isoformat() if dates else None,
        "uncertainty": {
            "status": "NOT_ESTIMATED",
            "interval": None,
            "reason": "NO_PROBABILITY_SAMPLING_OR_TARGET_POPULATION_DESIGN",
        },
        "limitations": [
            "Observed feedback corpus only; not citizen population prevalence",
            "Complaint frequency alone does not measure agency service quality",
        ],
    }
