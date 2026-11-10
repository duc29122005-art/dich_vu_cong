"""Deterministic group isolation and safe aggregate diagnostics; no label inference."""

import random
from collections import Counter, defaultdict
from collections.abc import Callable
from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator, model_validator

from pfa.annotation.agreement import TASKS
from pfa.annotation.schema import FeedbackID
from pfa.data.official_io import IngestionError
from pfa.data.official_schema import Feedback
from pfa.data.preprocessing import normalize_text
from pfa.data.registry import Metadata

SPLITS = ("train", "validation", "test")
ALGORITHM = "group-greedy-1"


class SplitConfig(Metadata):
    version: Literal["split-config-1"] = "split-config-1"
    ratios: list[float] = Field(
        default_factory=lambda: [0.70, 0.15, 0.15], min_length=3, max_length=3
    )
    strategy: Literal["group_random", "temporal"] = "group_random"
    primary_task: Literal["topic", "sentiment", "severity"] = "topic"
    missing_time: Literal["fail", "train_only"] = "fail"
    minimum_class_count: int = Field(default=1, ge=1, le=5000)
    class_policy: Literal["warn", "fail"] = "warn"
    near_threshold: float = Field(default=0.85, ge=0.5, le=1)
    max_candidate_pairs: int = Field(default=100000, ge=1, le=1000000)

    @model_validator(mode="after")
    def proportions(self) -> "SplitConfig":
        if any(not 0 < value < 1 for value in self.ratios) or abs(sum(self.ratios) - 1) > 1e-9:
            raise ValueError("Three positive split ratios must sum to one")
        return self


class CorpusRow(Metadata):
    feedback_id: FeedbackID
    content: str = Field(min_length=1, max_length=20000)
    source_id: str
    source_version: str
    taxonomy_checksum: str
    dataset_type: Literal["SYNTHETIC", "RESEARCH"]
    event_time: datetime | None
    group_id: str
    relations: list[str]
    labels: dict[str, str | None]
    eligible: dict[str, bool]
    exclusion_reasons: dict[str, str | None]
    holdout_eligible: bool
    domain_bucket: str | None = None
    agency_bucket: str | None = None

    @field_validator("event_time", mode="before")
    @classmethod
    def event_timestamp(cls, value: object) -> datetime | None:
        return Feedback.timestamp(value)

    @model_validator(mode="after")
    def task_contract(self) -> "CorpusRow":
        if not normalize_text(self.content).strip():
            raise ValueError("Empty corpus text")
        if any(
            set(mapping) != set(TASKS)
            for mapping in (self.labels, self.eligible, self.exclusion_reasons)
        ):
            raise ValueError("Exact task masks required")
        for task, labels in TASKS.items():
            label = self.labels[task]
            if label is not None and label not in labels:
                raise ValueError("Invalid supervised corpus label")
            if self.eligible[task] != (label is not None) or (
                self.eligible[task] == (self.exclusion_reasons[task] is not None)
            ):
                raise ValueError("Label eligibility and exclusion reason disagree")
        return self


def normalized(text: str) -> str:
    return normalize_text(text).casefold()


def group_rows(rows: list[CorpusRow], fingerprint: Callable[[str], str]) -> list[CorpusRow]:
    """Union transitive case/thread/source/duplicate relations and exact text."""
    if not rows or len(rows) > 5000:
        raise IngestionError("Corpus requires 1 to 5000 validated records")
    ids = [row.feedback_id for row in rows]
    if len(set(ids)) != len(ids):
        raise IngestionError("Duplicate corpus record IDs")
    parent = {identifier: identifier for identifier in ids}

    def find(value: str) -> str:
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    owners = {}
    for row in sorted(rows, key=lambda item: item.feedback_id):
        links = [
            *row.relations,
            "group:" + row.group_id,
            "text:" + fingerprint(normalized(row.content)),
        ]
        for link in links:
            if link in owners:
                a, b = find(row.feedback_id), find(owners[link])
                parent[max(a, b)] = min(a, b)
            else:
                owners[link] = row.feedback_id
    return [
        row.model_copy(update={"group_id": "g_" + fingerprint(find(row.feedback_id))})
        for row in rows
    ]


