# Synthetic persistence and human review

Current service supports invented fixtures only. The project has one independent
student researcher and no supervisor or independent validation team. Synthetic actors,
corrections and adjudication tests establish software behavior only. No database review
becomes STEP 07 gold, an independent annotation, agreement statistic or model approval.

Enable `PFA_DB_MODE=SYNTHETIC`, migrate a local PostgreSQL development database, set
`PFA_API_MODE=DEMO_ONLY`, and provide protected `PFA_API_PRINCIPALS`. Keep the server on
loopback. SQLite remains an internal test backend. See [RBAC](RBAC_MATRIX.md) and
[migrations](DATABASE_MIGRATIONS.md). The ordinary `PFA_API_KEY` grants no database role.

| Action | From | To | Required actor |
|---|---|---|---|
| CREATE | Absent | PENDING_REVIEW | ADMIN, authorized synthetic source |
| CLAIM | PENDING_REVIEW | IN_REVIEW | Text-authorized REVIEWER |
| ASSIGN | PENDING_REVIEW | IN_REVIEW | ADMIN, designated text-authorized reviewer |
| CONFIRM / CORRECT | IN_REVIEW | REVIEWED | Assigned REVIEWER |
| ESCALATE | IN_REVIEW | NEEDS_ADJUDICATION | Assigned REVIEWER |
| ADJUDICATE | NEEDS_ADJUDICATION | ADJUDICATED | REVIEWER with explicit adjudication grant |

State changes use a version-checked SQL UPDATE and append an event in the same
transaction. Failed audit insertion rolls back the state change. Stale/invalid writes
return 409 and append a conflict where possible. Duplicate operation IDs return 409
without repeating the original action. No read-modify-write overwrite is allowed.
Terminal items cannot reopen through these endpoints; a future revision workflow
requires explicit design. Confirmation copies the original three available predictions;
correction requires three valid labels. Unknown severity requires
`INSUFFICIENT_EVIDENCE` and remains a workflow outcome, never a supervised model label.
Out-of-scope/unlabelable conditions escalate rather than fabricate labels.

## API contract

All routes require verified `X-API-Key`; roles come from server configuration.
UUIDs below are opaque invented identifiers. Generate a new operation UUID per action.

```json
{"fixture_id":0,"operation_id":"0875a42b-c9b9-44de-85a7-b15bfe595503"}
```

POST `/api/v1/feedback` (ADMIN) returns 201. Fixture IDs are integers 0–119 and resolve
to bundled invented content. The server screens this content before persistence.
Arbitrary `text`, `text_redacted`, role/model paths or extra fields return 422. Real
source/flag requests return 403; even an ADMIN cannot create real feedback. Repeated
fixture/source references return 409. The model provider must return DEMO_ONLY with
null scores; no synthetic output can be relabeled as an approved model.

GET `/api/v1/feedback` accepts `limit` (1–100, default 20), `offset` (0–100000),
`status`, `source_id`, `include_text` (default false). It returns `{items,total,limit,
offset}`. GET `/api/v1/feedback/{id}` returns one authorized record. Text requires an
explicit grant. GET `/api/v1/reviews/queue` uses the same pagination/filter options and
requires ADMIN/REVIEWER. Default queue contains pending, in-review and escalated items.

PATCH `/api/v1/reviews/{id}` accepts:

```json
{"operation_id":"54c19b22-a9d6-4029-a795-9686063ed625","expected_version":1,"action":"CLAIM","reason_code":"CLAIM"}
```

An illustrative response fragment is:

```json
{"processing_mode":"DEMO_ONLY","review_status":"IN_REVIEW","version":2,"is_synthetic":true,"received_at":null,"current_labels":null}
```

Correction after claim:

```json
{"operation_id":"0f7b1327-77db-4d7d-9ac4-cf7100a5d440","expected_version":2,"action":"CORRECT","reason_code":"CORRECTION","labels":{"topic":"fees","sentiment":"negative","severity":"high"}}
```

The full response includes immutable `predictions` keyed by task, prediction UUID,
model reference, inference mode, score semantics, review reasons and sanitized model
provenance. `current_labels` stores the human workflow decision separately. Predictions
always retain their original requires_review flag. Feedback view's processing mode is
DEMO_ONLY. No administrative decision or research qualification is returned.

GET `/api/v1/reviews/{id}/history` is ADMIN-only and paginated. There are no history
update/delete endpoints. HTTP: 400 malformed JSON; 401 missing/wrong key; 403 role,
source or text denial; 404 missing ID; 409 conflict/duplicate/invalid transition;
422 invalid schema; 503 unavailable database/provider. Errors never reflect submitted
content or connection details. `/predict` and `/predict/batch` never save inputs.
