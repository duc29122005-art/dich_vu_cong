"""Seeded difficulty-matched crossover; no labels or protected test reader."""

import random
from collections import Counter, defaultdict

from pfa.annotation import pilot_store as store
from pfa.data.official_io import IngestionBlocked, IngestionError
from pfa.research.schemas import Assignment, Case, Participant


def generate(
    participants: list[Participant],
    cases: list[Case],
    protocol,
    experiment_id,
    mode,
    *,
    forbidden_case_ids: set[str],
    forbidden_groups: set[str],
):
    store.identifier(experiment_id)
    identities = [p.participant_id for p in participants]
    case_ids = [c.case_id for c in cases]
    if (
        not participants
        or len(identities) != len(set(identities))
        or len(case_ids) != len(set(case_ids))
    ):
        raise IngestionError("Unique nonempty participant registry and case pool required")
    if len(participants) > 1000 or len(cases) > 5000:
        raise IngestionError("Bounded experiment required")
    if len(participants) * protocol.cases_per_condition * 2 > 20000:
        raise IngestionError("At most 20000 assignments supported per experiment")
    if any(p.mode != mode for p in participants) or any(
        c.mode != mode or c.role != "EXPERIMENT_INDEPENDENT" for c in cases
    ):
        raise IngestionBlocked("Experiment pool mode or role mismatch")
    if set(case_ids) & forbidden_case_ids or {c.group_id for c in cases} & forbidden_groups:
        raise IngestionBlocked("Experiment pool overlaps training, tuning or protected holdout")
    rng = random.Random(protocol.seed)
    people = sorted(identities)
    rng.shuffle(people)
    # Odd samples differ by one order; which order gets the extra participant is seeded.
    orders = ["AB", "BA"] * (len(people) // 2)
    if len(people) % 2:
        orders.append(rng.choice(["AB", "BA"]))
    rng.shuffle(orders)
    strata = defaultdict(list)
    for case in sorted(cases, key=lambda c: c.case_id):
        strata[case.difficulty].append(case)
    exposure = Counter()
    allocations = []
    for person, order in zip(people, orders, strict=True):
        used_groups = set()
        blocks = {"MANUAL_ONLY": [], "AI_ASSISTED": []}
        for _ in range(protocol.cases_per_condition):
            options = [
                name
                for name in sorted(strata)
                if len({c.group_id for c in strata[name]} - used_groups) >= 2
            ]
            if not options:
                raise IngestionError(
                    "Insufficient distinct case groups for difficulty-matched conditions"
                )
            difficulty = rng.choice(options)
            candidates = [c for c in strata[difficulty] if c.group_id not in used_groups]
            rng.shuffle(candidates)
            candidates.sort(key=lambda c: exposure[c.case_id])
            first = candidates[0]
            second = next(c for c in candidates if c.group_id != first.group_id)
            pair = [first, second]
            rng.shuffle(pair)
            for condition, case in zip(blocks, pair, strict=True):
                blocks[condition].append(case)
                exposure[case.case_id] += 1
                used_groups.add(case.group_id)
        sequence = (
            ["MANUAL_ONLY", "AI_ASSISTED"] if order == "AB" else ["AI_ASSISTED", "MANUAL_ONLY"]
        )
        for period, condition in enumerate(sequence, 1):
            for position, case in enumerate(blocks[condition], 1):
                identity = (
                    "a_" + store.digest([experiment_id, person, condition, case.case_id])[:32]
                )
                allocations.append(
                    Assignment(
                        experiment_id=experiment_id,
                        assignment_id=identity,
                        participant_id=person,
                        case_id=case.case_id,
                        condition=condition,
                        condition_order=order,
                        period=period,
                        position=position,
                        difficulty=case.difficulty,
                    ).model_dump()
                )
    result = {
        "experiment_id": experiment_id,
        "mode": mode,
        "protocol_version": protocol.version,
        "protocol_sha256": store.digest(protocol.model_dump()),
        "seed": protocol.seed,
        "pool_sha256": store.digest(
            [c.model_dump(mode="json") for c in sorted(cases, key=lambda c: c.case_id)]
        ),
        "participants_sha256": store.digest(
            [p.model_dump() for p in sorted(participants, key=lambda p: p.participant_id)]
        ),
        "assignments": allocations,
        "order_counts": dict(Counter(orders)),
        "difficulty_matching": "EXACT_WITHIN_PARTICIPANT_CONDITION_COUNTS",
        "holdout_labels_read": False,
    }
    return {**result, "assignment_sha256": store.digest(result)}
