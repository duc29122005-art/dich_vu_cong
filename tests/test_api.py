"""Invented offline API fixtures only; research serving gates are explicitly mocked in tests."""

import copy
import json
import logging
import secrets
from pathlib import Path

import anyio
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from pfa.annotation import pilot_store as store
from pfa.annotation.taxonomy import CHECKSUM, VERSION
from pfa.api import schemas
from pfa.api.app_factory import create_app
from pfa.api.providers import DemoProvider, RegistryProvider
from pfa.api.security import Boundary
from pfa.api.settings import ApiSettings
from pfa.cli import main
from pfa.data import corpus
from pfa.data.official_io import IngestionBlocked
from pfa.ml import baseline, model_adapters, model_registry
from pfa.ml.evaluation_policy import Protocol

ROOT = Path(__file__).resolve().parents[1]
TEXT = "SYNTHETIC: Tôi chưa thấy hướng dẫn rõ cho hồ sơ giả định."


@pytest.fixture
def key():
    return secrets.token_urlsafe(48)


def config(key, **kwargs):
    return ApiSettings(mode="DEMO_ONLY", environment="test", api_key=SecretStr(key), **kwargs)


@pytest.fixture
def client(key):
    app = create_app(config(key), root=ROOT)
    with TestClient(
        app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000), headers={"X-API-Key": key}
    ) as client:
        yield client


def test_default_config_and_yaml(monkeypatch):
    monkeypatch.delenv("PFA_API_MODE", raising=False)
    monkeypatch.delenv("PFA_API_KEY", raising=False)
    defaults = ApiSettings()
    assert defaults.mode == "APPROVED_MODEL" and defaults.api_key is None
    for name, value in store.read_json(ROOT / "configs/api_v1.yaml").items():
        assert getattr(defaults, name) == value


@pytest.mark.parametrize(
    "changes",
    [
        {"host": "0.0.0.0"},
        {"max_text_length": 0},
        {"max_batch_size": 129},
        {"max_body_bytes": 99999999},
        {"body_timeout_seconds": float("nan")},
        {"max_concurrency": 0},
        {"cors_origins": ["*"]},
        {"cors_origins": ["https://example.test/path"]},
        {"cors_origins": ["https://secret@example.test"]},
        {"api_key": "short"},
        {"mode": "DEMO_ONLY", "environment": "production"},
    ],
)
def test_bad_configuration(changes):
    with pytest.raises(ValueError):
        ApiSettings(**changes)


def test_environment_secret_and_explicit_demo(monkeypatch, key):
    monkeypatch.setenv("PFA_API_KEY", key)
    monkeypatch.setenv("PFA_API_MODE", "DEMO_ONLY")
    value = ApiSettings()
    assert value.mode == "DEMO_ONLY" and value.api_key.get_secret_value() == key
    assert key not in repr(value) + json.dumps(value.public()) + value.model_dump_json()


def test_app_lifespan_load_once_cleanup(key):
    provider = DemoProvider()
    loaded = []
    original = provider.load

    def load():
        loaded.append(True)
        original()

    provider.load = load
    app = create_app(config(key), root=ROOT, provider_factory=lambda: provider)
    assert not provider.loaded
    with TestClient(
        app, base_url="http://localhost", client=("127.0.0.1", 50000), headers={"X-API-Key": key}
    ) as client:
        for _ in range(2):
            assert client.post("/api/v1/predict", json={"text": TEXT}).status_code == 200
        assert provider.loaded and loaded == [True]
    assert not provider.loaded
    with pytest.raises(ValueError):
        create_app(
            ApiSettings(mode="DEMO_ONLY", api_key=SecretStr(key)), provider_factory=DemoProvider
        )


