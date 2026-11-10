"""Optional current-run coverage; absence does not revoke historical verification."""

import os
from pathlib import Path

import pytest

from pfa.integration.smoke import smoke_postgres


@pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"), reason="Dedicated test DB not configured"
)
def test_integration_postgres_opt_in():
    result, code = smoke_postgres(Path(__file__).resolve().parents[1])
    assert code == 0, result
    assert result["POSTGRES_INTEGRATION"] == "VERIFIED"
    assert result["integration"]["prediction_nonpersistent"]
    assert result["integration"]["analytics_total"] == 10
