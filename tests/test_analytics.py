"""Synthetic formula, governance and calendar tests. No real datasets or model downloads."""

import json
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
from sqlalchemy import event, select

from pfa.analytics import alerts, kpis, trends
from pfa.analytics.fixtures import seed
from pfa.analytics.repository import Row
from pfa.analytics.schemas import NOTICE, Config, Filters, Report
from pfa.analytics.smoke import smoke
from pfa.api.app_factory import create_app
from pfa.api.identity import Principal
from pfa.api.settings import ApiSettings
from pfa.cli import main
from pfa.data.official_io import IngestionBlocked
from pfa.db.models import Feedback, Prediction, ReviewEvent
from pfa.db.repository import Repository
from pfa.db.smoke import create as create_feedback
from pfa.db.smoke import environment

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def seeded():
    with environment(ROOT) as value:
        client, database, headers, root = value
        (root / "configs/analytics_v1.yaml").write_bytes(
            (ROOT / "configs/analytics_v1.yaml").read_bytes()
        )
        seed(database)
        yield value


@pytest.fixture
def empty():
    with environment(ROOT) as value:
        (value[3] / "configs/analytics_v1.yaml").write_bytes(
            (ROOT / "configs/analytics_v1.yaml").read_bytes()
        )
        yield value


def get(system, endpoint="summary", role="ANALYST", **params):
    client, _, headers, _ = system
    return client.get("/api/v1/analytics/" + endpoint, headers=headers[role], params=params)


def record(day=None, sentiment="negative", severity="high", topic="fees", state="PENDING_REVIEW"):
    return Row(
        event_time=day,
        agency=None,
        domain=None,
        state=state,
        human={},
        ai=dict(topic=topic, sentiment=sentiment, severity=severity),
    )


def test_synthetic_smoke(monkeypatch):
    from pfa.data import corpus

    def forbidden(*args, **kwargs):
        pytest.fail("Analytics accessed governed research/holdout records")

    monkeypatch.setattr(corpus, "model_selection", forbidden)
    monkeypatch.setattr(corpus, "evaluation_data", forbidden)
    result = smoke(ROOT)
    assert result["status"] == "ANALYTICS_SMOKE_PASS_SYNTHETIC"
    assert result["temporary_storage_cleaned"] and result["POSTGRES_INTEGRATION"] == "NOT_VERIFIED"


def test_known_formulas_and_coverage(seeded):
    report = Report.model_validate(get(seeded).json())
    assert report.total == 420 and report.notice == NOTICE
    assert report.metrics["negative_share"].share == pytest.approx(250 / 420)
    assert report.metrics["high_severity_share"].share == pytest.approx(147 / 420)
    assert report.metrics["review_required"].share == 1
    assert report.metrics["review_pending"].numerator == 210
    assert report.metrics["reviewed"].share == 0.5
    assert report.metrics["adjudicated"].numerator == 105
    assert report.metrics["corrections"].share == pytest.approx(85 / 210)
    assert report.metrics["severity_unknown"].numerator == 0
    assert sum(c.count for c in report.distributions["topic"]) == 420
    assert report.top_complaint_topic == "fees"


def test_basis_never_falls_back_to_ai(seeded):
    prediction = get(seeded).json()
    reviewed = get(seeded, basis="reviewed").json()
    adjudicated = get(seeded, basis="adjudicated").json()
    assert reviewed["metrics"]["topic_missing"]["numerator"] == 210
    assert adjudicated["metrics"]["topic_missing"]["numerator"] == 315
    assert adjudicated["metrics"]["severity_unknown"]["numerator"] == 53
    assert adjudicated["metrics"]["severity_missing"]["numerator"] == 315
    assert prediction["distributions"]["topic"] != reviewed["distributions"]["topic"]
    assert reviewed["metrics"]["corrections"] == adjudicated["metrics"]["corrections"]


