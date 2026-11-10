"""Local FastAPI factory with cached models and explicitly enabled synthetic persistence."""

from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from pfa.annotation.taxonomy import Taxonomy, load_taxonomy
from pfa.api import schemas
from pfa.api.providers import DemoProvider, PredictionProvider, RegistryProvider
from pfa.api.security import Boundary, error, require_key
from pfa.api.service import PredictionService
from pfa.api.settings import ApiSettings
from pfa.core.config import Settings
from pfa.integration.observability import Metrics, operations


def get_service(request: Request) -> PredictionService:
    return request.app.state.service


def create_app(
    settings: ApiSettings | None = None,
    *,
    root: Path | None = None,
    provider_factory: Callable[[], PredictionProvider] | None = None,
    database_factory: Callable | None = None,
) -> FastAPI:
    core = Settings()
    settings = settings or ApiSettings(environment=core.environment)
    root = root or core.project_root
    if (
        provider_factory is not None or database_factory is not None
    ) and settings.environment != "test":
        raise ValueError("Provider injection is restricted to isolated tests")
    from pfa.db.session import DbSettings

    db_settings = DbSettings()

    @asynccontextmanager
    async def lifespan(app):
        taxonomy = load_taxonomy(root)
        provider = (
            provider_factory()
            if provider_factory
            else DemoProvider()
            if settings.mode == "DEMO_ONLY"
            else RegistryProvider(root, settings)
        )
        app.state.service = PredictionService(settings, provider)
        app.state.taxonomy = taxonomy
        app.state.database = None
        database = None
        try:
            # Missing credentials never cause model loading or authorize predictions.
            if settings.authentication_configured:
                provider.load()
            elif isinstance(provider, DemoProvider):
                provider.loaded = False
            if db_settings.mode != "DISABLED" or database_factory is not None:
                try:
                    from pfa.db.session import Database

                    if settings.mode != "DEMO_ONLY" or settings.environment == "production":
                        raise ValueError("Synthetic persistence requires local demo mode")
                    database = (
                        database_factory() if database_factory else Database(root, db_settings)
                    )
                    database.validate()
                    app.state.database = database
                except Exception:
                    if database is not None:
                        database.close()
                    database = None
            yield
        finally:
            if database is not None:
                database.close()
            provider.close()

    app = FastAPI(
        title="Public Service Feedback AI",
        version=schemas.API_VERSION,
        description="Local review support. DEMO_ONLY outputs are fixtures, not NLP conclusions.",
        lifespan=lifespan,
        debug=False,
        docs_url=None if settings.environment == "production" else "/docs",
        redoc_url=None,
        openapi_url=None if settings.environment == "production" else "/openapi.json",
    )
    app.state.settings = settings
    app.state.root = root
    app.state.persistence_requested = db_settings.mode != "DISABLED" or database_factory is not None
    app.state.metrics = Metrics()
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_methods=["GET", "POST", "PATCH"],
            allow_headers=["X-API-Key", "Content-Type"],
            allow_credentials=False,
            max_age=600,
        )
    app.add_middleware(Boundary, settings=settings, metrics=app.state.metrics)
    if settings.observability_enabled:
        app.add_api_route("/api/v1/operations/status", operations, methods=["GET"])

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exception):
        return error(422, "INVALID_REQUEST", request.state.trace_id)

    @app.exception_handler(ResponseValidationError)
    async def response_error(request, exception):
        return error(500, "INVALID_MODEL_RESPONSE", request.state.trace_id)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request, exception):
        codes = {
            401: "UNAUTHORIZED",
            403: "FORBIDDEN",
            404: "NOT_FOUND",
            405: "METHOD_NOT_ALLOWED",
            409: "CONFLICT",
            422: "INVALID_REQUEST",
            503: "SERVICE_UNAVAILABLE",
        }
        return error(
            exception.status_code,
            codes.get(exception.status_code, "REQUEST_FAILED"),
            request.state.trace_id,
            exception.headers,
        )

    @app.get("/health/live", response_model=schemas.Liveness)
    def live():
        return schemas.Liveness()

    @app.get("/health/ready", response_model=schemas.Readiness)
    def ready(response: Response, service: PredictionService = Depends(get_service)):
        result = service.readiness()
        if not result.prediction_ready:
            response.status_code = 503
        return result

    protected = [Depends(require_key)]
    errors = {
        code: {"model": schemas.ErrorResponse} for code in (400, 401, 403, 413, 415, 422, 503, 500)
    }

    @app.get(
        "/api/v1/models/status",
        response_model=schemas.ModelStatus,
        dependencies=protected,
        responses=errors,
    )
    def models(service: PredictionService = Depends(get_service)):
        return service.status()

    @app.post(
        "/api/v1/predict",
        response_model=schemas.PredictionResponse,
        dependencies=protected,
        responses=errors,
    )
    def predict(body: schemas.PredictionRequest, service: PredictionService = Depends(get_service)):
        result = service.predict([body]).items[0]
        if result.error:
            raise HTTPException(503, "PREDICTION_UNAVAILABLE")
        return result.result

    @app.post(
        "/api/v1/predict/batch",
        response_model=schemas.BatchResponse,
        dependencies=protected,
        responses=errors,
    )
    def batch(body: schemas.BatchRequest, service: PredictionService = Depends(get_service)):
        return service.predict(body.items)

    @app.get("/api/v1/taxonomy", response_model=Taxonomy, dependencies=protected, responses=errors)
    def taxonomy(request: Request):
        return request.app.state.taxonomy

    @app.get(
        "/api/v1/version",
        response_model=schemas.VersionResponse,
        dependencies=protected,
        responses=errors,
    )
    def version():
        return schemas.VersionResponse(processing_mode=settings.mode)

    if db_settings.mode != "DISABLED" or database_factory is not None:
        from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError

        from pfa.analytics.routes import router as analytics_router
        from pfa.db.routes import router

        app.include_router(router)
        app.include_router(analytics_router)

        @app.exception_handler(SQLAlchemyError)
        async def database_error(request, exception):
            # hide_parameters plus this boundary prevent connection strings/SQL input escaping.
            original = getattr(exception, "orig", None)
            request_scope_conflict = isinstance(exception, IntegrityError) or (
                isinstance(exception, OperationalError)
                and (
                    getattr(original, "sqlite_errorcode", 0) & 255 in {5, 6}
                    or getattr(original, "sqlstate", None) in {"40001", "40P01"}
                )
            )
            return error(
                409 if request_scope_conflict else 503,
                "DATABASE_CONFLICT" if request_scope_conflict else "DATABASE_UNAVAILABLE",
                request.state.trace_id,
            )

    return app
