# Descriptive alert rules — analytics-1

All generated alerts are DEMO_ONLY retrospective indicators for the requested window.
They support human review; they do not verify administrative incidents, crises, legal
violations or model confidence. Configuration is versioned and checksummed in
`configs/analytics_v1.yaml`. No threshold is presented as validated on real data.

## Shared eligibility

Rules currently support full daily windows only. Week/month trends work, but alert
requests for those intervals report DAILY_ALERT_WINDOWS_REQUIRED. The current window
is the last requested/observed daily bucket; baseline is the immediately preceding
seven buckets by default. Gaps remain explicit zero-observation buckets, not invented
observations. Every baseline bucket needs at least 10 feedback records and the current
bucket at least 20; both must also meet the configured cell-suppression threshold.
All windows must be complete local calendar days. Partial/future days, short baselines
and missing/zero support report INSUFFICIENT_DATA without alert values.

Null-date share is measured before the date filter, within the other selected filters.
Unknown coverage or share above 10% suppresses every rule. Known-label rules additionally
require minimum known-label support in every window. Small target cells/complements
and more than 10% missing/unknown selected task labels in any compared window
suppress the rule and its values. No isolated one-record fluctuation can alert.
Current/baseline start and exclusive end dates accompany each rule where available.

## Rules

1. **Volume**: current observed count must be at least 2× historical mean and exceed
   that mean by at least 3×max(population standard deviation, sqrt(mean)). The square-root
   floor prevents a perfectly constant small baseline from producing a zero threshold.
2. **High-severity share**: pool baseline known severity counts; compare current high /
   known severity against baseline high / known severity. Increase must exceed both
   0.20 and `3*sqrt(max(p*(1-p),0.01)*(1/current_n+1/baseline_n))`. Current high count must
   meet k. Unknown severity and missing labels never enter that denominator.
3. **Topic concentration**: choose the topic with the largest current-minus-baseline
   share increase (deterministic code tie-break). Apply the same support/noise guards
   with a 0.25 increase threshold. Topic shares use known selected-basis topic labels.

The noise formulas are transparent engineering guards, not calibrated p-values,
confidence intervals or population tests. Status is TRIGGERED, NORMAL, SUPPRESSED or
INSUFFICIENT_DATA, with a fixed explanation code. There is no email, webhook, incident
creation or automatic administrative action.

## Interpretation and validation

Service exposure, total citizen population and reporting completeness are unavailable.
Counts describe the observed feedback stream only; shares condition on recorded known
labels. They are not incident rates per service transaction. No seasonality, holidays,
source changes, autocorrelation, multiple-testing correction or case-level independence
adjustment is modeled. Seven preceding days are not a proven comparable seasonal
baseline. Check source continuity and coverage manually before any real interpretation.

Tests cover a stable baseline, deliberate invented spike, rare/small labels, all-null
dates, missing-date threshold, zero denominators, short baseline, incomplete windows,
different reporting boundaries and larger suppression thresholds. These checks establish
formula behavior only; no real false-positive rate, sensitivity or scientific validity
is claimed. Before research use, obtain authorized historical data and pre-register
domain-approved thresholds, exposure handling and empirical false-positive validation.
