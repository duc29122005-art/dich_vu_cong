"""Computed metrics and validation-only calibration/review; no dataset or test reader."""

import math
import random
from collections import Counter
from typing import Literal

from pydantic import Field, model_validator

from pfa.annotation import pilot_store as store
from pfa.data.official_io import IngestionBlocked, IngestionError
from pfa.data.preprocessing import TRANSFORMATION_VERSION
from pfa.data.registry import Metadata
from pfa.ml import baseline

ROLES = ("calibration", "threshold", "assessment")


class Protocol(Metadata):
    version: Literal["evaluation-protocol-1"] = "evaluation-protocol-1"
    seed: int = Field(default=42, ge=0, lt=2**32)
    selection_metric: Literal["validation_macro_f1"] = "validation_macro_f1"
    family_order: list[str] = Field(default_factory=lambda: ["lr", "svm", "phobert"])
    role_ratios: list[float] = Field(
        default_factory=lambda: [0.4, 0.3, 0.3], min_length=3, max_length=3
    )
    calibration: Literal["ovr_sigmoid"] = "ovr_sigmoid"
    minimum_calibration_per_class: int = Field(default=2, ge=1, le=5000)
    threshold_grid: list[float] = Field(
        default_factory=lambda: [0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 1.0], min_length=1, max_length=100
    )
    maximum_selective_risk: float = Field(default=0.1, ge=0, le=1, allow_inf_nan=False)
    minimum_automated_records: int = Field(default=5, ge=1, le=5000)
    review_severity_high: bool = True
    bootstrap_replicates: int = Field(default=500, ge=100, le=2000)
    bootstrap_minimum_groups: int = Field(default=20, ge=3, le=5000)
    bootstrap_minimum_class_support: int = Field(default=5, ge=2, le=5000)
    confidence_level: float = Field(default=0.95, gt=0.5, lt=1, allow_inf_nan=False)
    normalization: Literal[TRANSFORMATION_VERSION] = TRANSFORMATION_VERSION
    preprocessing_policy: Literal["FAMILY_SPECIFIC_FROZEN"] = "FAMILY_SPECIFIC_FROZEN"

    @model_validator(mode="after")
    def valid(self) -> "Protocol":
        if self.family_order != ["lr", "svm", "phobert"]:
            raise ValueError("Stable model family tie-breaking order required")
        if (
            any(not 0 < value < 1 for value in self.role_ratios)
            or abs(sum(self.role_ratios) - 1) > 1e-9
        ):
            raise ValueError(
                "Three positive calibration/threshold/assessment ratios must sum to one"
            )
        if any(
            not 0 < value <= 1 for value in self.threshold_grid
        ) or self.threshold_grid != sorted(set(self.threshold_grid)):
            raise ValueError("Ordered unique probability thresholds required")
        return self


def roles(rows: list, protocol: Protocol) -> tuple[dict[str, list[int]], dict]:
    """Deterministic group boundaries; no labels or test observations used to assign roles."""
    # Only ephemeral keyed fingerprints of sanitized content; none are exported.
    import secrets

    from pfa.data.official import fingerprint
    from pfa.data.splitting import group_rows

    key = secrets.token_bytes(32)
    grouped = group_rows(rows, lambda value: fingerprint(key, "evaluation-roles-1", value))
    groups = {}
    for index, row in enumerate(grouped):
        groups.setdefault(row.group_id, []).append(index)
    if len(groups) < 3:
        raise IngestionError("At least three validation groups are required for separate roles")
    # Sort by original opaque membership before shuffling randomized keyed groups.
    ordered = sorted(groups.values(), key=lambda indices: min(rows[i].feedback_id for i in indices))
    random.Random(protocol.seed).shuffle(ordered)
    result = {name: [] for name in ROLES}
    targets = [len(rows) * ratio for ratio in protocol.role_ratios]
    for index, members in enumerate(ordered):
        target = (
            index
            if index < 3
            else max(range(3), key=lambda j: (targets[j] - len(result[ROLES[j]]), -j))
        )
        result[ROLES[target]].extend(members)
    result = {name: sorted(indices) for name, indices in result.items()}
    return result, {
        name: {
            "records": len(indices),
            "membership_sha256": store.digest([rows[i].feedback_id for i in indices]),
        }
        for name, indices in result.items()
    }


