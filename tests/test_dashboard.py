"""Authenticated TestClient transport and Streamlit AppTest; no public listener."""

from datetime import date
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr, ValidationError
from streamlit.testing.v1 import AppTest

from dashboard.api_client import Client, DashboardError, Settings
from dashboard.charts import bars, cross_rows, distribution_rows, explain, line
from pfa.analytics.fixtures import seed
from pfa.analytics.schemas import NOTICE, Alert, Cell, Filters
from pfa.db.smoke import environment

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def api():
    with environment(ROOT) as (client, database, headers, root):
        (root / "configs/analytics_v1.yaml").write_bytes(
            (ROOT / "configs/analytics_v1.yaml").read_bytes()
        )
        seed(database)
        yield client, headers


def test_client_uses_auth_and_filters(api):
    http, headers = api
    client = Client(Settings(api_key=SecretStr(headers["ANALYST"]["X-API-Key"])), http=http)
    result = client.fetch("summary", Filters())
    assert result.total == 420 and result.notice == NOTICE
    changed = client.fetch("summary", Filters(agency="demo_agency_a"))
    assert changed.total == 210
    empty = client.fetch("summary", Filters(start=date(2024, 1, 1), end=date(2024, 1, 2)))
    assert empty.status == "EMPTY" and empty.total == 0
    assert empty.metrics["negative_share"].share is None


def test_client_auth_and_api_errors(api):
    http, headers = api
    with pytest.raises(DashboardError, match="MISSING_API_CREDENTIAL"):
        Client(Settings(api_key=None), http=http).fetch("summary", Filters())
    with pytest.raises(DashboardError, match="AUTHORIZATION_DENIED"):
        Client(Settings(api_key=SecretStr("incorrect")), http=http).fetch("summary", Filters())
    client = Client(Settings(api_key=SecretStr(headers["ANALYST"]["X-API-Key"])), http=http)
    with pytest.raises(DashboardError, match="UNSUPPORTED_ENDPOINT"):
        client.fetch("../../private", Filters())
    with pytest.raises(DashboardError, match="API_UNAVAILABLE"):
        client.fetch("summary", Filters(model_version="unavailable"))


@pytest.mark.parametrize(
    "url",
    [
        "https://example.org",
        "http://127.0.0.1/private",
        "http://user:secret@localhost",
        "http://127.0.0.1?x=1",
    ],
)
def test_no_remote_or_credentialed_origins(url):
    with pytest.raises(ValidationError):
        Settings(api_url=url)


def test_no_sensitive_chart_payloads_and_missing_values():
    sensitive = "private@example.invalid"
    cells = [
        Cell(code="negative", count=12),
        Cell(code=sensitive, count=6),
        Cell(code="positive", count=None, suppressed=True),
    ]
    assert distribution_rows(cells) == [{"label": "Tiêu cực", "count": 12}]
    figure = bars(cells, "Phân bố giả lập").to_json()
    assert sensitive not in figure and "feedback_id" not in figure and "customdata" not in figure
    assert distribution_rows([]) == [] and cross_rows([]) == []
    assert "Không đủ" in explain(Alert(rule="volume", status="INSUFFICIENT_DATA", reason="UNKNOWN"))
    assert "ngày sự kiện" in explain(
        Alert(rule="volume", status="SUPPRESSED", reason="MISSING_EVENT_TIME_COVERAGE")
    )


def test_trend_chart_and_alert_explanations(api):
    http, headers = api
    client = Client(Settings(api_key=SecretStr(headers["ANALYST"]["X-API-Key"])), http=http)
    filters = Filters(start=date(2025, 1, 6), end=date(2025, 1, 13))
    series = client.fetch("trends", filters)
    assert len(line(series.buckets).data[0].x) == 8
    for alert in client.fetch("alerts", filters).alerts:
        assert alert.processing_mode == "DEMO_ONLY" and explain(alert)


@pytest.mark.parametrize(
    "status,payload", [(503, {"secret": "must_not_display"}), (200, {"text": "must_not_display"})]
)
def test_client_never_echoes_error_bodies(status, payload):
    class Http:
        def get(self, *args, **kwargs):
            return httpx.Response(status, json=payload)

    with pytest.raises(DashboardError) as caught:
        Client(Settings(api_key=SecretStr("synthetic_test_credential")), http=Http()).fetch(
            "summary", Filters()
        )
    assert "must_not_display" not in str(caught.value)


def test_all_dashboard_pages_via_authenticated_api(api, monkeypatch):
    http, headers = api
    monkeypatch.setenv("PFA_DASHBOARD_API_KEY", headers["ANALYST"]["X-API-Key"])
    original = Client.fetch

    def local(self, endpoint, filters):
        self.http = http
        return original(self, endpoint, filters)

    monkeypatch.setattr(Client, "fetch", local)
    app = AppTest.from_file(str(ROOT / "dashboard/app.py"), default_timeout=20).run()
    assert not app.exception and any(NOTICE in w.value for w in app.warning)
    assert app.metric[0].value == "420"
    for page in (
        "Phân tích chủ đề",
        "Cảm xúc và mức độ",
        "Xu hướng và cảnh báo",
        "Mô hình và rà soát",
    ):
        app.sidebar.radio[0].set_value(page).run()
        assert not app.exception and not app.error
        assert any(NOTICE in w.value for w in app.warning)
    app.sidebar.radio[0].set_value("Tổng quan").run()
    app.selectbox(key="agency").set_value("demo_agency_a").run()
    assert not app.exception and app.metric[0].value == "210"
    model_family = next(s for s in app.selectbox if s.label == "Họ mô hình của tác vụ lọc")
    model_family.set_value("lr").run()
    assert not app.exception and any("Không có dữ liệu" in item.value for item in app.info)
    assert any(NOTICE in w.value for w in app.warning)


def test_dashboard_auth_failure_is_safe(api, monkeypatch):
    http, _ = api
    monkeypatch.setenv("PFA_DASHBOARD_API_KEY", "invalid")
    original = Client.fetch

    def local(self, endpoint, filters):
        self.http = http
        return original(self, endpoint, filters)

    monkeypatch.setattr(Client, "fetch", local)
    app = AppTest.from_file(str(ROOT / "dashboard/app.py"), default_timeout=20).run()
    assert not app.exception and app.error
    assert "Không được phép" in app.error[0].value
    assert any(NOTICE in w.value for w in app.warning)
