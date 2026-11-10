# Group-aware dataset splitting

Default policy: train 70%, validation 15%, test 15%, seed 42. `SplitConfig` is strict
JSON with defaults shown below:

```json
{
  "version": "split-config-1",
  "ratios": [0.70, 0.15, 0.15],
  "strategy": "group_random",
  "primary_task": "topic",
  "missing_time": "fail",
  "minimum_class_count": 1,
  "class_policy": "warn",
  "near_threshold": 0.85,
  "max_candidate_pairs": 100000
}
```

All proportions must be positive and sum to one. At least three independent groups
and nonempty partitions are required. No replacement or silent row removal occurs.

## Relationships and algorithm

Union-find combines exact normalized/case-folded text, existing duplicate groups,
and reviewed keyed case/thread/source-record/near-duplicate relationships. Transitive
links produce a single immutable group ID. General topic similarity alone is not
a relationship. Human grouping metadata must come from permitted evidence; missing
case/thread information is not invented.

Groups are sorted, shuffled with the seed, then allocated greedily by size and
primary-task class balance. The algorithm prefers large and rare-label groups;
ties retain seeded order. It never divides a group. Actual ratios and deviations
are recorded. Exact targets may be missed because of group size, class balancing
and holdout restrictions, even when a different optimization could fit better.
This bounded heuristic is not an optimal stratification guarantee.

All tasks use one record assignment. Topic/sentiment/severity masks are explicit.
Unknown severity becomes null with an exclusion reason, never low/medium/high.
Real unknown cases require an explicit human exception for topic/sentiment use.
OUT_OF_SCOPE and UNLABELABLE outcomes are excluded from partitions with counts and
source adjudication references retained. Other unresolved human review blocks freezing.

Class counts include all taxonomy classes, including zero counts. Minimum counts
apply to train and validation for each task. `class_policy: warn` reports gaps;
`fail` blocks publication. These operational thresholds are not scientifically
validated guarantees. Exact simultaneous stratification of all tasks may be
impossible because labels correlate and groups are indivisible.

## Temporal option

Use `strategy: temporal` explicitly. Only original verified feedback event times
are used. No ingestion time substitution or timezone inference occurs. Groups
are ordered by latest event time, then allocated chronologically. A group spanning
long periods can cause interval overlap; report it as potential temporal leakage.
This implementation does not promise disjoint time intervals for spanning groups.

Missing/naive timestamps fail by default. `missing_time: train_only` confines the
whole affected group to train and warns; it does not invent dates. Pilot records
not explicitly cleared for holdout also remain in train, with their connected
groups. These restrictions can create empty partitions, which fail rather than
yielding misleading ratios. Review coverage and temporal-overlap warnings before
human approval of the proposed dataset/card.
