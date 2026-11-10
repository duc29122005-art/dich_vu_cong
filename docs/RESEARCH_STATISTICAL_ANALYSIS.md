# Prespecified statistical analysis plan, research-protocol-1

This is a proposed plan, not a report of observed effects. No real samples or power
estimates exist. Freeze the final plan and exact configuration before collection.

## Estimands and units

Primary RQ4 outcomes are (1) mean seconds per completed assigned case, and (2) exact
three-task classification accuracy against independent adjudicated gold. Compute
each participant's condition mean, then the equally weighted mean of
AI_ASSISTED minus MANUAL_ONLY differences among participants with both conditions.
Negative time differences indicate shorter recorded completed-case time; positive
accuracy differences indicate greater recorded accuracy. Software generates no
automatic improvement, causal, significance or equivalence conclusion.

The time estimand conditions on completion. It is not an intention-to-treat total
workload effect. Always report assignments, observed/completed/incomplete/abandoned
and missing rows by condition alongside time. Attrition may bias completed-case
contrasts. Do not impute missing labels or clock measurements. Report participants
with only one measurable condition as unpaired exclusions from that contrast.

Exact joint accuracy requires all three gold labels. Per-task accuracy uses each
task's comparable gold subset. Unknown/missing gold severity is excluded from the
severity denominator, never converted to low. A human unknown response with known
gold is incorrect. Compute critical misses and high recall only on completed
gold-high records; absent support gives null, not perfect recall. Unobserved high
cases must not be classified as detected or missed automatically.

## Clustering, uncertainty and effects

Use a reproducible crossed participant/case-group percentile bootstrap: independently
sample participants and case groups with replacement; weight each observation by
case-group multiplicity and each resulting participant difference by participant
multiplicity. Group related cases before analysis. Use the protocol seed, 1,000
replicates and 95% intervals by default. At least 95% of replicates must be usable.

Technical floors: 20 paired participants, 20 observed independent case groups and
five paired participants in each order. Below any floor return INSUFFICIENT_EVIDENCE
and no interval. These are engineering guards, **not a validated power justification**.
Even above them the crossed bootstrap is approximate; very few cases per participant,
unbalanced exposure and sparse classes can impair inference. Inspect missingness,
support and design before interpreting intervals. Do not treat 1,000 repeated rows
from one participant as 1,000 independent observations.

Report the raw paired difference and participant paired standardized difference
(mean difference / SD of participant differences). Zero SD makes the standardized
effect undefined/null, even when the raw contrast is constant. Report no fabricated
p-values. Intervals are marginal, not simultaneous across primary/secondary outcomes;
there is no familywise significance claim. Per-task and safety measures are secondary.

Report AB-minus-BA differences in participant treatment contrasts when both orders
have at least five pairs, as a descriptive order diagnostic. Also report each
condition's mean participant time slope against within-period position, with its
participant support. This is a learning/fatigue diagnostic confounded by changing
case difficulty, not an isolated learning effect. No order/learning interval is
invented. Two periods cannot identify every carryover mechanism.

## Prospective sample-size strategy

Before genuine collection, define the smallest practically relevant time and accuracy
differences, target precision, allowable attrition, task counts and feasible recruitment.
Use an authorized feasibility pilot to estimate participant differences, case-group
heterogeneity, timing resolution and completion. Pilot outcomes inform a prospectively
reviewed **new** design; do not merge tuning pilot observations into confirmatory data.

A planning approximation for a paired mean CI half-width h is
`n ≈ (1.96 * SD_of_participant_differences / h)^2`; it is not a crossed-design power
calculation. Use a documented design simulation with plausible participant/case random
effects, observed class support and missingness for final planning, or seek qualified
statistical review when available. Choose the more demanding primary-outcome design,
allow for attrition, and record assumptions/evidence in allocation approval. No SD,
effect, target participant count or recruitment success is invented here. If feasible
recruitment cannot meet justified support, label the study exploratory/feasibility.

## RQ1, RQ2 and RQ3

RQ1 has no defensible citizen-population sampling interval by default. Report corpus
denominators and NOT_ESTIMATED uncertainty. STEP 11 retains its own approved metrics,
group bootstrap, calibration and test rules; STEP 15 consumes existing manifests only.

RQ3 numerical checks compare prespecified known values within fixed tolerances.
Alert TP/FP/FN/TN require independent reference events and eligible windows. Unknown
references/ineligible windows are excluded and counted. Human task accuracy/time and
questionnaire distributions are descriptive; do not calculate independent-observation
tests from repeated participant tasks. Rating missingness stays explicit; a single
workload item does not establish a validated psychometric scale.

Any outcome-driven change requires a deviation record and prospective new design;
never tune metrics, thresholds or models after final test or human outcome exposure.
