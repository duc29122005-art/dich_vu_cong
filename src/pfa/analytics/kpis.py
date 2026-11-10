"""One feedback is one unit; small positive cells suppress the whole partition."""

from collections import Counter
from typing import get_args

from pfa.analytics.schemas import Cell, Metric
from pfa.annotation.taxonomy import Sentiment, Severity, Topic

LABELS = {
    "topic": get_args(Topic),
    "sentiment": get_args(Sentiment),
    "severity": get_args(Severity),
}
REVIEWED = {"REVIEWED", "ADJUDICATED"}


def labels(row, basis):
    if basis == "prediction":
        return row.ai
    allowed = row.state == "ADJUDICATED" if basis == "adjudicated" else row.state in REVIEWED
    return row.human if allowed else {}


def metric(numerator, denominator, minimum):
    suppressed = (
        0 < denominator < minimum
        or 0 < numerator < minimum
        or 0 < denominator - numerator < minimum
    )
    return Metric(
        numerator=None if suppressed else numerator,
        denominator=None if suppressed else denominator,
        share=None if suppressed or denominator == 0 else numerator / denominator,
        suppressed=suppressed,
    )


def cells(counts, codes, minimum):
    total = sum(counts.values())
    suppress = any(0 < value < minimum for value in counts.values())
    return [
        Cell(
            code=code,
            count=None if suppress else counts[code],
            share=None if suppress or not total else counts[code] / total,
            suppressed=suppress,
        )
        for code in codes
    ]


def summarize(rows, basis, minimum):
    n = len(rows)
    selected = [labels(row, basis) for row in rows]
    distributions, metrics = {}, {}
    for task, codes in LABELS.items():
        all_codes = [*codes, "unknown", "missing"] if task == "severity" else [*codes, "missing"]
        counts = Counter(values.get(task) or "missing" for values in selected)
        distributions[task] = cells(counts, all_codes, minimum)
        metrics[task + "_missing"] = metric(counts["missing"], n, minimum)
        metrics[task + "_coverage"] = metric(sum(counts[code] for code in codes), n, minimum)
        if task in {"sentiment", "severity"}:
            name, code = (
                ("negative_share", "negative")
                if task == "sentiment"
                else ("high_severity_share", "high")
            )
            metrics[name] = metric(counts[code], sum(counts[c] for c in codes), minimum)
            if metrics[task + "_coverage"].suppressed:
                metrics[name] = Metric(
                    numerator=None, denominator=None, share=None, suppressed=True
                )
        if task == "severity":
            metrics["severity_unknown"] = metric(counts["unknown"], n, minimum)
    comparable = corrected = 0
    for row in rows:
        pairs = [
            (row.human.get(task), row.reference_ai.get(task))
            for task, codes in LABELS.items()
            if row.state in REVIEWED
            and row.human.get(task) in codes
            and row.reference_ai.get(task) in codes
        ]
        comparable += bool(pairs)
        corrected += bool(pairs) and any(a != b for a, b in pairs)
    metrics.update(
        {
            "review_required": metric(sum(r.requires_review for r in rows), n, minimum),
            "review_pending": metric(sum(r.state not in REVIEWED for r in rows), n, minimum),
            "reviewed": metric(sum(r.state in REVIEWED for r in rows), n, minimum),
            "adjudicated": metric(sum(r.state == "ADJUDICATED" for r in rows), n, minimum),
            "corrections": metric(corrected, comparable, minimum),
            "correction_comparison_coverage": metric(comparable, n, minimum),
        }
    )
    if metrics["correction_comparison_coverage"].suppressed:
        metrics["corrections"] = Metric(
            numerator=None, denominator=None, share=None, suppressed=True
        )
    for task, codes in LABELS.items():
        metrics[task + "_ai_coverage"] = metric(
            sum(r.ai.get(task) in codes for r in rows), n, minimum
        )
        metrics[task + "_reviewed_coverage"] = metric(
            sum(r.state in REVIEWED and r.human.get(task) in codes for r in rows), n, minimum
        )
    distributions["review_status"] = cells(
        Counter(r.state for r in rows),
        ["PENDING_REVIEW", "IN_REVIEW", "REVIEWED", "NEEDS_ADJUDICATION", "ADJUDICATED"],
        minimum,
    )
    complaint = Counter(
        v["topic"]
        for v in selected
        if v.get("sentiment") == "negative" and v.get("topic") in LABELS["topic"]
    )
    # Keep the complement: omitting it could reveal a small conditional cohort by subtraction.
    complaint_partition = complaint + Counter(not_comparable=n - sum(complaint.values()))
    complaint_cells = cells(complaint_partition, [*LABELS["topic"], "not_comparable"], minimum)
    top = (
        max(complaint, key=lambda code: (complaint[code], -LABELS["topic"].index(code)))
        if complaint
        else None
    )
    if any(c.suppressed for c in complaint_cells):
        top = None
    distributions["complaint_topic"] = complaint_cells
    cross = Counter(
        v["sentiment"] + ":" + v["severity"]
        for v in selected
        if v.get("sentiment") in LABELS["sentiment"] and v.get("severity") in LABELS["severity"]
    )
    cross["missing_pair"] = n - sum(cross.values())
    cross_tab = cells(
        cross,
        [a + ":" + b for a in LABELS["sentiment"] for b in LABELS["severity"]] + ["missing_pair"],
        minimum,
    )
    return metrics, distributions, top, cross_tab
