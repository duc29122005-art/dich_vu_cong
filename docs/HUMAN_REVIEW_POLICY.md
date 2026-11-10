# Abstention and human review

No model output authorizes an administrative decision. Every policy result includes
`administrative_decision_allowed=false`. A human remains responsible for consequential
actions, even when an engineering policy labels a record eligible for automation.

`evaluation_policy.review` requires review for invalid artifacts, unsupported or
out-of-scope input, explicitly conflicting predictions, missing calibrated scores,
unavailable validation-selected thresholds, low calibrated score, or disagreement
between the native predicted class and calibrated argmax. Predicted severity-high
requires review by default. Unsupported conditions fail closed. The caller must
perform artifact/input validation and pass its result; these flags do not themselves
implement out-of-distribution detection or guarantee safety.

Threshold selection uses only the grouped threshold-validation role. The fixed
protocol grid selects greatest automated coverage subject to at least five automated
records and empirical selective risk at most 0.10. Ties retain the first ascending
threshold. Those defaults are research proposals, not approved operational safety
limits. If no threshold qualifies, all records require review. A human must approve
the risk target and review capacity before operational use.

Metrics report review rate, automated coverage, selective risk on automated records,
and automated critical misses (true high severity predicted otherwise). No automated
records yields null selective risk. No observed high-severity support yields null
critical misses/high recall rather than an unsupported zero-risk claim. Counts remain
descriptive; small samples do not establish a reliable safety guarantee.

Unknown severity is an annotation state excluded from severity training/evaluation.
It never becomes low severity. Inference cannot infer a trustworthy severity from
insufficient evidence merely because a head returns a score. Authorized reviewers
should inspect sanitized content and permitted metadata through the existing review
workflow. Aggregate evaluation/registry reports contain no original feedback.

Thresholds and safety settings lock with the experiment before final-test access.
Do not change them after inspecting final results, choose thresholds on test labels,
or promote synthetic models to research/production. Future mock API work may expose
review flags only; this step implements no API or administrative automation.
