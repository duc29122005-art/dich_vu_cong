"""Deterministic invented inputs, through the existing validation/privacy contracts."""

from pydantic import ValidationError

from pfa.annotation import pilot_store as store
from pfa.annotation.taxonomy import Topic
from pfa.data.corpus_smoke import fixture
from pfa.data.official_schema import Feedback
from pfa.data.preprocessing import normalize_text
from pfa.data.privacy import audit_screen


def generate():
    rows, provenance = fixture(120)
    rows[2].content = rows[0].content + " Minh họa giả lập."
    for index, row in enumerate(rows):
        row.content = normalize_text(row.content)
        if index % 10 == 0:
            row.event_time = None
        Feedback(
            feedback_id=row.feedback_id,
            content=row.content,
            created_at=row.event_time,
            source_id=row.source_id,
        )
        assert not audit_screen(row.content).counts
    assert len({r.labels["topic"] for r in rows}) == len(Topic.__args__)
    assert rows[0].content == rows[1].content
    assert rows[2].content.startswith(rows[0].content) and rows[2].content != rows[0].content
    rejected = 0
    for text in ("", "   ", "\ud800"):
        try:
            normalize_text(text)
        except (ValueError, UnicodeError):
            rejected += 1
    try:
        Feedback(
            feedback_id="synthetic_bad",
            content="invented",
            source_id="synthetic_demo",
            created_at="not-a-date",
        )
    except ValidationError:
        rejected += 1
    assert rejected == 4
    sensitive = "SYNTHETIC: Hộp thư giả lập screening@example.invalid cần được che."
    screened = audit_screen(sensitive)
    assert screened.counts and "screening@example.invalid" not in screened.text
    return rows, {
        **provenance,
        "normalized_sha256": store.digest([r.model_dump(mode="json") for r in rows]),
        "preprocessing_version": "conservative-1",
        "missing_timestamp_cases": 12,
        "missing_severity_cases": sum(r.labels["severity"] is None for r in rows),
        "invalid_rejected": rejected,
        "privacy_fixture_screened": True,
        "near_duplicate_checked": True,
    }