def metrics(
    actual: list[str],
    predicted: list[str],
    task: baseline.Task,
    seconds: float = 0.0,
    model_bytes: int = 0,
) -> dict:
    if not math.isfinite(seconds) or seconds < 0 or model_bytes < 0:
        raise IngestionError("Invalid evaluation resource measurements")
    result = baseline.metrics(actual, predicted, task)
    n = len(actual)
    result["precision_weighted"] = (
        sum(v["precision"] * v["support"] for v in result["per_class"].values()) / n
    )
    result["recall_weighted"] = (
        sum(v["recall"] * v["support"] for v in result["per_class"].values()) / n
    )
    result["normalized_confusion_matrix"] = [
        [value / sum(row) if sum(row) else 0.0 for value in row]
        for row in result["confusion_matrix"]
    ]
    high = result["per_class"].get("high") if task == "severity" else None
    result.update(
        severity_high_recall=high["recall"] if high and high["support"] else None,
        batch_latency_seconds=seconds,
        throughput_records_per_second=n / seconds if seconds > 0 else None,
        model_size_bytes=model_bytes,
    )
    return result


def bootstrap(
    actual: list[str],
    predicted: list[str],
    task: baseline.Task,
    groups: list[str],
    protocol: Protocol,
) -> dict:
    baseline.metrics(actual, predicted, task)
    if len(groups) != len(actual):
        raise IngestionError("Bootstrap group/label membership mismatch")
    labels = list(baseline.TASKS[task])
    grouped = {}
    for index, group in enumerate(groups):
        grouped.setdefault(group, []).append(index)
    support = Counter(actual)
    unavailable = {
        "status": "INSUFFICIENT_SUPPORT",
        "interval": None,
        "method": "GROUP_BOOTSTRAP_PERCENTILE",
        "independent_groups": len(grouped),
    }
    if len(grouped) < protocol.bootstrap_minimum_groups or any(
        support[label] < protocol.bootstrap_minimum_class_support for label in labels
    ):
        return unavailable
    import numpy as np

    rng, values, missing = random.Random(protocol.seed), [], 0
    keys = sorted(grouped)
    for _ in range(protocol.bootstrap_replicates):
        indices = [i for key in rng.choices(keys, k=len(keys)) for i in grouped[key]]
        truth = [actual[i] for i in indices]
        if set(truth) != set(labels):
            missing += 1
            continue
        values.append(baseline.metrics(truth, [predicted[i] for i in indices], task)["macro_f1"])
    if len(values) < max(100, math.ceil(protocol.bootstrap_replicates * 0.8)):
        return {**unavailable, "missing_class_replicates": missing}
    alpha = (1 - protocol.confidence_level) / 2
    return {
        "status": "COMPUTED",
        "metric": "macro_f1",
        "method": "GROUP_BOOTSTRAP_PERCENTILE",
        "confidence_level": protocol.confidence_level,
        "interval": np.quantile(values, [alpha, 1 - alpha]).tolist(),
        "valid_replicates": len(values),
        "missing_class_replicates": missing,
        "seed": protocol.seed,
        "independent_groups": len(grouped),
        "limitation": "Conditional on observed groups/classes; no representativeness claim",
    }


def probabilities(values: list[list[float]], count: int, width: int):
    import numpy as np

    array = np.asarray(values, dtype=float)
    if (
        array.shape != (count, width)
        or not np.isfinite(array).all()
        or (array < 0).any()
        or (array > 1).any()
        or not np.allclose(array.sum(axis=1), 1.0)
    ):
        raise IngestionError("Invalid ordered probability matrix")
    return array


