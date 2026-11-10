"""Bounded, process-local operational metadata; no request content or identifiers."""

from threading import Lock

from fastapi import Depends, HTTPException, Request
from sqlalchemy import func, select, text

from pfa.api.identity import Principal, principal
from pfa.db.models import Feedback
from pfa.db.repository import Repository


# ponytail: process-local counters; use a protected metrics collector for multiple workers.
class Metrics:
    def __init__(self):
        self.lock = Lock()
        self.requests = self.errors = self.failures = 0
        self.total_ms = self.max_ms = 0.0

    def record(self, status, duration_ms):
        with self.lock:
            self.requests += 1
            self.errors += int(status >= 400)
            self.failures += int(status >= 500)
            self.total_ms += duration_ms
            self.max_ms = max(self.max_ms, duration_ms)

    def snapshot(self):
        with self.lock:
            return {
                "requests": self.requests,
                "request_errors": self.errors,
                "processing_failures": self.failures,
                "mean_latency_ms": self.total_ms / self.requests if self.requests else None,
                "max_latency_ms": self.max_ms if self.requests else None,
            }


def operations(request: Request, actor: Principal = Depends(principal)):
    if actor.role != "ADMIN":
        raise HTTPException(403, "ADMIN_REQUIRED")
    database = getattr(request.app.state, "database", None)
    health = "UNAVAILABLE" if request.app.state.persistence_requested else "DISABLED"
    queue = None
    if database is not None:
        try:
            with database.sessions() as session:
                session.execute(text("SELECT 1"))
                repo = Repository(request.app.state.root, session, actor)
                for source_id in actor.source_ids:
                    repo.permit(source_id)
                queue = session.scalar(
                    select(func.count())
                    .select_from(Feedback)
                    .where(
                        Feedback.source_id.in_(actor.source_ids),
                        Feedback.is_synthetic.is_(True),
                        Feedback.review_status.in_(
                            ["PENDING_REVIEW", "IN_REVIEW", "NEEDS_ADJUDICATION"]
                        ),
                    )
                )
            health = "AVAILABLE"
        except HTTPException:
            raise
        except Exception:
            health = "UNAVAILABLE"
    service = request.app.state.service
    return {
        "schema_version": "operations-1",
        "processing_mode": request.app.state.settings.mode,
        "model_loaded": any(task.available for task in service.provider.check().values()),
        "prediction_ready": service.readiness().prediction_ready,
        "database_health": health,
        "review_queue_size_in_authorized_sources": queue,
        "counters": request.app.state.metrics.snapshot(),
        "scope": "PROCESS_LOCAL_SINCE_STARTUP",
    }
