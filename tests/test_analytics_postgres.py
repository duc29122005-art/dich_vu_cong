"""Explicitly optional PostgreSQL aggregate-query verification in a fresh owned schema."""

import os
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from pfa.analytics.fixtures import seed
from pfa.db.smoke import environment


@pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"), reason="Dedicated TEST_DATABASE_URL not configured"
)
def test_postgresql_analytics_queries():
    supplied = os.environ["TEST_DATABASE_URL"]
    url = make_url(supplied)
    assert url.drivername == "postgresql+psycopg" and url.host in {"localhost", "127.0.0.1", "::1"}
    assert url.database and url.database.endswith("_test") and not url.query
    schema = "pfa_test_" + uuid4().hex
    engine = create_engine(url, hide_parameters=True, connect_args={"connect_timeout": 5})
    owned = False
    root = Path(__file__).resolve().parents[1]
    try:
        with engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            owned = True
        with environment(root, postgres_url=supplied, schema=schema) as (
            client,
            database,
            headers,
            temporary,
        ):
            (temporary / "configs/analytics_v1.yaml").write_bytes(
                (root / "configs/analytics_v1.yaml").read_bytes()
            )
            seed(database)
            for endpoint in ("summary", "topics", "trends", "alerts"):
                response = client.get("/api/v1/analytics/" + endpoint, headers=headers["ANALYST"])
                assert (
                    response.status_code == 200
                    and response.json()["processing_mode"] == "DEMO_ONLY"
                )
                assert response.json()["total"] == 420
            summary = client.get("/api/v1/analytics/summary", headers=headers["ANALYST"]).json()
            assert summary["metrics"]["corrections"]["numerator"] == 85
            assert database.engine.dialect.name == "postgresql"
    finally:
        try:
            if owned:
                with engine.begin() as connection:
                    connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        finally:
            engine.dispose()
