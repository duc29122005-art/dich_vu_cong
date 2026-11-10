"""Transactions, source boundaries and atomic compare-and-swap review transitions."""

from fastapi import HTTPException
from sqlalchemy import func, select, update

from pfa.annotation import pilot_store as store
from pfa.api.identity import Principal
from pfa.api.schemas import PredictionRequest
from pfa.data.corpus_smoke import fixture
from pfa.data.permissions import require_access
from pfa.data.privacy import audit_screen
from pfa.data.registry import load_registry
from pfa.db import contracts as contract
from pfa.db.models import Feedback, ModelVersion, Prediction, ReviewEvent, SourceRegistry, now


class Repository:
    def __init__(self, root, session, actor: Principal):
        self.root, self.session, self.actor = root, session, actor
        self.registry = load_registry(root / "configs/dataset_sources.yaml")

    def permit(self, source_id, *, text=False):
        if source_id not in self.actor.source_ids or (text and not self.actor.can_view_text):
            raise HTTPException(403, "SOURCE_OR_TEXT_ACCESS_DENIED")
        try:
            source = self.registry.source(source_id)
        except ValueError:
            raise HTTPException(403, "SOURCE_PERMISSION_REQUIRED") from None
        if source_id != "synthetic_demo" or source.dataset_role != "SYNTHETIC":
            # Existing rights are necessary, never sufficient to bypass STEP04/privacy handoff.
            try:
                require_access(self.root, self.registry, source_id, "internal_analysis")
            except (ValueError, OSError):
                raise HTTPException(403, "SOURCE_PERMISSION_REQUIRED") from None
            raise HTTPException(403, "VERIFIED_STEP04_INTAKE_REQUIRED")
        return source

    def get(self, identity, include_text=False):
        row = self.session.get(Feedback, identity)
        if row is None:
            raise HTTPException(404, "FEEDBACK_NOT_FOUND")
        source = self.permit(row.source_id, text=include_text)
        cached = self.session.get(SourceRegistry, row.source_id)
        if (
            not row.is_synthetic
            or cached is None
            or cached.registry_sha256 != store.digest(source.model_dump())
        ):
            raise HTTPException(403, "SOURCE_PROVENANCE_CHANGED")
        return row

    def predictions(self, row):
        records = self.session.scalars(
            select(Prediction)
            .where(Prediction.feedback_id == row.feedback_id)
            .order_by(Prediction.created_at, Prediction.prediction_id)
        ).all()
        result = {}
        for record in records:
            model = self.session.get(ModelVersion, record.model_version_id)
            result[record.task] = contract.StoredPrediction(
                prediction_id=str(record.prediction_id),
                inference_mode=record.inference_mode,
                requires_review=record.requires_review,
                review_reasons=record.review_reasons,
                provenance=record.provenance,
                available=record.predicted_label is not None,
                label=record.predicted_label,
                score=record.score,
                score_type=record.score_type,
                calibrated=record.calibrated,
                model_version=model.registry_reference,
            )
        return result

    def view(self, row, include_text=False):
        if include_text:
            self.permit(row.source_id, text=True)
        labels = None
        if row.current_topic is not None:
            labels = contract.Labels(
                topic=row.current_topic,
                sentiment=row.current_sentiment,
                severity=row.current_severity,
            )
        return contract.FeedbackView(
            feedback_id=str(row.feedback_id),
            source_id=row.source_id,
            source_record_ref=row.source_record_ref,
            text_redacted=row.text_redacted if include_text else None,
            received_at=row.received_at,
            domain=row.domain,
            agency=row.agency,
            channel=row.channel,
            processing_status=row.processing_status,
            is_synthetic=row.is_synthetic,
            provenance_reference=row.provenance_reference,
            review_status=row.review_status,
            assigned_actor_id=row.assigned_actor_id,
            current_labels=labels,
            version=row.version,
            created_at=row.created_at,
            updated_at=row.updated_at,
            predictions=self.predictions(row),
        )

    def add_event(
        self,
        row,
        operation,
        action,
        reason,
        version,
        *,
        previous=None,
        proposed=None,
        prediction_id=None,
        metadata=None,
        attempted=None,
    ):
        self.session.add(
            ReviewEvent(
                feedback_id=row.feedback_id,
                operation_id=operation,
                actor_reference=self.actor.actor_id,
                actor_role=self.actor.role,
                action_type=action,
                reason_code=reason,
                review_version=version,
                previous_labels=previous,
                proposed_labels=proposed,
                prediction_id=prediction_id,
                adjudication_metadata=metadata,
                attempted_version=attempted,
            )
        )

    def create(self, body: contract.CreateFeedback, prediction_service):
        if self.actor.role != "ADMIN":
            raise HTTPException(403, "ADMIN_REQUIRED")
        source = self.permit(body.source_id)
        if not body.is_synthetic:
            raise HTTPException(403, "REAL_PERSISTENCE_BLOCKED")
        rows, _ = fixture(120)
        item = rows[body.fixture_id]
        screening = audit_screen(item.content)
        if screening.counts or screening.ambiguous:
            raise HTTPException(422, "FIXTURE_PRIVACY_REVIEW_REQUIRED")
        output = prediction_service.predict([PredictionRequest(text=screening.text)]).items[0]
        if output.result is None or output.result.processing_mode != "DEMO_ONLY":
            raise HTTPException(503, "DEMO_PREDICTION_REQUIRED")
        response = output.result
        with self.session.begin():
            if self.session.scalar(
                select(ReviewEvent).where(ReviewEvent.operation_id == body.operation_id)
            ):
                raise HTTPException(409, "DUPLICATE_OPERATION")
            source_row = self.session.get(SourceRegistry, source.source_id)
            if source_row is None:
                self.session.add(
                    SourceRegistry(
                        source_id=source.source_id,
                        registry_sha256=store.digest(source.model_dump()),
                        provenance_reference="SYNTHETIC_SOFTWARE_FIXTURE_V1",
                        source_kind="SYNTHETIC",
                    )
                )
                self.session.flush()
            elif source_row.registry_sha256 != store.digest(source.model_dump()):
                raise HTTPException(403, "SOURCE_PROVENANCE_CHANGED")
            row = Feedback(
                source_id=source.source_id,
                source_record_ref=f"synthetic_fixture_{body.fixture_id}",
                text_redacted=screening.text,
                received_at=None,
                domain=getattr(item, "domain", None),
                agency=getattr(item, "agency", None),
                channel=None,
                is_synthetic=True,
                provenance_reference="SYNTHETIC_SOFTWARE_FIXTURE_V1",
            )
            self.session.add(row)
            self.session.flush()
            for task in ("topic", "sentiment", "severity"):
                prediction = getattr(response.predictions, task)
                if (
                    not prediction.available
                    or prediction.score is not None
                    or prediction.calibrated
                ):
                    raise HTTPException(503, "INVALID_DEMO_PREDICTION")
                descriptor = {
                    "task": task,
                    "reference": prediction.model_version,
                    "mode": "DEMO_ONLY",
                    **response.provenance.model_dump(),
                }
                model = self.session.scalar(
                    select(ModelVersion).where(
                        ModelVersion.registry_reference == prediction.model_version,
                        ModelVersion.task == task,
                        ModelVersion.inference_mode == "DEMO_ONLY",
                    )
                )
                if model is None:
                    model = ModelVersion(
                        registry_reference=prediction.model_version,
                        task=task,
                        inference_mode="DEMO_ONLY",
                        family="mock",
                        descriptor_sha256=store.digest(descriptor),
                        taxonomy_version=response.taxonomy_version,
                        taxonomy_checksum=response.provenance.taxonomy_checksum,
                        preprocessing_version=response.provenance.preprocessing_version,
                    )
                    self.session.add(model)
                    self.session.flush()
                elif model.descriptor_sha256 != store.digest(descriptor):
                    raise HTTPException(409, "MODEL_REFERENCE_CHANGED")
                self.session.add(
                    Prediction(
                        feedback_id=row.feedback_id,
                        model_version_id=model.model_version_id,
                        task=task,
                        predicted_label=prediction.label,
                        score=None,
                        score_type=prediction.score_type,
                        calibrated=False,
                        requires_review=True,
                        review_reasons=response.review_reasons,
                        inference_mode="DEMO_ONLY",
                        provenance={**response.provenance.model_dump(), "input_persisted": True},
                    )
                )
            self.add_event(row, body.operation_id, "CREATE", "SYNTHETIC_FIXTURE_CREATED", 1)
        return self.view(row)

    def page(self, limit, offset, status=None, source_id=None, include_text=False, queue=False):
        if queue and self.actor.role not in {"ADMIN", "REVIEWER"}:
            raise HTTPException(403, "REVIEW_ROLE_REQUIRED")
        sources = [source_id] if source_id else self.actor.source_ids
        for source in sources:
            self.permit(source, text=include_text)
        query = select(Feedback).where(Feedback.source_id.in_(sources))
        if status:
            query = query.where(Feedback.review_status == status)
        elif queue:
            query = query.where(
                Feedback.review_status.in_(["PENDING_REVIEW", "IN_REVIEW", "NEEDS_ADJUDICATION"])
            )
        total = self.session.scalar(select(func.count()).select_from(query.subquery()))
        records = self.session.scalars(
            query.order_by(Feedback.created_at, Feedback.feedback_id).limit(limit).offset(offset)
        ).all()
        for row in records:
            self.get(row.feedback_id)
        return contract.FeedbackPage(
            items=[self.view(r, include_text) for r in records],
            total=total,
            limit=limit,
            offset=offset,
        )

    def review(self, identity, body: contract.Review, principals):
        if self.actor.role not in {"ADMIN", "REVIEWER"} or not self.actor.can_view_text:
            raise HTTPException(403, "REVIEW_AUTHORIZATION_REQUIRED")
        with self.session.begin():
            row = self.get(identity, True)
            if self.session.scalar(
                select(ReviewEvent).where(ReviewEvent.operation_id == body.operation_id)
            ):
                return False, self.view(row)
            if self.actor.role == "ADMIN" and body.action != "ASSIGN":
                raise HTTPException(403, "ADMIN_ASSIGNMENT_ONLY")
            if body.action == "ASSIGN" and self.actor.role != "ADMIN":
                raise HTTPException(403, "ADMIN_REQUIRED")
            values, labels = {}, body.labels.model_dump() if body.labels else None
            target = {
                "CLAIM": "IN_REVIEW",
                "ASSIGN": "IN_REVIEW",
                "CORRECT": "REVIEWED",
                "CONFIRM": "REVIEWED",
                "ESCALATE": "NEEDS_ADJUDICATION",
                "ADJUDICATE": "ADJUDICATED",
            }[body.action]
            allowed = row.review_status == (
                "PENDING_REVIEW"
                if body.action in {"CLAIM", "ASSIGN"}
                else "NEEDS_ADJUDICATION"
                if body.action == "ADJUDICATE"
                else "IN_REVIEW"
            )
            if body.action == "ADJUDICATE" and not self.actor.can_adjudicate:
                raise HTTPException(403, "DESIGNATED_ADJUDICATOR_REQUIRED")
            if (
                body.action in {"CONFIRM", "CORRECT", "ESCALATE"}
                and row.assigned_actor_id != self.actor.actor_id
            ):
                raise HTTPException(403, "ASSIGNED_REVIEWER_REQUIRED")
            if body.action in {"CLAIM", "ASSIGN"}:
                assignee = self.actor.actor_id
                if body.action == "ASSIGN":
                    candidate = next(
                        (p for p in principals if p.actor_id == body.assignee_id), None
                    )
                    if (
                        candidate is None
                        or candidate.role != "REVIEWER"
                        or not candidate.can_view_text
                        or row.source_id not in candidate.source_ids
                    ):
                        raise HTTPException(403, "AUTHORIZED_ASSIGNEE_REQUIRED")
                    assignee = candidate.actor_id
                values["assigned_actor_id"] = assignee
            if body.prediction_id and not self.session.scalar(
                select(Prediction.prediction_id).where(
                    Prediction.prediction_id == body.prediction_id,
                    Prediction.feedback_id == identity,
                )
            ):
                raise HTTPException(422, "PREDICTION_MEMBERSHIP_MISMATCH")
            if row.version != body.expected_version or not allowed:
                self.add_event(
                    row,
                    body.operation_id,
                    "CONFLICT",
                    "STALE_VERSION"
                    if row.version != body.expected_version
                    else "INVALID_TRANSITION",
                    None,
                    attempted=body.expected_version,
                )
                return False, self.view(row)
            previous = {
                "topic": row.current_topic,
                "sentiment": row.current_sentiment,
                "severity": row.current_severity,
            }
            if body.action == "CONFIRM":
                labels = {task: value.label for task, value in self.predictions(row).items()}
                if set(labels) != {"topic", "sentiment", "severity"} or any(
                    value is None for value in labels.values()
                ):
                    raise HTTPException(409, "COMPLETE_PREDICTIONS_REQUIRED")
            if body.action in {"CONFIRM", "CORRECT", "ADJUDICATE"}:
                values.update(
                    {
                        "current_topic": labels["topic"],
                        "current_sentiment": labels["sentiment"],
                        "current_severity": labels["severity"],
                        "processing_status": "HUMAN_REVIEWED",
                    }
                )
            if body.action == "ADJUDICATE":
                values["adjudicator_id"] = self.actor.actor_id
            values.update(review_status=target, version=body.expected_version + 1, updated_at=now())
            changed = self.session.execute(
                update(Feedback)
                .where(
                    Feedback.feedback_id == identity,
                    Feedback.version == body.expected_version,
                    Feedback.review_status == row.review_status,
                )
                .values(**values)
            ).rowcount
            if changed != 1:
                self.add_event(
                    row,
                    body.operation_id,
                    "CONFLICT",
                    "STALE_VERSION",
                    None,
                    attempted=body.expected_version,
                )
                return False, self.view(row)
            metadata = {"is_synthetic": True, "independent_human_validation": False}
            if body.action == "ASSIGN":
                metadata["assigned_actor_id"] = values["assigned_actor_id"]
            self.add_event(
                row,
                body.operation_id,
                body.action,
                body.reason_code,
                body.expected_version + 1,
                previous=previous,
                proposed=labels,
                prediction_id=body.prediction_id,
                metadata=metadata if body.action in {"ASSIGN", "ADJUDICATE"} else None,
            )
            self.session.flush()
            self.session.refresh(row)
        return True, self.view(row)

    def history(self, identity, limit, offset):
        if self.actor.role != "ADMIN":
            raise HTTPException(403, "ADMIN_AUDIT_ACCESS_REQUIRED")
        self.get(identity)
        events = self.session.scalars(
            select(ReviewEvent)
            .where(ReviewEvent.feedback_id == identity)
            .order_by(
                ReviewEvent.occurred_at,
                ReviewEvent.review_version.asc().nulls_last(),
                ReviewEvent.review_event_id,
            )
            .limit(limit)
            .offset(offset)
        ).all()
        return [
            contract.AuditView(
                review_event_id=str(e.review_event_id),
                feedback_id=str(e.feedback_id),
                prediction_id=str(e.prediction_id) if e.prediction_id else None,
                actor_reference=e.actor_reference,
                actor_role=e.actor_role,
                action_type=e.action_type,
                reason_code=e.reason_code,
                review_version=e.review_version,
                attempted_version=e.attempted_version,
                previous_labels=e.previous_labels,
                proposed_labels=e.proposed_labels,
                adjudication_metadata=e.adjudication_metadata,
                occurred_at=e.occurred_at,
            )
            for e in events
        ]