def split_rows(rows: list[CorpusRow], config: SplitConfig, seed: int) -> tuple[dict, dict]:
    if not rows or not 0 <= seed < 2**32:
        raise IngestionError("Nonempty corpus and valid seed required")
    groups = defaultdict(list)
    for row in rows:
        groups[row.group_id].append(row)
    if len(groups) < 3:
        raise IngestionError("At least three isolated groups required; ratios impossible")
    rng = random.Random(seed)
    order = sorted(groups)
    rng.shuffle(order)
    counts, assigned = Counter(), {}
    label_counts = {split: Counter() for split in SPLITS}
    totals = Counter(
        row.labels[config.primary_task] for row in rows if row.eligible[config.primary_task]
    )
    targets = dict(zip(SPLITS, (len(rows) * ratio for ratio in config.ratios)))
    warnings = []
    if config.strategy == "temporal":
        unknown = [
            name
            for name in order
            if any(row.event_time is None or row.event_time.tzinfo is None for row in groups[name])
        ]
        if unknown and config.missing_time == "fail":
            raise IngestionError("Temporal split requires verified timezone-aware event dates")
        for name in unknown:
            assigned[name] = "train"
            counts["train"] += len(groups[name])
        if unknown:
            warnings.append("UNKNOWN_EVENT_TIME_GROUPS_TRAIN_ONLY")
        order = sorted(
            (name for name in order if name not in unknown),
            key=lambda name: (max(row.event_time.timestamp() for row in groups[name]), name),
        )
        cursor = 0
        for name in order:
            group = groups[name]
            if not all(row.holdout_eligible for row in group):
                assigned[name] = "train"
                counts["train"] += len(group)
                continue
            while cursor < 2 and counts[SPLITS[cursor]] >= targets[SPLITS[cursor]]:
                cursor += 1
            assigned[name] = SPLITS[cursor]
            counts[SPLITS[cursor]] += len(group)
    else:
        # ponytail: greedy allocation at 5000 rows; use optimization only if coverage needs it.
        order.sort(
            key=lambda name: (
                -len(groups[name]),
                min(
                    (
                        totals[row.labels[config.primary_task]]
                        for row in groups[name]
                        if row.eligible[config.primary_task]
                    ),
                    default=len(rows),
                ),
            )
        )
        for name in order:
            group = groups[name]
            allowed = SPLITS if all(row.holdout_eligible for row in group) else ("train",)
            hist = Counter(
                row.labels[config.primary_task]
                for row in group
                if row.eligible[config.primary_task]
            )

            def cost(split: str) -> float:
                total_cost = 0.0
                for candidate, ratio in zip(SPLITS, config.ratios):
                    size = counts[candidate] + (len(group) if candidate == split else 0)
                    total_cost += (size - targets[candidate]) ** 2 / max(targets[candidate], 1)
                    for label, total in sorted(totals.items()):
                        count = label_counts[candidate][label] + (
                            hist[label] if candidate == split else 0
                        )
                        total_cost += (count - total * ratio) ** 2 / max(total * ratio, 1)
                return total_cost

            chosen = min(allowed, key=cost)
            assigned[name] = chosen
            counts[chosen] += len(group)
            label_counts[chosen].update(hist)
    partitions = {
        split: sorted(
            (row for row in rows if assigned[row.group_id] == split),
            key=lambda row: row.feedback_id,
        )
        for split in SPLITS
    }
    if any(not partitions[split] for split in SPLITS):
        raise IngestionError("Group or holdout constraints leave an empty split")
    distributions = {}
    for split, records in partitions.items():
        distributions[split] = {}
        for task, labels in TASKS.items():
            hist = Counter(row.labels[task] for row in records if row.eligible[task])
            distributions[split][task] = {label: hist[label] for label in labels}
            if split in {"train", "validation"} and any(
                hist[label] < config.minimum_class_count for label in labels
            ):
                warnings.append(f"CLASS_COVERAGE_{split.upper()}_{task.upper()}")
    if (
        warnings
        and config.class_policy == "fail"
        and any(warning.startswith("CLASS_COVERAGE") for warning in warnings)
    ):
        raise IngestionError("Required train/validation class coverage not met")
    deviations = {
        split: counts[split] / len(rows) - ratio for split, ratio in zip(SPLITS, config.ratios)
    }
    if any(abs(value) > 1 / len(rows) for value in deviations.values()):
        warnings.append("GROUP_CONSTRAINT_RATIO_DEVIATION")
    return partitions, {
        "algorithm": ALGORITHM,
        "seed": seed,
        "strategy": config.strategy,
        "counts": {split: len(partitions[split]) for split in SPLITS},
        "ratios": {split: len(partitions[split]) / len(rows) for split in SPLITS},
        "deviation": deviations,
        "class_distributions": distributions,
        "warnings": sorted(set(warnings)),
    }