@pytest.mark.parametrize(
    "params,expected",
    [
        ({"agency": "demo_agency_a"}, 210),
        ({"domain": "demo_domain_a"}, 210),
        ({"review_status": "REVIEWED"}, 105),
        ({"sentiment": "negative"}, 250),
        ({"severity": "high"}, 147),
        ({"model_family": "mock"}, 420),
        ({"model_version": "analytics-fixture-v1"}, 420),
        ({"model_family": "lr"}, 0),
        ({"agency": "demo_agency_a", "domain": "demo_domain_a"}, 105),
        ({"source_id": "synthetic_demo", "start": "2025-01-13", "end": "2025-01-13"}, 120),
    ],
)
def test_filter_combinations(seeded, params, expected):
    response = get(seeded, **params)
    assert response.status_code == 200
    assert response.json()["total"] == expected


@pytest.mark.parametrize(
    "params",
    [
        {"start": "2025-01-01"},
        {"start": "bad", "end": "2025-01-13"},
        {"start": "2025-01-14", "end": "2025-01-13"},
        {"start": "2025-01-01", "end": "2026-01-02"},
        {"start": "2025-01-01T00:00:00", "end": "2025-01-13"},
        {"start": "9999-12-31", "end": "9999-12-31"},
        {"agency": "not_approved"},
        {"domain": "not_approved"},
        {"topic": "invalid"},
        {"basis": "mixed"},
        {"interval": "hour"},
        {"model_version": "not_a_model"},
        {"model_version": "../../secret"},
        {"small_group": "1"},
        {"extra": "secret"},
    ],
)
def test_invalid_filters_are_safe(seeded, params):
    response = get(seeded, **params)
    assert response.status_code == 422 and "secret" not in response.text


@pytest.mark.parametrize("endpoint", ["summary", "topics", "trends", "alerts"])
def test_auth_rbac_source_and_response_schema(seeded, endpoint):
    client, _, _, _ = seeded
    assert client.get("/api/v1/analytics/" + endpoint).status_code == 401
    for role in ("ADMIN", "REVIEWER", "ANALYST"):
        result = get(seeded, endpoint, role=role)
        assert result.status_code == 200
        Report.model_validate(result.json())
        assert result.json()["notice"] == NOTICE
    assert (
        get(seeded, endpoint, source_id="public_service_official", role="ADMIN").status_code == 403
    )


def test_no_text_or_record_identifiers_or_permission_changes(seeded, caplog):
    client, database, headers, root = seeded
    before = (root / "configs/dataset_sources.yaml").read_bytes()
    statements = []

    def observe(connection, cursor, statement, parameters, context, many):
        statements.append(statement)

    event.listen(database.engine, "before_cursor_execute", observe)
    caplog.set_level("INFO", logger="pfa.api")
    try:
        responses = [
            get(seeded, endpoint).text for endpoint in ("summary", "topics", "trends", "alerts")
        ]
    finally:
        event.remove(database.engine, "before_cursor_execute", observe)
    assert all("text_redacted" not in sql for sql in statements)
    assert all("source_record_ref" not in sql for sql in statements)
    payload = "".join(responses)
    assert all(
        word not in payload
        for word in (
            "feedback_id",
            "prediction_id",
            "actor_reference",
            "review_event_id",
            "Phản ánh dịch vụ giả định",
        )
    )
    assert "Phản ánh dịch vụ giả định" not in caplog.text
    assert all(h["X-API-Key"] not in caplog.text for h in headers.values())
    assert (root / "configs/dataset_sources.yaml").read_bytes() == before
    assert client.get("/health/live").status_code == 200


@pytest.mark.parametrize("endpoint", ["summary", "topics", "trends", "alerts"])
def test_empty_database_and_zero_denominators(empty, endpoint):
    result = get(empty, endpoint).json()
    assert result["status"] == "EMPTY" and result["total"] == 0
    assert all(m["share"] is None for m in result["metrics"].values())
    assert not result["buckets"]


def test_suppression_binary_partition_and_zero():
    assert kpis.metric(0, 0, 5).share is None
    assert kpis.metric(0, 20, 5).share == 0
    assert kpis.metric(20, 20, 5).share == 1
    assert kpis.metric(1, 20, 5).suppressed
    assert kpis.metric(19, 20, 5).suppressed
    result = kpis.cells(Counter(a=19, b=1), ["a", "b", "missing"], 5)
    assert all(c.suppressed and c.count is None and c.share is None for c in result)


