"""Analyze validated observations without inventing unobserved responses or gold."""

from collections import Counter, defaultdict
from statistics import mean

from pfa.annotation.agreement import TASKS
from pfa.research.statistics import paired_contrast, ratio


def analyze(payload, allocation, protocol):
    cases = {c.case_id: c for c in payload.cases}
    completed = [r for r in payload.observations if r.completion_status == "COMPLETED"]
    assignments = allocation["assignments"]
    conditions = {}
    for condition in ("MANUAL_ONLY", "AI_ASSISTED"):
        assigned = sum(a["condition"] == condition for a in assignments)
        selected = [r for r in payload.observations if r.condition == condition]
        counts = Counter(r.completion_status for r in selected)
        accepted = [r for r in selected if r.ai_suggestion_accepted is not None]
        conditions[condition] = {
            "assigned": assigned,
            "observed": len(selected),
            "missing": assigned - len(selected),
            "completed": counts["COMPLETED"],
            "incomplete": counts["INCOMPLETE"],
            "abandoned": counts["ABANDONED"],
            "completion_rate": ratio(counts["COMPLETED"], assigned),
            "suggestion_acceptance": ratio(
                sum(r.ai_suggestion_accepted for r in accepted), len(accepted)
            ),
            "override_rate": ratio(sum(r.override_flag for r in accepted), len(accepted)),
        }

    def records(get_value):
        result = []
        for row in completed:
            value = get_value(row, cases[row.case_id])
            if value is not None:
                result.append(
                    (
                        row.participant_id,
                        cases[row.case_id].group_id,
                        row.condition,
                        value,
                        row.condition_order,
                    )
                )
        return result

    time = paired_contrast(records(lambda r, c: r.duration_seconds), protocol)
    accuracies = {}
    for task in TASKS:

        def value(row, case):
            gold = getattr(case.labels, task)
            if case.basis != "adjudicated" or not case.reference_gold_id or gold not in TASKS[task]:
                return None
            return float(getattr(row, "reviewer_" + task) == gold)

        accuracies[task] = paired_contrast(records(value), protocol)

    def joint(row, case):
        if (
            case.basis != "adjudicated"
            or not case.reference_gold_id
            or any(getattr(case.labels, task) not in labels for task, labels in TASKS.items())
        ):
            return None
        return float(
            all(getattr(row, "reviewer_" + task) == getattr(case.labels, task) for task in TASKS)
        )

    accuracy = paired_contrast(records(joint), protocol)
    critical = {}
    for condition in conditions:
        high = [
            r
            for r in completed
            if r.condition == condition
            and cases[r.case_id].basis == "adjudicated"
            and cases[r.case_id].reference_gold_id
            and cases[r.case_id].labels.severity == "high"
        ]
        hits = sum(r.reviewer_severity == "high" for r in high)
        critical[condition] = {
            "high_severity_recall": ratio(hits, len(high)),
            "critical_miss_count": len(high) - hits if high else None,
            "scope": "COMPLETED_GOLD_COMPARABLE_ONLY",
        }
    positions = {a["assignment_id"]: a["position"] for a in assignments}
    learning = {}
    for condition in conditions:
        people = defaultdict(list)
        for row in completed:
            if row.condition == condition:
                people[row.participant_id].append(
                    (positions[row.assignment_id], row.duration_seconds)
                )
        slopes = []
        for points in people.values():
            if len({p for p, _ in points}) < 2:
                continue
            x, y = mean(p for p, _ in points), mean(t for _, t in points)
            slopes.append(
                sum((p - x) * (t - y) for p, t in points) / sum((p - x) ** 2 for p, _ in points)
            )
        learning[condition] = {
            "participants_with_repeated_positions": len(slopes),
            "mean_time_slope_seconds_per_position": mean(slopes) if slopes else None,
            "status": "DESCRIPTIVE_ONLY"
            if len(slopes) >= protocol.minimum_participants
            else "INSUFFICIENT_EVIDENCE",
            "interval": None,
            "limitation": "Case difficulty and fatigue confound this learning diagnostic",
        }
    return {
        "status": "ESTIMATED_CONTRAST"
        if time["status"] == accuracy["status"] == "ESTIMATED_CONTRAST"
        else "INSUFFICIENT_EVIDENCE",
        "conditions": conditions,
        "completed_case_time_seconds": time,
        "independent_gold_accuracy": accuracy,
        "per_task_accuracy": accuracies,
        "severity_safety": critical,
        "within_condition_learning_diagnostic": learning,
        "missing_observations": len(assignments) - len(payload.observations),
        "deviations": dict(Counter(d.code for d in payload.deviations)),
        "limitations": [
            "Completed-case time excludes missing/abandoned cases; inspect attrition",
            "Participant-weighted contrast; crossed case-group bootstrap is approximate",
            "Order contrast is descriptive; carryover and learning may remain",
            "No p-values, significance, equivalence or automatic improvement claims",
        ],
    }
