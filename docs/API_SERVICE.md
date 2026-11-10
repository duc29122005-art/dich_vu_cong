# STEP 12: local prediction service

This service is a technical demo, not a production deployment. No approved research
dataset or model exists. Genuine pretrained PhoBERT remains unverified. The default
APPROVED_MODEL configuration reports unavailable prediction readiness. It never falls
back to mock predictions. STEP 13 adds optional synthetic persistence; STEP 14 adds
authenticated aggregate dashboards. See [review operations](HUMAN_REVIEW_WORKFLOW.md)
and the STEP 17 [local technical demo quickstart](DEMO_QUICKSTART.md).

## Windows setup

Use Python 3.11 and the existing virtual environment:

```powershell
.\.venv\Scripts\python.exe -m pip install -e '.[api]'
.\.venv\Scripts\python.exe -m pfa.cli api smoke
.\.venv\Scripts\python.exe -m pfa.cli api status
```

The existing `api` extra retains its pre-existing optional database dependencies;
database connections remain disabled by default. FastAPI 0.162.0, Starlette
1.10.0, HTTPX 0.28.1 and Uvicorn 0.54.0 were used for verification. The API smoke
uses TestClient, synthetic Vietnamese input and a temporary directory. It opens no
public listener, downloads no model and cleans up. `status` starts only an in-process
application lifespan; it exits 3 when prediction readiness is unavailable, 0 when ready.

For an explicitly configured local demo, generate a new private process credential:

```powershell
$env:PFA_API_KEY = & .\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
$env:PFA_API_MODE = 'DEMO_ONLY'
.\.venv\Scripts\python.exe -m pfa.cli api status
.\.venv\Scripts\python.exe -m pfa.cli api serve --host 127.0.0.1 --port 8000
# In the same protected environment, use invented examples only:
$headers = @{ 'X-API-Key' = $env:PFA_API_KEY }
$payload = @{ text = 'SYNTHETIC: Hướng dẫn thủ tục giả định chưa rõ.'; request_id = 'example-001' } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/api/v1/predict' -Headers $headers -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($payload))
# Remove the process credential after stopping the server:
Remove-Item Env:PFA_API_KEY
```

Never print, commit or share that credential. It is not a reusable example secret.
The CLI serves one worker, loopback only, with proxy-header trust and access logging
disabled. `uvicorn pfa.api.main:app --host 127.0.0.1 --port 8000 --no-access-log --no-proxy-headers`
is an alternative; retain those security settings. An import starts no listener.

## Configuration

`configs/api_v1.yaml` records public defaults; it is not a credential file or an
automatic override. Set `PFA_API_MODE`, `PFA_API_MAX_TEXT_LENGTH`,
`PFA_API_MAX_BATCH_SIZE`, `PFA_API_MAX_BODY_BYTES`, `PFA_API_BODY_TIMEOUT_SECONDS`,
`PFA_API_MAX_CONCURRENCY`, and `PFA_API_CORS_ORIGINS` through protected environment
configuration. Origins use a JSON list. `PFA_API_KEY` is environment-only; the API
settings do not read a dotenv credential file. The existing `PFA_PROJECT_ROOT` and
`PFA_ENVIRONMENT` settings still apply. Production forbids DEMO_ONLY. No authentication
bypass setting exists. Missing credentials keep prediction readiness unavailable.

Defaults: raw text 4,000 Unicode code points, 16 batch items, 262,144 body bytes,
five seconds to receive a body, one concurrent prediction request. Absolute schema
ceilings are 20,000 code points and 128 items; deployment settings may be stricter.
Body limits apply to both declared size and actual streamed bytes. Batches preserve
order and process items sequentially to bound memory and isolate failures.

## Architecture and lifecycle

`app_factory.create_app` owns lifespan startup/shutdown. Schemas, security middleware,
prediction orchestration and providers are separate small modules. FastAPI dependencies
retrieve the lifespan-owned service. `PredictionProvider` supports mock and registry
implementations; replacing a provider through the factory is restricted to isolated tests.

Demo fixtures always return topic `other`, sentiment `neutral`, severity `medium`,
independently of text meaning. Scores are null, calibrated is false, and every output
requires review. These are not scientific predictions or human labels. Ambiguous
privacy candidates instead return unavailable tasks and require human review.

Registry startup obtains active models through STEP 11. It validates current data
rights, model approvals, artifact integrity, frozen taxonomy and preprocessing,
final-evaluation/locked-experiment bindings, validation-selected winners, and calibration
and threshold provenance. Baseline pickle requires its explicit trust approval.
PhoBERT requires the exact local segmentation config, supplied by registry ID through
`PFA_API_SEGMENTERS_FILE` pointing inside protected `data/private/`. No request can
specify an artifact ID/path or mutate the registry. Synthetic artifacts are rejected.

Heavy model objects load once at startup and release on shutdown. Before each prediction
request, control evidence and checksums are revalidated without deserializing models
again. The existing registry validator may read authorized frozen train/validation
partitions while verifying provenance; no serving path reads protected test labels.
This conservative control check is expensive for future real corpora. Any active model
or experiment change requires process restart; no unreviewed hot reload exists.

Readiness requires all three task models and authentication. A partial startup blocks
prediction with 503. A task inference failure returns an explicit unavailable task and
review flag, and disables subsequent readiness until restart. Missing calibration does
not invent confidence: scores stay null and the STEP 11 policy requires review.
High-severity predictions retain their policy reason. All inputs additionally require
review while language and scope validation remain unavailable. The service makes no
administrative decision and persists no input text.

See [contract](API_CONTRACT.md) and [security limits](API_SECURITY.md). Authorized real
serving remains blocked pending source/privacy approval, real pilot/gold data, approved
models, verified PhoBERT if selected, deployment-scope authorization and security review.