def test_suppression_protects_conditional_denominators():
    rows = [record() for _ in range(20)]
    rows[0].ai["sentiment"] = None
    metrics, distributions, top, cross = kpis.summarize(rows, "prediction", 5)
    assert metrics["negative_share"].suppressed
    assert top is None and all(c.suppressed for c in distributions["complaint_topic"])
    assert all(c.suppressed for c in cross)


def test_missing_predictions_and_all_missing_event_dates(empty):
    client, database, headers, _ = empty
    for index in range(5):
        assert create_feedback(client, headers["ADMIN"], fixture_id=index).status_code == 201
    result = get(empty).json()
    assert result["metrics"]["missing_event_time_in_filter_scope"]["share"] == 1
    assert get(empty, "trends").json()["buckets"] == []
    assert all(
        a["reason"] == "MISSING_EVENT_TIME_COVERAGE" for a in get(empty, "alerts").json()["alerts"]
    )
    assert get(empty, "trends", start="2025-01-01", end="2025-01-02").json()["total"] == 0


def test_capacity_fails_instead_of_truncating(empty):
    _, database, _, root = empty
    seed(database)
    document = json.loads((root / "configs/analytics_v1.yaml").read_text("utf-8"))
    document["max_records"] = 100
    (root / "configs/analytics_v1.yaml").write_text(json.dumps(document), "utf-8")
    assert get(empty).status_code == 503


def test_whole_narrow_cohort_suppression(seeded):
    result = get(
        seeded,
        agency="demo_agency_a",
        start="2025-01-06",
        end="2025-01-06",
        topic="delayed_processing",
    ).json()
    # Five examples are retained; another filter makes the cohort zero, never a leaked count 1..4.
    assert result["total"] == 5
    result = get(
        seeded,
        agency="demo_agency_a",
        start="2025-01-13",
        end="2025-01-13",
        topic="delayed_processing",
    ).json()
    assert result["status"] == "SUPPRESSED" and result["total"] is None
    assert result["metrics"] == {} and result["distributions"] == {} and result["models"] == []


def test_event_dates_timezone_and_null_guard():
    rows = [
        record(datetime(2025, 1, 5, 16, 59, 59, tzinfo=UTC)),
        record(datetime(2025, 1, 5, 17, 0, tzinfo=UTC)),
        record(None),
    ]
    assert trends.local_date(rows[0]) == date(2025, 1, 5)
    assert trends.local_date(rows[1]) == date(2025, 1, 6)
    buckets, members = trends.group(
        rows, Filters(start=date(2025, 1, 6), end=date(2025, 1, 6)), Config()
    )
    assert len(members[0]) == 1 and buckets[0].count is None
    with pytest.raises(ValueError):
        trends.local_date(record(datetime(2025, 1, 1)))


def test_week_month_and_partial_boundaries(seeded):
    weekly = get(seeded, "trends", interval="week", start="2025-01-06", end="2025-01-13").json()[
        "buckets"
    ]
    assert [b["count"] for b in weekly] == [280, 120]
    assert weekly[0]["complete_calendar_window"] and not weekly[1]["complete_calendar_window"]
    monthly = get(seeded, "trends", interval="month", start="2025-01-01", end="2025-01-31").json()[
        "buckets"
    ]
    assert monthly[0]["count"] == 400
    assert monthly[0]["start"] == "2025-01-01" and monthly[0]["end_exclusive"] == "2025-02-01"
    assert trends.next_bucket(date(2024, 12, 1), "month") == date(2025, 1, 1)
    assert trends.next_bucket(date(2024, 2, 1), "month") == date(2024, 3, 1)


def test_missing_dates_reported_before_window_filter(seeded):
    result = get(seeded, "trends", start="2025-01-06", end="2025-01-06").json()
    assert result["total"] == 40
    assert result["metrics"]["missing_event_time_in_filter_scope"]["numerator"] == 20
    assert result["metrics"]["missing_event_time_in_filter_scope"]["denominator"] == 420


