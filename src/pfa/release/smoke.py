"""Offline release validation using the real composed services and a public source manifest."""

import secrets
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient
from pydantic import SecretStr

from pfa.annotation import pilot_store as store
from pfa.api.settings import ApiSettings
from pfa.integration.smoke import smoke as integration_smoke
from pfa.release import manifest
from pfa.release.demo import application
from pfa.release.preflight import preflight


def smoke(root):
    readiness = preflight(root, isolated=True)
    if readiness["status"] == "BLOCKED" or not __debug__:
        raise ValueError("Release preflight blocked")
    integration = integration_smoke(root)
    credentials = []
    for role in ("ADMIN", "REVIEWER", "ANALYST"):
        credentials.append(
            {
                "actor_id": "demo_" + role.lower(),
                "role": role,
                "source_ids": ["synthetic_demo"],
                "can_view_text": role != "ANALYST",
                "key": secrets.token_urlsafe(48),
            }
        )
    import json

    settings = ApiSettings(
        mode="DEMO_ONLY",
        environment="test",
        api_key=None,
        principals=SecretStr(json.dumps(credentials)),
        observability_enabled=True,
    )
    with application(root, settings) as (app, _, temporary_root, fixtures):
        with TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000)) as client:
            assert client.get("/health/ready").status_code == 200
            status = client.get(
                "/api/v1/models/status", headers={"X-API-Key": credentials[0]["key"]}
            )
            assert status.status_code == 200 and status.json()["processing_mode"] == "DEMO_ONLY"
            assert all(t["family"] == "mock" for t in status.json()["tasks"].values())
    assert not temporary_root.exists()
    with TemporaryDirectory(prefix="pfa-release-manifest-") as temporary:
        target = Path(temporary) / "bundle"
        value = manifest.build(root)
        store.publish(target, {"manifest.json": value})
        documents, _ = store.bundle(target)
        verified = manifest.verify(root, documents["manifest.json"])
    assert not Path(temporary).exists()
    return {
        "status": "RELEASE_SMOKE_PASS_TECHNICAL_DEMO",
        "classification": "TECHNICAL_DEMO_ONLY",
        "integration_status": integration["status"],
        "integration_records": integration["analytics_total"],
        "launch_fixture_records": fixtures["records"],
        "model_status": "DEMO_ONLY_MOCK",
        "requires_human_review": True,
        "manifest": verified,
        "test_holdout": "PROTECTED",
        "research_results": "NOT_AVAILABLE",
        "temporary_storage_cleaned": True,
        "POSTGRES_CURRENT_RUN": "NOT_VERIFIED",
        "CI_HOSTED_RUN": "NOT_VERIFIED",
        "BACKUP_RESTORE_REHEARSAL": "NOT_VERIFIED",
    }