def calibration_metrics(actual: list[str], values: list[list[float]], task: baseline.Task) -> dict:
    import numpy as np

    baseline.metrics(actual, actual, task)
    labels = list(baseline.TASKS[task])
    matrix = probabilities(values, len(actual), len(labels))
    targets = np.eye(len(labels))[[labels.index(label) for label in actual]]
    confidence, predicted = matrix.max(axis=1), matrix.argmax(axis=1)
    truth = targets.argmax(axis=1)
    bins, ece = [], 0.0
    for index in range(10):
        mask = (confidence >= index / 10) & (
            (confidence <= 1) if index == 9 else (confidence < (index + 1) / 10)
        )
        n = int(mask.sum())
        accuracy = float((predicted[mask] == truth[mask]).mean()) if n else None
        average = float(confidence[mask].mean()) if n else None
        if n:
            ece += n / len(actual) * abs(average - accuracy)
        bins.append(
            {
                "lower": index / 10,
                "upper": (index + 1) / 10,
                "count": n,
                "mean_top_score": average,
                "accuracy": accuracy,
            }
        )
    return {
        "multiclass_brier_sum": float(((matrix - targets) ** 2).sum(axis=1).mean()),
        "top_label_ece_10_bins": ece,
        "reliability_bins": bins,
        "limitations": "Brier sums classes (0..2); top-label ECE is not calibration proof",
    }


def fit_calibrator(
    scores: list[list[float]] | None,
    actual: list[str],
    task: baseline.Task,
    protocol: Protocol,
    provenance: dict,
) -> dict:
    if provenance.get("evaluation_split") != "validation":
        raise IngestionBlocked("Calibration fitting requires validation provenance")
    if task not in baseline.TASKS or any(label not in baseline.TASKS[task] for label in actual):
        raise IngestionError("Invalid calibration task or labels")
    labels = list(baseline.TASKS[task])
    unavailable = {
        "status": "UNAVAILABLE",
        "reason": "SCORES_OR_CLASS_SUPPORT_INSUFFICIENT",
        "provenance": provenance,
    }
    if (
        scores is None
        or not actual
        or any(Counter(actual)[label] < protocol.minimum_calibration_per_class for label in labels)
    ):
        return unavailable
    baseline.metrics(actual, actual, task)
    import numpy as np
    from sklearn.linear_model import LogisticRegression

    matrix = np.asarray(scores, dtype=float)
    if matrix.shape != (len(actual), len(labels)) or not np.isfinite(matrix).all():
        raise IngestionError("Invalid ordered calibration scores")
    coefficients, intercepts = [], []
    for index, label in enumerate(labels):
        model = LogisticRegression(C=1.0, max_iter=1000, random_state=protocol.seed)
        model.fit(matrix[:, index : index + 1], [int(value == label) for value in actual])
        coefficients.append(float(model.coef_[0, 0]))
        intercepts.append(float(model.intercept_[0]))
    return {
        "status": "FITTED",
        "method": "OVR_SIGMOID_RENORMALIZED",
        "labels": labels,
        "coefficients": coefficients,
        "intercepts": intercepts,
        "fitting_role": "calibration",
        "provenance": provenance,
        "research_calibration_validity_claimed": False,
    }


def apply_calibrator(calibrator: dict, scores: list[list[float]] | None, task: baseline.Task):
    if calibrator.get("status") != "FITTED" or scores is None:
        return None
    import numpy as np

    labels = list(baseline.TASKS[task])
    matrix = np.asarray(scores, dtype=float)
    if (
        calibrator.get("labels") != labels
        or matrix.ndim != 2
        or matrix.shape[1] != len(labels)
        or not np.isfinite(matrix).all()
    ):
        raise IngestionError("Calibration labels or score matrix incompatible")
    coefficients = np.asarray(calibrator.get("coefficients"), dtype=float)
    intercepts = np.asarray(calibrator.get("intercepts"), dtype=float)
    if (
        coefficients.shape != (len(labels),)
        or intercepts.shape != (len(labels),)
        or not np.isfinite(coefficients).all()
        or not np.isfinite(intercepts).all()
    ):
        raise IngestionError("Invalid sigmoid calibration parameters")
    logits = matrix * coefficients + intercepts
    values = 1 / (1 + np.exp(-np.clip(logits, -35, 35)))
    return (values / values.sum(axis=1, keepdims=True)).tolist()


