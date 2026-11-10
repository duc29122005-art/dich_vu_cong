"""Offline in-process TestClient demonstration. No public server or real dataset."""

import io
import logging
import secrets
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient
from pydantic import SecretStr

from pfa.api.app_factory import create_app
from pfa.api.settings import ApiSettings


def smoke(project_root: Path):
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    logger = logging.getLogger("pfa.api")
    previous = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        with TemporaryDirectory(prefix="pfa-api-synthetic-") as temporary:
            root = Path(temporary)
            (root / "configs").mkdir()
            for name in ("taxonomy_v1.yaml", "dataset_sources.yaml"):
                (root / "configs" / name).write_bytes(
                    (project_root / "configs" / name).read_bytes()
                )
            key = secrets.token_urlsafe(48)
            settings = ApiSettings(mode="DEMO_ONLY", environment="test", api_key=SecretStr(key))
            app = create_app(settings, root=root)
            text = "SYNTHETIC: Tôi chưa thấy hướng dẫn thủ tục tại quầy giả định."
            with TestClient(
                app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000)
            ) as client:
                assert client.get("/health/live").status_code == 200
                assert client.get("/health/ready").status_code == 200
                assert client.post("/api/v1/predict", json={"text": text}).status_code == 401
                headers = {"X-API-Key": key}
                result = client.post("/api/v1/predict", headers=headers, json={"text": text})
                assert result.status_code == 200
                single = result.json()
                assert single["processing_mode"] == "DEMO_ONLY" and single["requires_review"]
                assert all(
                    p["score"] is None and not p["calibrated"]
                    for p in single["predictions"].values()
                )
                batch = client.post(
                    "/api/v1/predict/batch",
                    headers=headers,
                    json={
                        "items": [
                            {"text": text},
                            {"text": "SYNTHETIC: Hồ sơ giả định cần hướng dẫn."},
                        ]
                    },
                )
                assert batch.status_code == 200 and len(batch.json()["items"]) == 2
                assert all(item["result"]["requires_review"] for item in batch.json()["items"])
                invalid = client.post("/api/v1/predict", headers=headers, json={"text": "   "})
                assert invalid.status_code == 422 and "text" not in invalid.text
                assert (
                    client.get("/api/v1/models/status", headers=headers).json()["processing_mode"]
                    == "DEMO_ONLY"
                )
                assert client.get("/api/v1/taxonomy", headers=headers).status_code == 200
                assert client.get("/api/v1/version", headers=headers).status_code == 200
                assert client.get("/openapi.json").status_code == 200
            assert not app.state.service.provider.loaded
            blocked = create_app(
                ApiSettings(mode="APPROVED_MODEL", environment="test", api_key=SecretStr(key)),
                root=root,
            )
            with TestClient(blocked) as client:
                assert client.get("/health/ready").status_code == 503
                assert (
                    client.post("/api/v1/predict", headers=headers, json={"text": text}).status_code
                    == 503
                )
            assert text not in stream.getvalue() and key not in stream.getvalue()
            assert not (root / "data").exists()
            summary = {
                "status": "API_SMOKE_PASS_SYNTHETIC",
                "processing_mode": "DEMO_ONLY",
                "single_prediction_verified": True,
                "batch_items": 2,
                "authentication_verified": True,
                "requires_review": True,
                "mock_scores": None,
                "approved_model_blocked": True,
                "input_text_logged": False,
                "real_dataset_accessed": False,
                "test_labels_read": False,
                "model_downloaded": False,
                "lifespan_cleanup_verified": True,
            }
        return {**summary, "temporary_storage_cleaned": not root.exists()}
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous)
        handler.close()