def test_health_taxonomy_version_and_openapi(client):
    assert client.get("/health/live").json() == {"status": "ALIVE"}
    ready = client.get("/health/ready")
    assert ready.status_code == 200 and ready.json()["processing_mode"] == "DEMO_ONLY"
    status = client.get("/api/v1/models/status").json()
    assert set(status["tasks"]) == set(baseline.TASKS)
    assert all(value["deployment_status"] == "DEMO_ONLY" for value in status["tasks"].values())
    assert client.get("/api/v1/taxonomy").json()["version"] == VERSION
    assert client.get("/api/v1/version").json()["schema_version"] == schemas.SCHEMA_VERSION
    document = client.get("/openapi.json").json()
    assert set(document["paths"]) == {
        "/health/live",
        "/health/ready",
        "/api/v1/models/status",
        "/api/v1/predict",
        "/api/v1/predict/batch",
        "/api/v1/taxonomy",
        "/api/v1/version",
    }
    assert document["components"]["securitySchemes"]["APIKeyHeader"]["name"] == "X-API-Key"
    assert document["paths"]["/api/v1/predict"]["post"]["security"]


def test_consistent_demo_single_batch_and_negation(client):
    result = client.post("/api/v1/predict", json={"text": TEXT, "request_id": "fixture-001"})
    assert result.status_code == 200
    parsed = schemas.PredictionResponse.model_validate(result.json())
    assert parsed.request_id == "fixture-001" and parsed.requires_review
    assert parsed.provenance.administrative_decision_allowed is False
    assert parsed.processing_mode == "DEMO_ONLY"
    for prediction in parsed.predictions.model_dump().values():
        assert prediction["score"] is None and not prediction["calibrated"]
        assert prediction["score_type"] == "MOCK_NO_SCORE"
    assert TEXT not in result.text
    assert result.headers["cache-control"] == "no-store"
    batch = client.post(
        "/api/v1/predict/batch", json={"items": [{"text": TEXT}, {"text": "SYNTHETIC: Không rõ."}]}
    )
    parsed_batch = schemas.BatchResponse.model_validate(batch.json())
    assert len(parsed_batch.items) == 2 and all(
        item.result.requires_review for item in parsed_batch.items
    )
    assert all(
        "CALIBRATION_OR_THRESHOLD_UNAVAILABLE" in item.result.review_reasons
        for item in parsed_batch.items
    )


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"text": ""},
        {"text": " \n\t"},
        {"text": 42},
        {"text": None},
        {"text": TEXT, "path": "sensitive-secret"},
        {"text": "\ud800"},
        {"text": "SYNTHETIC\x00private"},
        {"text": "SYNTHETIC\u202esecret"},
        {"text": "\ufffd"},
        {"text": "!!!"},
        {"text": "\U0001fffe"},
        {"text": TEXT, "request_id": "../../private"},
        {"text": TEXT, "request_id": "name@example.test"},
    ],
)
def test_invalid_requests_no_input_reflection(client, body):
    response = client.post(
        "/api/v1/predict",
        content=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_REQUEST"
    assert "input" not in response.json()["error"] and TEXT not in response.text
    assert "sensitive-secret" not in response.text and "private" not in response.text


@pytest.mark.parametrize(
    "payload", [b"{", b'{"text":"a","text":"private"}', b'{"text":NaN}', b"\xff"]
)
def test_malformed_json_safe(client, payload):
    response = client.post(
        "/api/v1/predict", content=payload, headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 400 and "private" not in response.text


def test_limits_and_content_types(key):
    app = create_app(
        config(key, max_text_length=40, max_batch_size=2, max_body_bytes=1024), root=ROOT
    )
    with TestClient(
        app, base_url="http://localhost", client=("127.0.0.1", 50000), headers={"X-API-Key": key}
    ) as client:
        assert client.post("/api/v1/predict", json={"text": "x" * 41}).status_code == 422
        assert client.post("/api/v1/predict", json={"text": "x" * 1100}).status_code == 413
        assert (
            client.post(
                "/api/v1/predict/batch", json={"items": [{"text": "SYNTHETIC"}] * 3}
            ).status_code
            == 422
        )
        assert client.post("/api/v1/predict", content=b"private").status_code == 415
        assert (
            client.post(
                "/api/v1/predict", json={"text": TEXT}, headers={"Content-Encoding": "gzip"}
            ).status_code
            == 415
        )
        assert client.post("/api/v1/predict/batch", json={"items": []}).status_code == 422
        assert (
            client.post(
                "/api/v1/predict/batch",
                json={"items": [{"text": "SYNTHETIC", "request_id": "same"}] * 2},
            ).status_code
            == 422
        )


def test_authentication_and_missing_credentials(key):
    app = create_app(config(key), root=ROOT)
    with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as client:
        assert client.get("/health/live").status_code == 200
        for path in ("/api/v1/models/status", "/api/v1/taxonomy", "/api/v1/version"):
            assert client.get(path).status_code == 401
        for supplied in ("wrong", "", "x" * 500):
            assert (
                client.post(
                    "/api/v1/predict", headers={"X-API-Key": supplied}, json={"text": TEXT}
                ).status_code
                == 401
            )
    app = create_app(ApiSettings(mode="DEMO_ONLY", environment="test", api_key=None), root=ROOT)
    with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as client:
        assert client.get("/health/ready").status_code == 503
        assert client.post("/api/v1/predict", json={"text": TEXT}).status_code == 503
        assert not app.state.service.provider.loaded


def test_local_only_ignores_forwarded_headers(key):
    app = create_app(config(key), root=ROOT)
    with TestClient(
        app,
        base_url="http://localhost",
        client=("198.51.100.7", 50000),
        headers={"X-API-Key": key, "X-Forwarded-For": "127.0.0.1"},
    ) as client:
        assert client.get("/health/live").status_code == 403
        assert client.post("/api/v1/predict", json={"text": TEXT}).status_code == 403
    with TestClient(app, base_url="http://evil.test", client=("127.0.0.1", 50000)) as client:
        assert client.get("/health/live").status_code == 403


def test_cors_allowlist(key):
    app = create_app(config(key, cors_origins=["http://localhost:3000"]), root=ROOT)
    with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as client:
        headers = {
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "X-API-Key,Content-Type",
        }
        response = client.options("/api/v1/predict", headers=headers)
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
        assert (
            client.options(
                "/api/v1/predict", headers=headers | {"Origin": "https://evil.test"}
            ).status_code
            == 400
        )


def test_no_privacy_content_in_logs_or_errors(client, key, caplog):
    caplog.set_level(logging.INFO, logger="pfa.api")
    sentinel = "SYNTHETIC_PRIVATE_SENTINEL"
    response = client.post("/api/v1/predict", json={"text": sentinel + " contact@example.test"})
    assert response.status_code == 200 and response.json()["requires_review"]
    assert "PRIVACY_SCREENING_REQUIRES_REVIEW" in response.json()["review_reasons"]
    invalid = client.post("/api/v1/predict", json={"text": sentinel, sentinel: key})
    assert invalid.status_code == 422
    output = response.text + invalid.text + caplog.text
    assert sentinel not in output and "contact@example.test" not in output and key not in output
    for record in caplog.records:
        if record.name == "pfa.api":
            assert set(json.loads(record.message)) == {
                "event",
                "trace_id",
                "route",
                "status",
                "duration_ms",
            }


def test_ambiguous_privacy_input_never_reaches_provider(client, monkeypatch):
    monkeypatch.setattr(
        client.app.state.service.provider,
        "predict",
        lambda *args: pytest.fail("Sensitive input reached model"),
    )
    response = client.post("/api/v1/predict", json={"text": "SYNTHETIC: họ và tên: ví dụ giả định"})
    assert (
        response.status_code == 200 and response.json()["model_status"] == "INPUT_REVIEW_REQUIRED"
    )
    assert all(not p["available"] for p in response.json()["predictions"].values())


def test_concurrency_limit(client):
    service = client.app.state.service
    service.slots.acquire()
    try:
        response = client.post("/api/v1/predict", json={"text": TEXT})
        assert response.status_code == 503 and response.headers["retry-after"] == "1"
    finally:
        service.slots.release()
    assert client.post("/api/v1/predict", json={"text": TEXT}).status_code == 200


def test_batch_per_item_failure_is_safe(client, monkeypatch):
    original = client.app.state.service.provider.predict

    def fail_one(texts):
        if "FAIL_SENTINEL" in texts[0]:
            raise RuntimeError(texts[0])
        return original(texts)

    monkeypatch.setattr(client.app.state.service.provider, "predict", fail_one)
    response = client.post(
        "/api/v1/predict/batch",
        json={"items": [{"text": TEXT}, {"text": "SYNTHETIC FAIL_SENTINEL"}]},
    )
    assert response.status_code == 200
    assert response.json()["items"][0]["result"] is not None
    assert response.json()["items"][1]["error"]["code"] == "PREDICTION_UNAVAILABLE"
    assert "FAIL_SENTINEL" not in response.text


def test_default_missing_approved_models_no_dataset_or_holdout(key, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Dataset or final holdout accessed")

    monkeypatch.setattr(corpus, "_read_partition", forbidden)
    monkeypatch.setattr(corpus, "evaluation_data", forbidden)
    app = create_app(ApiSettings(api_key=SecretStr(key)), root=ROOT)
    with TestClient(app, headers={"X-API-Key": key}) as client:
        assert client.get("/health/live").status_code == 200
        assert client.get("/health/ready").status_code == 503
        response = client.post("/api/v1/predict", json={"text": TEXT})
        assert response.status_code == 503
        status = client.get("/api/v1/models/status").json()
        assert status["processing_mode"] == "APPROVED_MODEL" and not status["ready"]
        assert "data/private" not in json.dumps(status)


@pytest.fixture
def controls(tmp_path, monkeypatch):
    """Mocked registry/model boundary only. No real approval, model or data is created."""
    (tmp_path / "configs").mkdir()
    for name in ("taxonomy_v1.yaml", "dataset_sources.yaml"):
        (tmp_path / "configs" / name).write_bytes((ROOT / "configs" / name).read_bytes())
    protocol = Protocol().model_dump()
    binding = {"dataset_type": "RESEARCH", "MOCK_ONLY_NOT_A_DATASET": True}
    records, models = {}, {}
    for task in baseline.TASKS:
        descriptor = {
            "task": task,
            "family": "lr",
            "model_kind": "lr",
            "dataset": binding,
            "labels": list(baseline.TASKS[task]),
            "taxonomy_checksum": CHECKSUM,
            "taxonomy_version": VERSION,
            "preprocessing": {"normalization": "conservative-1"},
            "validation": {"macro_f1": 0.0},
        }
        record = {"run_id": "mock_" + task, "model": descriptor}
        records[task] = record
        provenance = {
            "evaluation_split": "validation",
            "dataset": binding,
            "model_sha256": store.digest(descriptor),
            "protocol_sha256": store.digest(protocol),
            "roles": {},
        }
        models[record["run_id"]] = {
            "descriptor": descriptor,
            "calibrator": {"status": "UNAVAILABLE", "provenance": provenance},
            "threshold": {"status": "ALL_REQUIRE_REVIEW", "provenance": provenance},
        }
    experiment = {
        "dataset": binding,
        "protocol": protocol,
        "models": models,
        "roles": {},
        "selected_by_task": {task: record["run_id"] for task, record in records.items()},
        "trust_references": {},
    }
    base = model_registry.base(tmp_path)
    checksum = store.publish(base / "experiments/mock_experiment", {"experiment.json": experiment})
    store.publish(base / "locks/mock_experiment", {"lock.json": {"experiment_sha256": checksum}})
    report = {
        "dataset_type": "RESEARCH",
        "dataset": binding,
        "selected_by_task": experiment["selected_by_task"],
        "experiment_id": "mock_experiment",
        "experiment_sha256": checksum,
    }
    final_hash = store.publish(base / "final_results/mock_final", {"report.json": report})
    mutable = {"revoked": False, "bad_output": False, "high": False}

    def active(root, registry, task):
        if mutable["revoked"]:
            raise IngestionBlocked("SYNTHETIC_PRIVATE_EXCEPTION")
        return records[task]

    monkeypatch.setattr(model_registry, "active", active)
    monkeypatch.setattr(
        model_registry,
        "history",
        lambda *args: (
            [
                {
                    "run_id": r["run_id"],
                    "action": "RESEARCH_APPROVED",
                    "evaluation": {"id": "mock_final", "sha256": final_hash},
                }
                for r in records.values()
            ],
            None,
        ),
    )
    monkeypatch.setattr(model_registry, "authorize", lambda *args: {"MOCK_ONLY": True})
    loads = []

    class FakeAdapter:
        def __init__(self, root, registry, descriptor, **kwargs):
            self.descriptor = descriptor
            loads.append(descriptor["task"])

        def predict(self, texts):
            labels = self.descriptor["labels"]
            label = (
                "high" if self.descriptor["task"] == "severity" and mutable["high"] else labels[0]
            )
            return {
                "label_order": list(reversed(labels)) if mutable["bad_output"] else labels,
                "labels": [label] * len(texts),
                "scores": [[3 if value == label else -1 for value in labels] for _ in texts],
            }

    monkeypatch.setattr(model_adapters, "Adapter", FakeAdapter)
    return tmp_path, records, experiment, mutable, loads


def approved_app(controls, key):
    return create_app(ApiSettings(api_key=SecretStr(key), environment="test"), root=controls[0])


def test_cached_registry_bridge_missing_calibration_review(controls, key):
    app = approved_app(controls, key)
    with TestClient(app, headers={"X-API-Key": key}) as client:
        assert client.get("/health/ready").status_code == 200
        for _ in range(2):
            response = client.post("/api/v1/predict", json={"text": TEXT})
            assert response.status_code == 200 and response.json()["requires_review"]
            assert "CALIBRATION_OR_THRESHOLD_UNAVAILABLE" in response.json()["review_reasons"]
            assert all(
                not p["calibrated"] and p["score"] is None
                for p in response.json()["predictions"].values()
            )
        assert sorted(controls[4]) == sorted(baseline.TASKS)
    assert app.state.service.provider.runtimes == {}


@pytest.mark.parametrize("change", ["taxonomy", "labels", "preprocessing", "synthetic", "checksum"])
def test_registry_bridge_rejects_invalid_material(controls, key, change):
    root, records, _, _, loads = controls
    if change == "taxonomy":
        records["topic"]["model"]["taxonomy_checksum"] = "0" * 64
    elif change == "labels":
        records["topic"]["model"]["labels"].reverse()
    elif change == "preprocessing":
        records["topic"]["model"]["preprocessing"]["normalization"] = "wrong"
    elif change == "synthetic":
        records["topic"]["model"]["dataset"] = {"dataset_type": "SYNTHETIC"}
    else:
        (model_registry.base(root) / "experiments/mock_experiment/experiment.json").write_text("{}")
    app = approved_app(controls, key)
    with TestClient(app, headers={"X-API-Key": key}) as client:
        assert client.get("/health/ready").status_code == 503
        assert client.post("/api/v1/predict", json={"text": TEXT}).status_code == 503
        assert "topic" not in loads
        assert not client.get("/api/v1/models/status").json()["tasks"]["topic"]["available"]


def test_revocation_and_bad_output_fail_closed(controls, key):
    app = approved_app(controls, key)
    with TestClient(app, headers={"X-API-Key": key}) as client:
        controls[3]["bad_output"] = True
        result = client.post("/api/v1/predict", json={"text": TEXT})
        assert result.status_code == 200 and result.json()["requires_review"]
        assert all(not p["available"] for p in result.json()["predictions"].values())
        assert client.get("/health/ready").status_code == 503
    app = approved_app(controls, key)
    controls[3]["bad_output"] = False
    with TestClient(app, headers={"X-API-Key": key}) as client:
        controls[3]["revoked"] = True
        response = client.post("/api/v1/predict", json={"text": TEXT})
        assert response.status_code == 503 and "SYNTHETIC_PRIVATE_EXCEPTION" not in response.text


def test_high_severity_policy_through_registry_provider(controls, key):
    provider = RegistryProvider(controls[0], ApiSettings(api_key=SecretStr(key)))
    provider.load()
    controls[3]["high"] = True
    prediction, reasons = provider.predict([TEXT])[0]["severity"]
    assert prediction.label == "high" and "SEVERITY_HIGH_REQUIRES_HUMAN" in reasons
    provider.close()


def test_calibrated_registry_path_has_explicit_semantics(controls, key, monkeypatch):
    root, records, original, mutable, _ = controls
    experiment = copy.deepcopy(original)
    for task, record in records.items():
        model = experiment["models"][record["run_id"]]
        model["calibrator"] = {
            "status": "FITTED",
            "labels": list(baseline.TASKS[task]),
            "coefficients": [1.0] * len(baseline.TASKS[task]),
            "intercepts": [0.0] * len(baseline.TASKS[task]),
            "provenance": model["calibrator"]["provenance"],
        }
        model["threshold"] = {
            "status": "SELECTED_ON_THRESHOLD_VALIDATION",
            "threshold": 0.5,
            "provenance": model["threshold"]["provenance"],
        }
    base = model_registry.base(root)
    checksum = store.publish(base / "experiments/mock_calibrated", {"experiment.json": experiment})
    store.publish(base / "locks/mock_calibrated", {"lock.json": {"experiment_sha256": checksum}})
    report = {
        "dataset_type": "RESEARCH",
        "dataset": experiment["dataset"],
        "selected_by_task": experiment["selected_by_task"],
        "experiment_id": "mock_calibrated",
        "experiment_sha256": checksum,
    }
    checksum = store.publish(base / "final_results/mock_calibrated", {"report.json": report})
    monkeypatch.setattr(
        model_registry,
        "history",
        lambda *args: (
            [
                {
                    "run_id": r["run_id"],
                    "action": "RESEARCH_APPROVED",
                    "evaluation": {"id": "mock_calibrated", "sha256": checksum},
                }
                for r in records.values()
            ],
            None,
        ),
    )
    mutable["high"] = True
    app = approved_app(controls, key)
    with TestClient(app, headers={"X-API-Key": key}) as client:
        response = client.post("/api/v1/predict", json={"text": TEXT})
        assert response.status_code == 200
        value = response.json()
        assert (
            value["requires_review"] and "SEVERITY_HIGH_REQUIRES_HUMAN" in value["review_reasons"]
        )
        assert "LANGUAGE_AND_SCOPE_NOT_VALIDATED" in value["review_reasons"]
        for prediction in value["predictions"].values():
            assert prediction["calibrated"] and prediction["score_type"] == "CALIBRATED_PROBABILITY"
            assert 0 <= prediction["score"] <= 1
        assert "CALIBRATION_IS_NOT_A_RELIABILITY_GUARANTEE" in value["warnings"]


def test_structured_identifiers_redacted_before_model(client, monkeypatch):
    provider = client.app.state.service.provider
    original = provider.predict
    captured = []

    def capture(texts):
        captured.extend(texts)
        return original(texts)

    monkeypatch.setattr(provider, "predict", capture)
    response = client.post(
        "/api/v1/predict", json={"text": "SYNTHETIC: Không gửi lại cho contact@example.test"}
    )
    assert response.status_code == 200 and response.json()["requires_review"]
    assert "contact@example.test" not in captured[0] and "Không" in captured[0]
    assert "[REDACTED_EMAIL]" in captured[0]


def test_control_tampering_after_cached_load_blocks_without_reload(controls, key):
    app = approved_app(controls, key)
    with TestClient(app, headers={"X-API-Key": key}) as client:
        assert client.get("/health/ready").status_code == 200
        artifact = model_registry.base(controls[0]) / "experiments/mock_experiment/experiment.json"
        artifact.write_text("{}")
        assert client.post("/api/v1/predict", json={"text": TEXT}).status_code == 503
        assert len(controls[4]) == 3


def test_internal_exception_never_reflects_input(client, monkeypatch, caplog):
    def fail():
        raise RuntimeError("SYNTHETIC_PRIVATE_FAILURE")

    monkeypatch.setattr(client.app.state.service.provider, "check", fail)
    response = client.get("/health/ready")
    assert response.status_code == 500
    assert "SYNTHETIC_PRIVATE_FAILURE" not in response.text + caplog.text


def test_production_has_no_docs_or_demo(key):
    app = create_app(ApiSettings(environment="production", api_key=SecretStr(key)), root=ROOT)
    with TestClient(app) as client:
        assert client.get("/docs").status_code == 404
        assert client.get("/openapi.json").status_code == 404
        assert client.get("/health/ready").status_code == 503


def test_response_rejects_unknown_labels_and_fake_demo_confidence():
    with pytest.raises(ValueError):
        schemas.Predictions(
            topic=schemas.TaskPrediction(available=True, label="invented", model_version="mock"),
            sentiment=schemas.TaskPrediction(available=False),
            severity=schemas.TaskPrediction(available=False),
        )
    with pytest.raises(ValueError):
        schemas.TaskPrediction(
            available=True,
            label="neutral",
            model_version="mock",
            score=0.9,
            score_type="MOCK_NO_SCORE",
        )


def test_raw_chunk_limit_and_timeout(key):
    async def run_case(timeout):
        received, sent = 0, []

        async def never_called(*args):
            pytest.fail("Oversized body reached application")

        boundary = Boundary(
            never_called, config(key, max_body_bytes=1024, body_timeout_seconds=0.1)
        )
        scope = {
            "type": "http",
            "path": "/api/v1/predict",
            "method": "POST",
            "client": ("127.0.0.1", 0),
            "headers": [
                (b"host", b"localhost"),
                (b"x-api-key", key.encode()),
                (b"content-type", b"application/json"),
            ],
        }

        async def receive():
            nonlocal received
            received += 1
            if timeout:
                await anyio.sleep(0.2)
            return {"type": "http.request", "body": b"x" * 600, "more_body": True}

        async def send(message):
            sent.append(message)

        await boundary(scope, receive, send)
        assert sent[0]["status"] == (408 if timeout else 413)
        assert received == (1 if timeout else 2)

    anyio.run(run_case, False)
    anyio.run(run_case, True)


def test_smoke_cli_no_data_access(monkeypatch, capsys):
    monkeypatch.setenv("PFA_PROJECT_ROOT", str(ROOT))

    def forbidden(*args, **kwargs):
        pytest.fail("API smoke accessed data or promoted a model")

    monkeypatch.setattr(corpus, "_read_partition", forbidden)
    monkeypatch.setattr(corpus, "evaluation_data", forbidden)
    monkeypatch.setattr(model_registry, "activate", forbidden)
    assert main(["api", "smoke"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "API_SMOKE_PASS_SYNTHETIC" and result["temporary_storage_cleaned"]
    assert result["approved_model_blocked"] and not result["test_labels_read"]
    monkeypatch.delenv("PFA_API_KEY", raising=False)
    monkeypatch.setenv("PFA_API_MODE", "APPROVED_MODEL")
    assert main(["api", "status"]) == 3
    assert not json.loads(capsys.readouterr().out)["prediction_ready"]
