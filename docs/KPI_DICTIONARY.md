# Analytics KPI dictionary — analytics-1

All current results are **SYNTHETIC DATA — DEMO ONLY**. They validate software and
mathematics, not scientific findings or service quality. One feedback UUID is one
statistical unit. Neither three task predictions nor repeated review/audit events
multiply that unit. No percentage below is model confidence or population satisfaction.

## Common population and label rules

Let **S** be feedback from authorized sources after agency/domain, source, model,
review-state and selected-label filters, before date filtering. Let **C** be S after
the optional event-date window; **N** is its size. Without a date filter, C includes
undated feedback. With a date filter, undated feedback cannot be placed in that
window and is excluded from C but reported separately using S.

`basis=prediction` uses the latest immutable prediction per feedback/task, ordered by
prediction creation time then opaque UUID as a deterministic tie-break. `reviewed`
uses current human labels only for REVIEWED and ADJUDICATED states. `adjudicated`
uses only ADJUDICATED labels. Other records retain missing labels; no basis falls back
to another. A label filter acts on the chosen basis. Counts include missing labels
unless an explicit label filter excludes them. Taxonomy label order remains frozen.
Unknown severity is a separate workflow outcome, not low/medium/high.

All counts are nonnegative feedback counts. Shares are fractions in [0,1], displayed
as percentages only for descriptive aggregates. Zero denominators yield null. Positive
small cells, small complements and small denominators yield suppression/null rather
than zero. Suppression details and filtering semantics are in [API](ANALYTICS_API.md).

| KPI / response key | Numerator | Denominator | Missing treatment and interpretation |
|---|---|---|---|
| Total / `total` | N | None; unit: feedback | Includes missing labels; date filtering excludes unknown event dates |
| Topic counts / `distributions.topic` | Records with each selected primary topic | N for cell share | Missing is an explicit category; one topic per feedback |
| Sentiment counts / `distributions.sentiment` | Records with each selected sentiment | N for cell share | Missing is explicit |
| Severity counts / `distributions.severity` | Records with each low/medium/high/unknown/missing outcome | N for cell share | Unknown never enters supervised severity denominator |
| Negative share / `negative_share` | Selected sentiment = negative | Selected sentiment in negative/neutral/positive | Excludes missing; report sentiment coverage alongside it |
| High-severity share / `high_severity_share` | Selected severity = high | Selected severity in low/medium/high | Excludes unknown and missing; never interpret excluded cases as low severity |
| Top complaint topic / `top_complaint_topic` | Topic with greatest count among negative feedback with known topic | Ranking; no percentage is returned | Ties follow taxonomy order; null for no support or suppressed complaint partition. “Complaint” here means selected negative sentiment, not a verified legal complaint |
| Complaint-topic cells / `distributions.complaint_topic` | Negative feedback with each known topic | N for cell share | `not_comparable` is the complement, preventing residual reconstruction within this partition |
| AI requests review / `review_required` | Any latest task prediction has requires_review=true, or any task output is missing | N | Original AI review flags remain true after a human review. Missing model/task evidence requires review conservatively |
| Outstanding queue / `review_pending` | State is PENDING_REVIEW, IN_REVIEW or NEEDS_ADJUDICATION | N | Current workflow state, distinct from original AI flags |
| Reviewed / `reviewed` | State is REVIEWED or ADJUDICATED | N | Workflow completion, not evidence of independent human annotation |
| Adjudicated / `adjudicated` | State is ADJUDICATED | N | Current fixtures simulate adjudication only |
| Corrections / `corrections` | Reviewed records with at least one differing comparable task label | Reviewed records with at least one known human label and corresponding valid prediction at final review time | Each feedback counts at most once. Unknown/missing task labels are not comparable; missing comparisons never become agreement |
| Comparison coverage / `correction_comparison_coverage` | Correction denominator | N | Reveals how much of C supports a correction comparison, subject to suppression |
| Task label coverage / `{task}_coverage` | Selected label is a supervised taxonomy label for that task | N | Unknown severity is excluded; basis is explicit |
| Missing label rate / `{task}_missing` | Selected task label absent | N | Includes records ineligible under chosen human basis; not automatically poor model performance |
| Unknown severity / `severity_unknown` | Selected severity is unknown | N | Separate from missing and supervised severity |
| AI coverage / `{task}_ai_coverage` | Latest AI label is a valid supervised label | N | Independent of selected label basis |
| Reviewed coverage / `{task}_reviewed_coverage` | Terminal reviewed state and valid current supervised task label | N | Separates review coverage from AI coverage |
| Missing event time / `missing_event_time_in_filter_scope` | Records in S with received_at=null | Size of S | Deliberately measured before date filtering; no invented dates or ingestion-time substitution |
| Missing metadata / `agency_missing`, `domain_missing` | Null approved-metadata field | N | A missing agency/domain is not assigned to a real unit |
| Unapproved metadata / `agency_unapproved`, `domain_unapproved` | Non-null metadata outside the public synthetic allowlist | N | Values are never returned; aggregated into unapproved_metadata |
| Agency/domain distribution | Each approved public code, missing or unapproved_metadata | N for cell share | Observed counts only; no service-exposure denominator or fair agency ranking |
| Review-state distribution | Each current state | N for cell share | Historical events do not add counts |
| Sentiment × severity / `cross_tab` | Feedback with each pair of known supervised labels | N including missing_pair complement for cell share | Unknown/missing pair is explicit; suppress entire table if a positive cell is small |
| Day/week/month trend | Dated records in each local calendar bucket | Count has no rate denominator | Null-date records remain separate; bucket sentiment/severity shares use the known task labels in that bucket |

## Correction history

The comparison uses the last successful CONFIRM/CORRECT/ADJUDICATE event by review
version. For each task it selects the last prediction available at that event's UTC
timestamp. A later inference cannot rewrite historical correction rates. Current
human labels remain separate from immutable AI predictions. Repeated conflicts and
other audit events do not affect denominator size. A correction event whose proposed
labels equal AI is not counted as a changed label merely because its action is CORRECT.

## Limitations

Coverage and missingness can change with filters and selected basis. Narrow groups
are suppressed; users must not interpret null as zero. Cross-query differencing is
not eliminated by cell suppression. There is no weighting, population denominator,
causal inference, representativeness claim, model accuracy estimate or empirical
false-positive rate. The taxonomy remains pending human approval. See
[limitations](ANALYTICS_LIMITATIONS.md) before interpreting any chart.
