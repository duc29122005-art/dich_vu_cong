"""Cohen's kappa from matched independent annotations; no scientific claims or label changes."""

from collections import Counter
from typing import get_args

from pfa.annotation.schema import Annotation
from pfa.annotation.taxonomy import Sentiment, Severity, Topic
from pfa.data.official_io import IngestionError

TASKS = {"topic": get_args(Topic), "sentiment": get_args(Sentiment), "severity": get_args(Severity)}
EXCLUDED = {"OUT_OF_SCOPE", "UNLABELABLE"}


def cohen(pairs: list[tuple[str, str]], labels: tuple[str, ...]) -> dict:
    """Use integer marginals for stable undefined detection; return null, never a fake kappa."""
    matrix = [[0 for _ in labels] for _ in labels]
    left, right = Counter(), Counter()
    for a, b in pairs:
        if a not in labels or b not in labels:
            raise IngestionError("Agreement received an invalid supervised label")
        matrix[labels.index(a)][labels.index(b)] += 1
        left[a] += 1
        right[b] += 1
    n = len(pairs)
    agrees = sum(matrix[i][i] for i in range(len(labels)))
    expected = sum(left[label] * right[label] for label in labels)
    denominator = n * n - expected
    kappa = (n * agrees - expected) / denominator if denominator else None
    return {
        "comparable_pairs": n,
        "agreement_count": agrees,
        "disagreement_count": n - agrees,
        "raw_agreement_percent": 100 * agrees / n if n else None,
        "kappa": kappa,
        "undefined_reason": "NO_COMPARABLE_PAIRS"
        if not n
        else "SINGLE_LABEL_DEGENERACY"
        if not denominator
        else None,
        "labels": list(labels),
        "confusion_matrix": matrix,
        "class_distribution_a": {label: left[label] for label in labels},
        "class_distribution_b": {label: right[label] for label in labels},
        "rare_classes": [label for label in labels if min(left[label], right[label]) < 5],
    }


def calculate(
    annotations_a: list[Annotation],
    annotations_b: list[Annotation],
    expected_ids: list[str],
    *,
    synthetic: bool,
) -> dict:
    """Review states are reported separately; supplied comparable labels remain task-specific."""
    expected = set(expected_ids)
    if len(expected) != len(expected_ids):
        raise IngestionError("Pilot contains duplicate identifiers")
    sides = []
    contexts = {
        (
            item.dataset_version,
            item.taxonomy_version,
            item.taxonomy_checksum,
            item.source_id,
            item.dataset_type,
        )
        for item in [*annotations_a, *annotations_b]
    }
    if len(contexts) > 1 or any(
        item.dataset_type != ("SYNTHETIC" if synthetic else "RESEARCH")
        for item in [*annotations_a, *annotations_b]
    ):
        raise IngestionError("Agreement source, taxonomy or provenance mismatch")
    for records in (annotations_a, annotations_b):
        mapping = {item.feedback_id: item for item in records}
        if len(mapping) != len(records) or not set(mapping) <= expected:
            raise IngestionError("Agreement input has duplicate or unexpected records")
        if len({item.annotator_id for item in records}) > 1:
            raise IngestionError("Each agreement side must be one independent annotator")
        sides.append(mapping)
    if annotations_a and annotations_b:
        if annotations_a[0].annotator_id == annotations_b[0].annotator_id:
            raise IngestionError("Agreement requires two independent annotator identities")
    a, b = sides
    matched = expected & set(a) & set(b)
    workflow = Counter((a[item].annotation_status, b[item].annotation_status) for item in matched)
    disagreements, tasks = [], {}
    for task, labels in TASKS.items():
        pairs, missing = [], Counter()
        for record_id in expected_ids:
            x, y = a.get(record_id), b.get(record_id)
            if x is None or y is None:
                missing["missing_annotation"] += 1
                continue
            u, v = getattr(x, task + "_label"), getattr(y, task + "_label")
            category = None
            if x.annotation_status in EXCLUDED or y.annotation_status in EXCLUDED:
                missing["excluded_workflow"] += 1
                category = (
                    "EXCLUDED_WORKFLOW" if x.annotation_status != y.annotation_status else None
                )
            elif u not in labels or v not in labels:
                missing["unknown_or_missing_label"] += 1
                category = "UNKNOWN_OR_MISSING_LABEL"
            else:
                pairs.append((u, v))
                if u != v:
                    category = "LABEL_DISAGREEMENT"
            if category:
                disagreements.append(
                    {
                        "feedback_id": record_id,
                        "task": task,
                        "annotator_a_label": u,
                        "annotator_b_label": v,
                        "status": "REQUIRES_HUMAN_ADJUDICATION",
                        "category": category,
                    }
                )
        metric = cohen(pairs, labels)
        metric["not_comparable"] = {
            name: missing[name]
            for name in ("missing_annotation", "excluded_workflow", "unknown_or_missing_label")
        }
        metric["review_recommendations"] = (
            ["Review coverage, class imbalance and unresolved workflow cases"]
            if metric["kappa"] is None
            else ["Review handbook boundaries and calibrate independently"]
            if metric["kappa"] < 0.70
            else ["Provisional target met; still require human review"]
        )
        tasks[task] = metric
    for item in expected_ids:
        if item in matched and a[item].annotation_status != b[item].annotation_status:
            disagreements.append(
                {
                    "feedback_id": item,
                    "task": "workflow",
                    "annotator_a_label": a[item].annotation_status,
                    "annotator_b_label": b[item].annotation_status,
                    "status": "REQUIRES_HUMAN_ADJUDICATION",
                    "category": "WORKFLOW_DISAGREEMENT",
                }
            )
    frequencies = Counter(
        (item["task"], item["annotator_a_label"], item["annotator_b_label"], item["category"])
        for item in disagreements
    )
    return {
        "status": "AVAILABLE" if matched else "NOT_AVAILABLE",
        "dataset_type": "SYNTHETIC" if synthetic else "RESEARCH",
        "metrics_usage": "SOFTWARE_TEST_ONLY" if synthetic else "PILOT_DECISION_SUPPORT",
        "human_agreement_measured": not synthetic and bool(matched),
        "expected_count": len(expected),
        "matched_pairs": len(matched),
        "missing_a": len(expected - set(a)),
        "missing_b": len(expected - set(b)),
        "workflow_disagreement_count": sum(n for (x, y), n in workflow.items() if x != y),
        "workflow_pairs": [{"a": x, "b": y, "count": n} for (x, y), n in sorted(workflow.items())],
        "tasks": tasks,
        "disagreements": disagreements,
        "label_pair_frequencies": [
            {"task": t, "a": x, "b": y, "category": c, "count": n}
            for (t, x, y, c), n in sorted(frequencies.items(), key=lambda entry: str(entry[0]))
        ],
        "warning": "Kappa is not proof of validity; 0.70 is a provisional review target",
    }
