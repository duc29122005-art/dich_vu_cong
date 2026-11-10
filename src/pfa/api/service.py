"""Transient privacy screening and review-only orchestration; no input persistence."""

from threading import BoundedSemaphore
from uuid import uuid4

from fastapi import HTTPException

from pfa.api.providers import PredictionProvider
from pfa.api.schemas import (
    BatchItem,
    BatchResponse,
    ErrorDetail,
    ModelStatus,
    PredictionRequest,
    PredictionResponse,
    Predictions,
    Provenance,
    Readiness,
    TaskPrediction,
)
from pfa.api.settings import ApiSettings
from pfa.data.privacy import audit_screen


class PredictionService:
    def __init__(self, settings: ApiSettings, provider: PredictionProvider):
        self.settings, self.provider = settings, provider
        # ponytail: one local process; use an external admission/rate limiter before public service.
        self.slots = BoundedSemaphore(settings.max_concurrency)

    def status(self):
        states = self.provider.check()
        return ModelStatus(
            processing_mode=self.settings.mode,
            ready=self.settings.authentication_configured
            and all(state.available for state in states.values())
            and len(states) == 3,
            tasks=states,
        )

    def readiness(self):
        status = self.status()
        blockers = sorted({state.blocker for state in status.tasks.values() if state.blocker})
        if not self.settings.authentication_configured:
            blockers.append("AUTHENTICATION_NOT_CONFIGURED")
        return Readiness(
            status="READY" if status.ready else "UNAVAILABLE",
            processing_mode=self.settings.mode,
            prediction_ready=status.ready,
            blockers=blockers,
        )

    def predict(self, items: list[PredictionRequest]) -> BatchResponse:
        if len(items) > self.settings.max_batch_size or any(
            len(item.text) > self.settings.max_text_length for item in items
        ):
            raise HTTPException(422, "CONFIGURED_INPUT_LIMIT_EXCEEDED")
        if not self.slots.acquire(blocking=False):
            raise HTTPException(503, "SERVICE_BUSY", headers={"Retry-After": "1"})
        try:
            if not self.status().ready:
                raise HTTPException(503, "APPROVED_MODEL_UNAVAILABLE")
            results = []
            for item in items:
                identity = item.request_id or uuid4().hex
                try:
                    screening = audit_screen(item.text, self.settings.max_text_length)
                    reasons, warnings = (
                        ["LANGUAGE_AND_SCOPE_NOT_VALIDATED"],
                        ["LANGUAGE_NOT_VALIDATED", "NOT_AN_ADMINISTRATIVE_DECISION"],
                    )
                    if self.settings.mode == "DEMO_ONLY":
                        warnings.append("DEMO_ONLY_MOCK_OUTPUTS_NOT_NLP_INFERENCE")
                    if screening.counts:
                        reasons.append("PRIVACY_SCREENING_REQUIRES_REVIEW")
                        warnings.append("PRIVACY_SCREENING_IS_HEURISTIC")
                    if screening.ambiguous:
                        predictions = {
                            task: TaskPrediction(available=False)
                            for task in ("topic", "sentiment", "severity")
                        }
                        model_status = "INPUT_REVIEW_REQUIRED"
                    else:
                        values = self.provider.predict([screening.text])[0]
                        predictions = {task: value[0] for task, value in values.items()}
                        reasons.extend(reason for value in values.values() for reason in value[1])
                        if any(not value.available for value in predictions.values()):
                            reasons.append("TASK_UNAVAILABLE")
                            model_status = "PARTIAL"
                        else:
                            model_status = self.settings.mode
                        if any(value.calibrated for value in predictions.values()):
                            warnings.append("CALIBRATION_IS_NOT_A_RELIABILITY_GUARANTEE")
                    if self.settings.mode == "DEMO_ONLY":
                        reasons.append("DEMO_ONLY_REQUIRES_HUMAN_REVIEW")
                    response = PredictionResponse(
                        request_id=identity,
                        processing_mode=self.settings.mode,
                        model_status=model_status,
                        predictions=Predictions(**predictions),
                        requires_review=bool(reasons),
                        review_reasons=sorted(set(reasons)),
                        provenance=Provenance(
                            provider="MOCK_FIXTURE"
                            if self.settings.mode == "DEMO_ONLY"
                            else "APPROVED_LOCAL_REGISTRY"
                        ),
                        warnings=warnings,
                    )
                    results.append(BatchItem(request_id=identity, result=response))
                except Exception:
                    results.append(
                        BatchItem(
                            request_id=identity,
                            error=ErrorDetail(
                                code="PREDICTION_UNAVAILABLE",
                                message="Prediction requires human review",
                                request_id=identity,
                            ),
                        )
                    )
            return BatchResponse(processing_mode=self.settings.mode, items=results)
        finally:
            self.slots.release()
