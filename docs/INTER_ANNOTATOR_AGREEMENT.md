# Inter-annotator agreement

```powershell
.\.venv\Scripts\python.exe -m pfa.cli annotation agreement --pilot pilot_v1
```

Compare latest immutable independent A/B revisions without changing them. Reports
bind pilot/submission checksums; corrections create distinct report versions.
Protected reports include no feedback text or justifications, only non-identifying
IDs, labels and aggregate statistics.

## Metrics and denominators

Each task receives unweighted Cohen's Kappa, raw agreement percentage, comparable
count, fixed-label confusion matrix, class distributions, rare-class warnings and
disagreement counts. Kappa is `(observed - expected) / (1 - expected)`; expected
agreement uses A/B marginal frequencies. Severity uses nominal, not ordinal Kappa.

Only matched expected IDs from independent annotators are comparable. Repeated
IDs, unexpected IDs, identical annotator identities or mixed provenance fail.
For each task, expected records partition into comparable pairs and:

- `missing_annotation`: either side is absent;
- `excluded_workflow`: either side is OUT_OF_SCOPE or UNLABELABLE;
- `unknown_or_missing_label`: a supervised label is absent, including unknown severity.

Unknown severity excludes severity only. Known labels on REQUIRES_REVIEW records
remain comparable. Workflow-state disagreement and missing/excluded counts are
separate and visible. No difficult cases are silently dropped or relabeled.

Zero comparable pairs yield null raw agreement and null Kappa. Expected agreement
of one gives undefined/null Kappa even if raw agreement is 100%. Negative Kappa
is valid. Missing submissions yield NOT_AVAILABLE (CLI exit 4). Interpret class
imbalance and rare classes with the full matrix, not Kappa alone.

Kappa >= 0.70 is a provisional project review target, not proof of scientific
validity. Low agreement generates human review recommendations for handbook
boundaries and calibration. Never alter labels automatically to improve scores.
Disagreement rows show feedback ID, task, A/B labels, category and human-adjudication
status; pair frequencies summarize confusion. Only controlled review exports have text.

## Known synthetic check

| Task | Comparable pairs | Raw agreement | Kappa |
|---|---:|---:|---:|
| Topic | 8 | 75% | 0.50 |
| Sentiment | 8 | 75% | 0.60 |
| Severity | 8 | 75% | 0.60 |

These predetermined software fixtures are not human agreement measurements,
research findings or scientifically validated taxonomy evidence.
