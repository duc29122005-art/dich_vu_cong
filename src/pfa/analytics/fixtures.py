"""Invented dated fixtures and simulated review events, never human research annotations."""

from datetime import UTC, datetime, timedelta
from typing import get_args
from uuid import NAMESPACE_URL, uuid4, uuid5
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from pfa.annotation import pilot_store as store
from pfa.annotation.taxonomy import CHECKSUM, VERSION, Topic
from pfa.data.official_io import IngestionBlocked
from pfa.data.privacy import audit_screen
from pfa.data.registry import load_registry
from pfa.db.models import Feedback, ModelVersion, Prediction, ReviewEvent, SourceRegistry


def seed(database, *, identifier_seed=None):
    if identifier_seed is not None and (
        type(identifier_seed) is not int or not 0 <= identifier_seed < 2**32
    ):
        raise ValueError("Invalid synthetic identifier seed")

    def identity(reference):
        # The known mathematical fixture is fixed; seed only changes reproducible opaque IDs.
        return (
            uuid4()
            if identifier_seed is None
            else uuid5(NAMESPACE_URL, f"pfa-synthetic-release-1:{identifier_seed}:{reference}")
        )

    if database.settings.mode != "SYNTHETIC":
        raise IngestionBlocked("Explicit synthetic database required")
    database.validate()
    source = load_registry(database.root / "configs/dataset_sources.yaml").source("synthetic_demo")
    if source.dataset_role != "SYNTHETIC":
        raise IngestionBlocked("Synthetic source declaration required")
    codes = get_args(Topic)
    stamp = datetime(2025, 1, 1, tzinfo=UTC)
    with database.sessions() as session, session.begin():
        # Never overwrite, clear, or silently reuse an existing private dataset.
        if any(
            session.scalar(select(func.count()).select_from(table))
            for table in (Feedback, Prediction, ReviewEvent, SourceRegistry, ModelVersion)
        ):
            raise IngestionBlocked("Synthetic demo seeding requires an explicitly empty database")
        session.add(
            SourceRegistry(
                source_id="synthetic_demo",
                registry_sha256=store.digest(source.model_dump()),
                provenance_reference="SYNTHETIC_ANALYTICS_FIXTURE_V1",
                source_kind="SYNTHETIC",
                created_at=stamp,
            )
        )
        models = {}
        for task in ("topic", "sentiment", "severity"):
            model = ModelVersion(
                model_version_id=identity("model:" + task),
                registry_reference="analytics-fixture-v1",
                task=task,
                inference_mode="DEMO_ONLY",
                family="mock",
                descriptor_sha256=store.digest({"task": task, "fixture": "analytics-1"}),
                taxonomy_version=VERSION,
                taxonomy_checksum=CHECKSUM,
                preprocessing_version="conservative-1",
                created_at=stamp,
            )
            session.add(model)
            models[task] = model
        session.flush()
        for index in range(420):
            day, position = (index // 40, index % 40) if index < 280 else (7, index - 280)
            undated = index >= 400
            spike = 280 <= index < 400
            event = datetime(2025, 1, 6, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh")) + timedelta(
                days=day, minutes=position
            )
            event = event.astimezone(UTC)
            created = event + timedelta(minutes=5)
            topic = (
                "fees"
                if spike and position < 80
                else (
                    [c for c in codes if c != "fees"][(position - 80) % 7]
                    if spike
                    else codes[position % 8]
                )
            )
            sentiment = (
                (
                    "negative"
                    if position >= 80 or position % 4 != 3
                    else "neutral"
                    if position % 8 == 3
                    else "positive"
                )
                if spike
                else (
                    "negative"
                    if position % 4 < 2
                    else "neutral"
                    if position % 4 == 2
                    else "positive"
                )
            )
            severity = (
                ("high" if position < 72 else "medium" if position < 96 else "low")
                if spike
                else ("high" if position % 4 == 0 else "medium" if position % 4 == 1 else "low")
            )
            ai = dict(topic=topic, sentiment=sentiment, severity=severity)
            state = ["PENDING_REVIEW", "IN_REVIEW", "REVIEWED", "ADJUDICATED"][index % 4]
            human = {**ai, "topic": "fees"} if state == "REVIEWED" else ai.copy()
            if state == "ADJUDICATED" and index % 8 == 3:
                human["severity"] = "unknown"
            version = {"PENDING_REVIEW": 1, "IN_REVIEW": 2, "REVIEWED": 3, "ADJUDICATED": 4}[state]
            text = "SYNTHETIC: Phản ánh dịch vụ giả định dùng kiểm tra bảng thống kê."
            screened = audit_screen(text)
            if screened.counts or screened.ambiguous:
                raise IngestionBlocked("Synthetic fixture privacy check failed")
            feedback = Feedback(
                feedback_id=identity(f"feedback:{index}"),
                source_id="synthetic_demo",
                source_record_ref=f"analytics_demo_{index}",
                text_redacted=screened.text,
                received_at=None if undated else event,
                agency="demo_agency_a" if index % 2 == 0 else "demo_agency_b",
                domain="demo_domain_a" if index % 4 < 2 else "demo_domain_b",
                processing_status="HUMAN_REVIEWED" if version >= 3 else "AWAITING_REVIEW",
                is_synthetic=True,
                provenance_reference="SYNTHETIC_ANALYTICS_FIXTURE_V1",
                review_status=state,
                assigned_actor_id=None if version == 1 else "synthetic_fixture_reviewer",
                adjudicator_id="synthetic_fixture_adjudicator" if version == 4 else None,
                current_topic=human["topic"] if version >= 3 else None,
                current_sentiment=human["sentiment"] if version >= 3 else None,
                current_severity=human["severity"] if version >= 3 else None,
                created_at=created,
                updated_at=created + timedelta(minutes=version),
                version=version,
            )
            session.add(feedback)
            session.flush()
            for task, label in ai.items():
                session.add(
                    Prediction(
                        prediction_id=identity(f"prediction:{index}:{task}"),
                        feedback_id=feedback.feedback_id,
                        model_version_id=models[task].model_version_id,
                        task=task,
                        predicted_label=label,
                        score=None,
                        score_type="MOCK_NO_SCORE",
                        calibrated=False,
                        requires_review=True,
                        review_reasons=["SYNTHETIC_FIXTURE_NOT_NLP"],
                        inference_mode="DEMO_ONLY",
                        provenance={"is_synthetic": True, "independent_human_validation": False},
                        created_at=created + timedelta(seconds=1),
                    )
                )
            actions = [("CREATE", "SYNTHETIC_FIXTURE_CREATED")]
            if version >= 2:
                actions.append(("CLAIM", "CLAIM"))
            if state == "REVIEWED":
                actions.append(("CORRECT", "CORRECTION"))
            if state == "ADJUDICATED":
                actions.extend(
                    [
                        ("ESCALATE", "ESCALATE_CONFLICT"),
                        (
                            "ADJUDICATE",
                            "INSUFFICIENT_EVIDENCE"
                            if human["severity"] == "unknown"
                            else "HUMAN_ADJUDICATION",
                        ),
                    ]
                )
            for number, (action, reason) in enumerate(actions, 1):
                session.add(
                    ReviewEvent(
                        review_event_id=identity(f"event:{index}:{number}"),
                        feedback_id=feedback.feedback_id,
                        operation_id=identity(f"operation:{index}:{number}"),
                        actor_reference="synthetic_fixture_actor",
                        actor_role="ADMIN" if number == 1 else "REVIEWER",
                        action_type=action,
                        reason_code=reason,
                        review_version=number,
                        proposed_labels=human if action in {"CORRECT", "ADJUDICATE"} else None,
                        adjudication_metadata={
                            "is_synthetic": True,
                            "independent_human_validation": False,
                        },
                        occurred_at=created + timedelta(minutes=number),
                    )
                )
    return {
        "status": "SYNTHETIC_ANALYTICS_FIXTURES_CREATED",
        "processing_mode": "DEMO_ONLY",
        "records": 420,
        "dated": 400,
        "missing_event_time": 20,
        "predictions": 1260,
        "simulated_review_events": 1050,
    }
