"""Descriptive moving-baseline indicators, not incident detection or significance tests."""

from collections import Counter
from math import sqrt
from statistics import mean, pstdev

from pfa.analytics.kpis import labels
from pfa.analytics.schemas import Alert

RULES = ("volume", "high_severity_share", "topic_concentration")


def evaluate(buckets, members, filters, config, missing_share):
    def unavailable(reason, status="INSUFFICIENT_DATA"):
        return [Alert(rule=rule, status=status, reason=reason) for rule in RULES]

    if filters.interval != "day":
        return unavailable("DAILY_ALERT_WINDOWS_REQUIRED")
    if missing_share is None or missing_share > config.max_missing_date_share:
        return unavailable("MISSING_EVENT_TIME_COVERAGE", "SUPPRESSED")
    required = config.baseline_windows + 1
    if len(buckets) < required:
        return unavailable("INSUFFICIENT_BASELINE_WINDOWS")
    windows = buckets[-required:]
    groups = members[-required:]
    if not all(b.complete_calendar_window for b in windows):
        return unavailable("PARTIAL_CALENDAR_WINDOW")
    counts = [len(g) for g in groups]
    if min(counts[:-1]) < max(config.baseline_min_count, config.small_group) or counts[-1] < max(
        config.current_min_count, config.small_group
    ):
        return unavailable("INSUFFICIENT_WINDOW_SUPPORT")
    average = mean(counts[:-1])
    deviation = max(pstdev(counts[:-1]), sqrt(average))
    volume = (
        counts[-1] >= config.volume_ratio * average
        and counts[-1] - average >= config.volume_sigma * deviation
    )
    alerts = [
        Alert(
            rule="volume",
            status="TRIGGERED" if volume else "NORMAL",
            reason="OBSERVED_VOLUME_INCREASE" if volume else "WITHIN_BASELINE_RULE",
            observed=float(counts[-1]),
            baseline=average,
        )
    ]
    values = [[labels(r, filters.basis) for r in group] for group in groups]
    for rule, task, target, increase in (
        ("high_severity_share", "severity", "high", config.share_increase),
        ("topic_concentration", "topic", None, config.topic_increase),
    ):
        available = {
            "severity": {"low", "medium", "high"},
            "topic": {
                "delayed_processing",
                "complex_procedure",
                "unclear_guidance",
                "online_system_error",
                "staff_attitude",
                "fees",
                "unsatisfactory_result",
                "other",
            },
        }
        distributions = [
            Counter(v.get(task) for v in group if v.get(task) in available[task])
            for group in values
        ]
        totals = [sum(c.values()) for c in distributions]
        if any(
            1 - known / count > config.max_missing_label_share
            for known, count in zip(totals, counts, strict=True)
        ):
            alerts.append(Alert(rule=rule, status="SUPPRESSED", reason="MISSING_LABEL_COVERAGE"))
            continue
        if min(totals[:-1]) < max(config.baseline_min_count, config.small_group) or totals[
            -1
        ] < max(config.current_min_count, config.small_group):
            alerts.append(
                Alert(rule=rule, status="INSUFFICIENT_DATA", reason="INSUFFICIENT_KNOWN_LABELS")
            )
            continue
        historical = sum(distributions[:-1], Counter())
        denominator = sum(totals[:-1])
        if target is None:
            target = max(
                sorted(available[task]),
                key=lambda code: (
                    distributions[-1][code] / totals[-1] - historical[code] / denominator
                ),
            )
        current_count, baseline_count = distributions[-1][target], historical[target]
        if any(
            0 < value < config.small_group
            for value in (
                current_count,
                totals[-1] - current_count,
                baseline_count,
                denominator - baseline_count,
            )
        ):
            alerts.append(Alert(rule=rule, status="SUPPRESSED", reason="SMALL_LABEL_CELL"))
            continue
        current, baseline = current_count / totals[-1], baseline_count / denominator
        noise = 3 * sqrt(max(baseline * (1 - baseline), 0.01) * (1 / totals[-1] + 1 / denominator))
        triggered = current_count >= config.small_group and current - baseline >= max(
            increase, noise
        )
        alerts.append(
            Alert(
                rule=rule,
                status="TRIGGERED" if triggered else "NORMAL",
                reason="OBSERVED_SHARE_INCREASE" if triggered else "WITHIN_BASELINE_RULE",
                observed=current,
                baseline=baseline,
                topic=target if task == "topic" else None,
            )
        )
    return alerts
