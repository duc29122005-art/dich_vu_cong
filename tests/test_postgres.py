"""Requires explicitly configured dedicated local PostgreSQL; never substitutes SQLite."""

import os
from pathlib import Path

import pytest

from pfa.db.postgres import smoke


@pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"), reason="Dedicated TEST_DATABASE_URL not configured"
)
def test_postgresql_integration():
    result, code = smoke(Path(__file__).resolve().parents[1])
    assert code == 0, result
    assert result["POSTGRES_INTEGRATION"] == "VERIFIED"
