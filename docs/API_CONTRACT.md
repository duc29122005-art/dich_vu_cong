# Prediction API v1

API version: `1.0.0`. Response schema: `prediction-schema-1`. Frozen taxonomy: `1.0.0`.
OpenAPI is available at `/openapi.json` in local development; `/docs` provides Swagger
UI. Production disables both. All `/api/v1/` endpoints require `X-API-Key`.

| Method | Route | Result |
|---|---|---|
| GET | `/health/live` | Process ALIVE; says nothing about model validity |
| GET | `/health/ready` | 200 READY or 503 UNAVAILABLE, explicit mode and blockers |
| GET | `/api/v1/models/status` | Task availability, family, version, taxonomy, deployment status |
| POST | `/api/v1/predict` | One prediction response; unavailable service returns 503 |
| POST | `/api/v1/predict/batch` | Bounded ordered per-item results/errors |
| GET | `/api/v1/taxonomy` | Public versioned label definitions and instrument status |
| GET | `/api/v1/version` | Sanitized API/schema/package versions and mode |

There are no endpoints for training, final-test evaluation, registry mutation, file
access. STEP 13 separately adds opt-in synthetic persistence/review endpoints documented
in [workflow contract](HUMAN_REVIEW_WORKFLOW.md). Model status omits private paths, source evidence and reviewer
identities. Health is public but demo's local-peer/Host restrictions apply to all routes.

STEP 14 adds four opt-in source-scoped aggregate GET routes under
`/api/v1/analytics/{summary,topics,trends,alerts}`. See
[analytics schemas, filters and suppression](ANALYTICS_API.md). These return DEMO_ONLY
statistics and never feedback text or record identifiers. The legacy inference key
does not grant analytics access without an authorized STEP 13 principal.

## Requests

Invented SYNTHETIC example:

```json
{"text":"SYNTHETIC: Hướng dẫn thủ tục giả định chưa rõ.","request_id":"example-001"}
```

`text` is a strict nonempty string. The configured default limit is 4,000 raw Unicode
code points, before normalization; UTF-8 body limits apply separately. Whitespace-only,
malformed/control Unicode, missing/extra fields and non-string values fail. No identity
inference or external source lookup occurs. `request_id` is optional, opaque, 1–64 ASCII
letters/digits/underscores/hyphens with an alphanumeric first character. Do not place
personal information in it. It is returned but never logged; absent IDs are generated.
The separate `X-Request-ID` response header is always server-generated.

Batch requests use `{"items":[{"text":"SYNTHETIC: Nội dung giả định."}]}` with 1–16
items by default. Duplicate explicit IDs fail. Structural validation rejects the whole
batch; inference-time failures are isolated per item. Ordering is preserved. Deployment
limits can be lower than OpenAPI's absolute 20,000-character/128-item schema ceilings.

## Single response

Illustrative DEMO_ONLY fragment (all examples SYNTHETIC):

```json
{
  "request_id":"example-001",
  "processing_mode":"DEMO_ONLY",
  "model_status":"DEMO_ONLY",
  "taxonomy_version":"1.0.0",
  "predictions":{
    "topic":{"available":true,"label":"other","score":null,"score_type":"MOCK_NO_SCORE","calibrated":false,"model_version":"mock-fixture-v1"},
    "sentiment":{"available":true,"label":"neutral","score":null,"score_type":"MOCK_NO_SCORE","calibrated":false,"model_version":"mock-fixture-v1"},
    "severity":{"available":true,"label":"medium","score":null,"score_type":"MOCK_NO_SCORE","calibrated":false,"model_version":"mock-fixture-v1"}
  },
  "requires_review":true,
  "review_reasons":["CALIBRATION_OR_THRESHOLD_UNAVAILABLE","DEMO_ONLY_MOCK_NOT_NLP","DEMO_ONLY_REQUIRES_HUMAN_REVIEW","LANGUAGE_AND_SCOPE_NOT_VALIDATED"],
  "provenance":{
    "api_version":"1.0.0",
    "schema_version":"prediction-schema-1",
    "taxonomy_checksum":"500a61fd8f8fe49d31f3ec7eca955ebfe1856bb235e04ffc62d6f44f16f5af02",
    "preprocessing_version":"conservative-1",
    "provider":"MOCK_FIXTURE",
    "administrative_decision_allowed":false,
    "input_persisted":false
  },
  "warnings":["LANGUAGE_NOT_VALIDATED","NOT_AN_ADMINISTRATIVE_DECISION","DEMO_ONLY_MOCK_OUTPUTS_NOT_NLP_INFERENCE"]
}
```

Fixture labels are constants unrelated to text meaning; they are not NLP conclusions
or evidence that severity is medium. Unknown annotation severity never enters a
supervised label mapping. Review reasons are extensible machine codes; clients must
honor `requires_review` and task availability, never whitelist only familiar reasons.

`score_type` distinguishes MOCK_NO_SCORE, UNAVAILABLE, CALIBRATED_PROBABILITY,
UNCALIBRATED_DECISION_SCORE and UNCALIBRATED_LOGIT. Uncalibrated scores intentionally
remain null in this API. A calibrated number means an approved bound sigmoid method
was applied, not that percentage reliability has been scientifically validated. No
percentage-confidence claims are made. Missing calibration retains STEP 11 review flags.

Unavailable tasks have `available=false`, null label/score/version, calibrated=false
and UNAVAILABLE score type. Input privacy review may make all tasks unavailable with
`model_status=INPUT_REVIEW_REQUIRED`. Runtime task failure produces PARTIAL and review
reasons; missing required startup models instead returns 503. No response contains
the original submitted text, redacted text or private approval details.

Batch responses contain `processing_mode` and ordered `items`. Each item has a
request_id and exactly one non-null `result` (the single response) or `error`.
Per-item errors imply no prediction and require human review; never treat absence of
a result as a negative/low-severity finding. Prediction calls never enter the optional
STEP 13 review queue; explicit synthetic fixture intake is separate.

## Errors

Errors use `{"error":{"code":"INVALID_REQUEST","message":"Request could not be processed","request_id":"SERVER_GENERATED_ID"}}`.
Messages and codes never reflect arbitrary input or exception text.

| HTTP | Meaning |
|---:|---|
| 400 | Invalid headers, malformed/duplicate-key JSON or inconsistent body framing |
| 401 | Missing or incorrect API credential |
| 403 | Demo peer or Host is not local |
| 404 / 405 | Unknown endpoint or unsupported method |
| 408 | Request body receive deadline exceeded |
| 413 | Request body exceeds declared or streamed byte limit |
| 415 | Unsupported media type or compressed body |
| 422 | Invalid schema/text/ID or configured text/batch limit exceeded |
| 503 | Missing auth/model readiness, admission busy, or prediction unavailable |
| 500 | Safe internal/invalid-model-response error |

Busy responses include Retry-After. All responses use Cache-Control no-store and
X-Content-Type-Options nosniff. Clients should use liveness/readiness separately,
protect credentials, handle unavailable tasks, and retain human accountability.