def leakage(partitions: dict[str, list[CorpusRow]], config: SplitConfig) -> dict:
    """No content or private identifiers in diagnostics; uncertain matches need review."""
    if set(partitions) != set(SPLITS) or any(not partitions[split] for split in SPLITS):
        raise IngestionError("NOT_AVAILABLE: three nonempty partitions required")
    owners, failures, warnings = {}, Counter(), Counter()
    all_rows = []
    for split in SPLITS:
        for row in partitions[split]:
            all_rows.append((split, row))
            if split != "train" and not row.holdout_eligible:
                failures["UNAPPROVED_HOLDOUT_MEMBERSHIP"] += 1
            for kind, values in {
                "RECORD_ID": [row.feedback_id],
                "GROUP": [row.group_id],
                "RELATION": row.relations,
                "EXACT_TEXT": [normalized(row.content)],
            }.items():
                for value in values:
                    key = (kind, value)
                    if key in owners:
                        if owners[key] != split:
                            failures["CROSS_SPLIT_" + kind] += 1
                        elif kind == "RECORD_ID":
                            failures["DUPLICATE_RECORD_ID"] += 1
                    else:
                        owners[key] = split
    provenance = {
        (row.source_id, row.source_version, row.taxonomy_checksum, row.dataset_type)
        for _, row in all_rows
    }
    if len(provenance) != 1:
        failures["PROVENANCE_MISMATCH"] += 1
    # Candidate generation is bounded and explicit; exceeding capacity never yields PASS.
    shingles, pairs, tokens = defaultdict(list), set(), []
    for index, (_, row) in enumerate(all_rows):
        words = normalized(row.content).split()
        parts = {tuple(words[i : i + 3]) for i in range(max(1, len(words) - 2))}
        tokens.append(set(words))
        for part in sorted(parts):
            for previous in shingles[part]:
                if all_rows[previous][0] != all_rows[index][0]:
                    pairs.add((previous, index))
                    if len(pairs) > config.max_candidate_pairs:
                        raise IngestionError(
                            "Near-duplicate review capacity exceeded; no safe PASS"
                        )
            shingles[part].append(index)
    for a, b in sorted(pairs):
        union = tokens[a] | tokens[b]
        score = len(tokens[a] & tokens[b]) / len(union) if union else 0
        if score >= config.near_threshold:
            warnings["POTENTIAL_NEAR_DUPLICATE"] += 1
    dates = {
        split: [
            row.event_time.timestamp()
            for row in records
            if row.event_time and row.event_time.tzinfo
        ]
        for split, records in partitions.items()
    }
    if config.strategy == "temporal":
        for a, b in (SPLITS[:2], SPLITS[1:], ("train", "test")):
            if dates[a] and dates[b] and max(dates[a]) >= min(dates[b]):
                warnings["TEMPORAL_INTERVAL_OVERLAP"] += 1
    return {
        "status": "FAIL" if failures else "WARN" if warnings else "PASS",
        "critical_count": sum(failures.values()),
        "failures": dict(failures),
        "warnings": dict(warnings),
        "near_candidate_pairs_checked": len(pairs),
        "timestamp_known": sum(len(values) for values in dates.values()),
        "timestamp_unknown_or_ambiguous": len(all_rows) - sum(map(len, dates.values())),
        "near_detection_limit": "Shared three-word shingles; lexical heuristic, not exhaustive",
    }