def review(
    predicted: list[str],
    values,
    task: baseline.Task,
    threshold: dict | None,
    protocol: Protocol,
    *,
    calibrated: bool,
    invalid_artifact: bool = False,
    unsupported_input: bool = False,
    conflicts: bool = False,
) -> list[dict]:
    labels = list(baseline.TASKS[task])
    if any(label not in labels for label in predicted):
        raise IngestionError("Unknown predicted label")
    matrix = (
        probabilities(values, len(predicted), len(labels))
        if values is not None and predicted
        else None
    )
    selected = threshold and threshold.get("status") == "SELECTED_ON_THRESHOLD_VALIDATION"
    if selected and not 0 < threshold["threshold"] <= 1:
        raise IngestionError("Invalid review threshold")
    result = []
    for index, label in enumerate(predicted):
        reasons = []
        if invalid_artifact:
            reasons.append("INVALID_ARTIFACT")
        if unsupported_input:
            reasons.append("UNSUPPORTED_OR_OUT_OF_SCOPE_INPUT")
        if conflicts:
            reasons.append("CONFLICTING_PREDICTIONS")
        if not calibrated or matrix is None or not selected:
            reasons.append("CALIBRATION_OR_THRESHOLD_UNAVAILABLE")
        else:
            if labels[int(matrix[index].argmax())] != label:
                reasons.append("CALIBRATED_CLASS_CONFLICT")
            if matrix[index, labels.index(label)] < threshold["threshold"]:
                reasons.append("BELOW_VALIDATION_THRESHOLD")
        if task == "severity" and label == "high" and protocol.review_severity_high:
            reasons.append("SEVERITY_HIGH_REQUIRES_HUMAN")
        result.append(
            {
                "requires_review": bool(reasons),
                "reasons": reasons,
                "administrative_decision_allowed": False,
            }
        )
    return result


def review_metrics(
    actual: list[str], predicted: list[str], decisions: list[dict], task: baseline.Task
) -> dict:
    baseline.metrics(actual, predicted, task)
    if len(decisions) != len(actual):
        raise IngestionError("Review membership mismatch")
    automatic = [i for i, decision in enumerate(decisions) if not decision["requires_review"]]
    high = actual.count("high") if task == "severity" else 0
    return {
        "review_rate": 1 - len(automatic) / len(actual),
        "automated_coverage": len(automatic) / len(actual),
        "selective_risk": sum(actual[i] != predicted[i] for i in automatic) / len(automatic)
        if automatic
        else None,
        "automated_count": len(automatic),
        "record_count": len(actual),
        "critical_miss_count": sum(
            actual[i] == "high" and predicted[i] != "high" for i in automatic
        )
        if high
        else None,
        "severity_high_support": high if task == "severity" else None,
        "severity_high_recall": baseline.metrics(actual, predicted, task)["per_class"]["high"][
            "recall"
        ]
        if high
        else None,
    }


def select_threshold(
    actual: list[str],
    predicted: list[str],
    values,
    task: baseline.Task,
    protocol: Protocol,
    provenance: dict,
) -> dict:
    if provenance.get("evaluation_split") != "validation":
        raise IngestionBlocked("Threshold selection requires validation provenance")
    if values is None or not actual:
        return {"status": "ALL_REQUIRE_REVIEW", "threshold": None, "provenance": provenance}
    best = None
    for value in protocol.threshold_grid:
        candidate = {"status": "SELECTED_ON_THRESHOLD_VALIDATION", "threshold": value}
        result = review_metrics(
            actual,
            predicted,
            review(predicted, values, task, candidate, protocol, calibrated=True),
            task,
        )
        if (
            result["automated_count"] >= protocol.minimum_automated_records
            and result["selective_risk"] <= protocol.maximum_selective_risk
            and (
                best is None or result["automated_coverage"] > best["metrics"]["automated_coverage"]
            )
        ):
            best = {**candidate, "metrics": result, "provenance": provenance}
    return best or {
        "status": "ALL_REQUIRE_REVIEW",
        "threshold": None,
        "provenance": provenance,
        "reason": "No threshold satisfies configured support/risk targets; no safety guarantee",
    }
