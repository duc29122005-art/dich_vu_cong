"""Offline API analytics validation with invented fixtures in disposable SQLite."""

import io
import logging

from sqlalchemy import select

from pfa.analytics.fixtures import seed
from pfa.analytics.schemas import NOTICE, Report
from pfa.db.models import Feedback
from pfa.db.smoke import environment


def smoke(project_root):
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    logger = logging.getLogger("pfa.api")
    logger.addHandler(handler)
    previous = logger.level
    logger.setLevel(logging.INFO)
    try:
        with environment(project_root) as (client, database, headers, root):
            (root / "configs/analytics_v1.yaml").write_bytes(
                (project_root / "configs/analytics_v1.yaml").read_bytes()
            )
            seeded = seed(database)

            def get(endpoint, **params):
                response = client.get(
                    "/api/v1/analytics/" + endpoint, params=params, headers=headers["ANALYST"]
                )
                assert response.status_code == 200, response.text
                result = Report.model_validate(response.json())
                assert result.notice == NOTICE and result.processing_mode == "DEMO_ONLY"
                return result

            summary = get("summary")
            assert summary.total == 420
            assert summary.metrics["negative_share"].numerator == 250
            assert summary.metrics["high_severity_share"].numerator == 147
            assert summary.metrics["reviewed"].numerator == 210
            assert summary.metrics["corrections"].numerator == 85
            assert summary.metrics["corrections"].denominator == 210
            assert summary.metrics["missing_event_time_in_filter_scope"].numerator == 20
            assert get("summary", agency="demo_agency_a").total == 210
            assert get("summary", basis="adjudicated").metrics["severity_unknown"].numerator == 53
            assert get("topics").distributions["topic"]
            series = get("trends", start="2025-01-06", end="2025-01-13")
            assert [b.count for b in series.buckets] == [40] * 7 + [120]
            assert series.metrics["missing_event_time_in_filter_scope"].numerator == 20
            weekly = get("trends", start="2025-01-06", end="2025-01-13", interval="week")
            assert [b.count for b in weekly.buckets] == [280, 120]
            alerts = get("alerts", start="2025-01-06", end="2025-01-13")
            assert all(a.status == "TRIGGERED" for a in alerts.alerts)
            assert client.get("/api/v1/analytics/summary").status_code == 401
            assert (
                client.get(
                    "/api/v1/analytics/summary",
                    params={"source_id": "public_service_official"},
                    headers=headers["ADMIN"],
                ).status_code
                == 403
            )
            with database.sessions() as session:
                private_text = session.scalar(select(Feedback.text_redacted))
            payload = (
                summary.model_dump_json() + series.model_dump_json() + alerts.model_dump_json()
            )
            assert private_text not in payload and "feedback_id" not in payload
            assert private_text not in stream.getvalue()
            assert all(h["X-API-Key"] not in stream.getvalue() for h in headers.values())
            result = {
                "status": "ANALYTICS_SMOKE_PASS_SYNTHETIC",
                "notice": NOTICE,
                "records": seeded["records"],
                "dated": seeded["dated"],
                "missing_event_time": 20,
                "negative_count": 250,
                "high_severity_count": 147,
                "reviewed": 210,
                "corrected": 85,
                "comparison_denominator": 210,
                "daily_counts": [40] * 7 + [120],
                "triggered_demo_rules": [a.rule for a in alerts.alerts],
                "raw_text_exposed": False,
                "research_or_holdout_accessed": False,
                "POSTGRES_INTEGRATION": "NOT_VERIFIED",
            }
        return {**result, "temporary_storage_cleaned": not root.exists()}
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous)
        handler.close()