def series(counts, high_share=0.25, *, current_share=None):
    rows = []
    for day, count in enumerate(counts):
        proportion = (
            current_share if current_share is not None and day == len(counts) - 1 else high_share
        )
        for position in range(count):
            rows.append(
                record(
                    datetime(2025, 1, 6 + day, tzinfo=UTC),
                    severity="high" if position < count * proportion else "low",
                    topic="fees" if position % 2 else "other",
                )
            )
    filters = Filters(start=date(2025, 1, 6), end=date(2025, 1, 5 + len(counts)))
    buckets, members = trends.group(rows, filters, Config(), today=date(2025, 2, 1))
    return buckets, members, filters


def test_alert_stable_and_synthetic_spike():
    buckets, members, filters = series([40] * 8)
    assert all(
        a.status == "NORMAL" for a in alerts.evaluate(buckets, members, filters, Config(), 0)
    )
    buckets, members, filters = series([40] * 7 + [120], current_share=0.7)
    result = alerts.evaluate(buckets, members, filters, Config(), 0)
    assert result[0].status == result[1].status == "TRIGGERED"
    assert result[2].status == "NORMAL"


@pytest.mark.parametrize(
    "counts,missing,reason",
    [
        ([0] * 7 + [1], 0, "INSUFFICIENT_WINDOW_SUPPORT"),
        ([2] * 7 + [5], 0, "INSUFFICIENT_WINDOW_SUPPORT"),
        ([40] * 7 + [120], 0.5, "MISSING_EVENT_TIME_COVERAGE"),
        ([40] * 7 + [120], None, "MISSING_EVENT_TIME_COVERAGE"),
        ([40] * 3, 0, "INSUFFICIENT_BASELINE_WINDOWS"),
    ],
)
def test_alert_insufficient_evidence(counts, missing, reason):
    buckets, members, filters = series(counts)
    result = alerts.evaluate(buckets, members, filters, Config(), missing)
    assert all(a.status != "TRIGGERED" and a.reason == reason for a in result)


def test_alert_low_count_rare_class_and_partial_window():
    buckets, members, filters = series([40] * 8, high_share=0)
    members[-1][0].ai["severity"] = "high"
    result = alerts.evaluate(buckets, members, filters, Config(), 0)
    assert result[1].status == "SUPPRESSED" and result[1].observed is None
    buckets[-1].complete_calendar_window = False
    assert all(
        a.reason == "PARTIAL_CALENDAR_WINDOW"
        for a in alerts.evaluate(buckets, members, filters, Config(), 0)
    )


def test_alert_respects_configured_cell_threshold():
    buckets, members, filters = series([40] * 7 + [120])
    result = alerts.evaluate(buckets, members, filters, Config(small_group=100), 0)
    assert all(a.status == "INSUFFICIENT_DATA" and a.observed is None for a in result)


def test_share_alerts_reject_poor_known_label_coverage():
    buckets, members, filters = series([40] * 7 + [120])
    for row in members[-1][:100]:
        row.ai["severity"] = "unknown"
        row.ai["topic"] = None
    result = alerts.evaluate(buckets, members, filters, Config(), 0)
    assert result[0].status == "TRIGGERED"
    assert all(
        a.status == "SUPPRESSED" and a.reason == "MISSING_LABEL_COVERAGE" and a.observed is None
        for a in result[1:]
    )


def test_alert_window_references(seeded):
    result = get(seeded, "alerts", start="2025-01-06", end="2025-01-13").json()
    assert all(
        a["window_start"] == "2025-01-13" and a["window_end_exclusive"] == "2025-01-14"
        for a in result["alerts"]
    )
    assert all(
        a["baseline_start"] == "2025-01-06" and a["baseline_end_exclusive"] == "2025-01-13"
        for a in result["alerts"]
    )
    buckets, members, filters = series([40] * 8)
    filters.interval = "week"
    assert all(
        a.reason == "DAILY_ALERT_WINDOWS_REQUIRED"
        for a in alerts.evaluate(buckets, members, filters, Config(), 0)
    )


