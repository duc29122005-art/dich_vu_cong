"""Authenticated, source-scoped aggregate endpoints; never return feedback rows."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from pfa.analytics.schemas import Filters, Report, load_config
from pfa.analytics.service import build
from pfa.db.repository import Repository
from pfa.db.routes import repository

router = APIRouter(prefix="/api/v1/analytics", tags=["synthetic analytics"])


def report(request: Request, filters: Filters, repo: Repository, endpoint: str):
    settings = request.app.state.settings
    if settings.mode != "DEMO_ONLY" or settings.environment == "production":
        raise HTTPException(403, "REAL_ANALYTICS_BLOCKED")
    return build(repo, filters, load_config(repo.root), endpoint)


@router.get("/summary", response_model=Report)
def summary(
    request: Request, filters: Annotated[Filters, Query()], repo: Repository = Depends(repository)
):
    return report(request, filters, repo, "summary")


@router.get("/topics", response_model=Report)
def topics(
    request: Request, filters: Annotated[Filters, Query()], repo: Repository = Depends(repository)
):
    return report(request, filters, repo, "topics")


@router.get("/trends", response_model=Report)
def trends(
    request: Request, filters: Annotated[Filters, Query()], repo: Repository = Depends(repository)
):
    return report(request, filters, repo, "trends")


@router.get("/alerts", response_model=Report)
def alerts(
    request: Request, filters: Annotated[Filters, Query()], repo: Repository = Depends(repository)
):
    return report(request, filters, repo, "alerts")
