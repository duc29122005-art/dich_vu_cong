"""Participant-weighted contrasts and crossed participant/case-group bootstrap."""

import random
from collections import Counter, defaultdict
from math import ceil
from statistics import mean, stdev


def ratio(numerator, denominator):
    return {
        "numerator": numerator,
        "denominator": denominator,
        "share": numerator / denominator if denominator else None,
    }


def percentile(values, fraction):
    values = sorted(values)
    position = (len(values) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    return values[lower] + (values[upper] - values[lower]) * (position - lower)


def paired_contrast(records, protocol):
    """Records: (participant, case_group, condition, measured_value, order).

    Equal participant weights; case-group weights handle repeated case exposure across people.
    This estimates a completed-case contrast, not an intention-to-treat time effect.
    """
    grouped = defaultdict(lambda: defaultdict(list))
    orders = {}
    for person, group, condition, value, order in records:
        grouped[person][condition].append((group, value))
        orders[person] = order
    complete = {
        p: groups
        for p, groups in grouped.items()
        if groups.get("MANUAL_ONLY") and groups.get("AI_ASSISTED")
    }
    deltas = {
        p: mean(v for _, v in groups["AI_ASSISTED"]) - mean(v for _, v in groups["MANUAL_ONLY"])
        for p, groups in complete.items()
    }
    group_ids = sorted(
        {g for groups in complete.values() for rows in groups.values() for g, _ in rows}
    )
    order_counts = Counter(orders[p] for p in complete)
    enough = (
        len(complete) >= protocol.minimum_participants
        and len(group_ids) >= protocol.minimum_case_groups
        and all(order_counts[o] >= protocol.minimum_order_participants for o in ("AB", "BA"))
    )
    point = mean(deltas.values()) if deltas else None
    spread = stdev(deltas.values()) if len(deltas) > 1 else 0
    result = {
        "status": "ESTIMATED_CONTRAST" if enough else "INSUFFICIENT_EVIDENCE",
        "paired_participants": len(complete),
        "unpaired_participants": len(grouped) - len(complete),
        "independent_case_groups": len(group_ids),
        "order_counts": dict(order_counts),
        "difference_ai_minus_manual": point,
        "paired_standardized_difference": point / spread
        if point is not None and spread > 0
        else None,
        "interval": None,
        "method": "CROSSED_PARTICIPANT_CASE_GROUP_PERCENTILE_BOOTSTRAP",
        "confidence_level": protocol.confidence_level,
        "valid_replicates": 0,
        "order_effect_difference_AB_minus_BA": (
            mean(v for p, v in deltas.items() if orders[p] == "AB")
            - mean(v for p, v in deltas.items() if orders[p] == "BA")
            if all(order_counts[o] >= protocol.minimum_order_participants for o in ("AB", "BA"))
            else None
        ),
        "p_value": None,
        "equivalence_claim": False,
    }
    if not enough:
        return result
    rng, estimates, people = random.Random(protocol.seed), [], sorted(complete)
    for _ in range(protocol.bootstrap_replicates):
        person_weights = Counter(rng.choices(people, k=len(people)))
        group_weights = Counter(rng.choices(group_ids, k=len(group_ids)))
        contrasts = []
        for person, weight in person_weights.items():
            averages = {}
            for condition, rows in complete[person].items():
                denominator = sum(group_weights[g] for g, _ in rows)
                if denominator:
                    averages[condition] = sum(group_weights[g] * v for g, v in rows) / denominator
            if len(averages) == 2:
                contrasts.extend([averages["AI_ASSISTED"] - averages["MANUAL_ONLY"]] * weight)
        if contrasts:
            estimates.append(mean(contrasts))
    result["valid_replicates"] = len(estimates)
    if len(estimates) < ceil(protocol.bootstrap_replicates * 0.95):
        return {**result, "status": "INSUFFICIENT_EVIDENCE"}
    tail = (1 - protocol.confidence_level) / 2
    result["interval"] = [percentile(estimates, tail), percentile(estimates, 1 - tail)]
    return result