def test_later_predictions_and_extra_events_do_not_duplicate_feedback(empty):
    client, database, headers, root = empty
    seed(database)
    with database.sessions() as session, session.begin():
        row = session.scalar(select(Feedback).where(Feedback.review_status == "REVIEWED"))
        original = session.scalar(
            select(Prediction).where(
                Prediction.feedback_id == row.feedback_id, Prediction.task == "topic"
            )
        )
        values = {c.key: getattr(original, c.key) for c in Prediction.__table__.columns}
        session.add(
            Prediction(
                **{
                    **values,
                    "prediction_id": uuid4(),
                    "predicted_label": row.current_topic,
                    "created_at": datetime(2026, 1, 1, tzinfo=UTC),
                }
            )
        )
        for _ in range(10):
            session.add(
                ReviewEvent(
                    feedback_id=row.feedback_id,
                    operation_id=uuid4(),
                    actor_reference="synthetic_actor",
                    actor_role="REVIEWER",
                    action_type="CONFLICT",
                    reason_code="STALE_VERSION",
                    review_version=None,
                )
            )
    report = get(empty).json()
    assert report["total"] == 420
    assert report["metrics"]["corrections"]["numerator"] == 85
    assert report["metrics"]["corrections"]["denominator"] == 210


def test_configuration_and_source_tampering_fail_closed(empty):
    _, database, _, root = empty
    seed(database)
    document = json.loads((root / "configs/dataset_sources.yaml").read_text("utf-8"))
    source = next(s for s in document["sources"] if s["source_id"] == "synthetic_demo")
    source["description"] += " changed"
    (root / "configs/dataset_sources.yaml").write_text(json.dumps(document), "utf-8")
    assert get(empty).status_code == 403
    with database.sessions() as session:
        principal = Principal(
            actor_id="synthetic_analyst", role="ANALYST", source_ids=["public_service_official"]
        )
        with pytest.raises(HTTPException):
            Repository(root, session, principal).permit("public_service_official")
    config = Config()
    with pytest.raises(ValidationError):
        Config(small_group=1)
    assert config.small_group == 5


def test_seed_never_overwrites_or_changes_permissions(seeded):
    _, database, _, root = seeded
    before = (root / "configs/dataset_sources.yaml").read_bytes()
    with pytest.raises(IngestionBlocked, match="empty"):
        seed(database)
    assert (root / "configs/dataset_sources.yaml").read_bytes() == before


def test_missing_persistence_and_legacy_auth_fail_closed(empty):
    _, _, headers, root = empty
    settings = ApiSettings(
        mode="DEMO_ONLY", environment="test", api_key=SecretStr("x" * 48), principals=None
    )
    app = create_app(
        settings, root=root, database_factory=lambda: (_ for _ in ()).throw(ValueError("private"))
    )
    with TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50001)) as client:
        assert client.get("/health/live").status_code == 200
        assert (
            client.get("/api/v1/analytics/summary", headers={"X-API-Key": "x" * 48}).status_code
            == 403
        )
    app = create_app(
        ApiSettings(
            mode="DEMO_ONLY", environment="test", principals=empty[0].app.state.settings.principals
        ),
        root=root,
        database_factory=lambda: (_ for _ in ()).throw(ValueError("private")),
    )
    with TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50001)) as client:
        result = client.get("/api/v1/analytics/summary", headers=headers["ANALYST"])
        assert result.status_code == 503 and "private" not in result.text


def test_cli_smoke(capsys):
    assert main(["analytics", "smoke"]) == 0
    assert "ANALYTICS_SMOKE_PASS_SYNTHETIC" in capsys.readouterr().out


def test_seed_cli_requires_explicit_demo(monkeypatch, capsys):
    monkeypatch.setenv("PFA_API_MODE", "APPROVED_MODEL")
    assert main(["analytics", "seed-demo"]) == 3
    assert "DEMO_ONLY" in capsys.readouterr().out
