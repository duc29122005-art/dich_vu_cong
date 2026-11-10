"""Opt-in database endpoints. No history mutation, raw intake or approval endpoint."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from pfa.api.app_factory import get_service
from pfa.api.identity import Principal, principal
from pfa.api.service import PredictionService
from pfa.db import contracts as contract
from pfa.db.repository import Repository


def session(request: Request):
    database = getattr(request.app.state, "database", None)
    if database is None:
        raise HTTPException(503, "PERSISTENCE_UNAVAILABLE")
    with database.sessions() as value:
        yield value


def repository(
    request: Request, actor: Principal = Depends(principal), connection: Session = Depends(session)
):
    return Repository(request.app.state.root, connection, actor)


router = APIRouter(prefix="/api/v1", tags=["synthetic persistence"])


@router.post("/feedback", response_model=contract.FeedbackView, status_code=201)
def create(
    body: contract.CreateFeedback,
    repo: Repository = Depends(repository),
    service: PredictionService = Depends(get_service),
):
    return repo.create(body, service)


@router.get("/feedback", response_model=contract.FeedbackPage)
def feedback(
    repo: Repository = Depends(repository),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0, le=100000),
    status: contract.State | None = None,
    source_id: str | None = None,
    include_text: bool = False,
):
    return repo.page(limit, offset, status, source_id, include_text)


@router.get("/feedback/{identity}", response_model=contract.FeedbackView)
def detail(identity: UUID, repo: Repository = Depends(repository), include_text: bool = False):
    return repo.view(repo.get(identity, include_text), include_text)


@router.get("/reviews/queue", response_model=contract.FeedbackPage)
def queue(
    repo: Repository = Depends(repository),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0, le=100000),
    status: contract.State | None = None,
    source_id: str | None = None,
    include_text: bool = False,
):
    return repo.page(limit, offset, status, source_id, include_text, queue=True)


@router.patch("/reviews/{identity}", response_model=contract.FeedbackView)
def review(
    identity: UUID, body: contract.Review, request: Request, repo: Repository = Depends(repository)
):
    success, result = repo.review(identity, body, request.app.state.settings.credentials)
    if not success:
        raise HTTPException(409, "STALE_DUPLICATE_OR_INVALID_TRANSITION")
    return result


@router.get("/reviews/{identity}/history", response_model=list[contract.AuditView])
def history(
    identity: UUID,
    repo: Repository = Depends(repository),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0, le=100000),
):
    return repo.history(identity, limit, offset)
