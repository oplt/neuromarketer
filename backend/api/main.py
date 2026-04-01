from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from asgi_correlation_id import CorrelationIdMiddleware

from backend.api.errors import register_exception_handlers
from backend.api.router.account import router as account_router
from backend.api.router.analysis import router as analysis_router
from backend.api.router.auth import router as auth_router
from backend.api.router.creative_versions import router as creative_versions_router
from backend.api.router.predict import router as predict_router
from backend.api.router.settings import router as settings_router
from backend.api.router.uploads import router as uploads_router
from backend.core.config import settings
from backend.core.logging import configure_logging
from backend.core.metrics import metrics
from backend.core.telemetry import configure_telemetry
from backend.db.session import close_db, database_is_ready, init_db
from backend.middleware.request_context import RequestContextMiddleware
from backend.schemas.schemas import HealthResponse

configure_logging()
configure_telemetry()


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()
    yield
    await close_db()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

app.add_middleware(
    CorrelationIdMiddleware,
    header_name="X-Request-ID",
    update_request_header=True,
)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-Correlation-ID"],
)

register_exception_handlers(app)

app.include_router(auth_router, prefix=settings.api_v1_prefix)
app.include_router(account_router, prefix=settings.api_v1_prefix)
app.include_router(analysis_router, prefix=settings.api_v1_prefix)
app.include_router(predict_router, prefix=settings.api_v1_prefix)
app.include_router(uploads_router, prefix=settings.api_v1_prefix)
app.include_router(creative_versions_router, prefix=settings.api_v1_prefix)
app.include_router(settings_router, prefix=settings.api_v1_prefix)


@app.get("/health/live", response_model=HealthResponse)
async def live_health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        version=settings.app_version,
        dependencies={},
    )


@app.get("/health", response_model=HealthResponse, include_in_schema=False)
async def health_alias() -> HealthResponse:
    return await live_health()


@app.get("/health/ready", response_model=HealthResponse)
async def readiness_health() -> HealthResponse:
    database_status = "ok" if await database_is_ready() else "unavailable"
    overall_status = "ok" if database_status == "ok" else "degraded"
    return HealthResponse(
        status=overall_status,
        service=settings.app_name,
        version=settings.app_version,
        dependencies={"database": database_status},
    )


@app.get("/metrics")
async def metrics_endpoint() -> Response:
    return Response(content=metrics.render_prometheus(), media_type="text/plain; version=0.0.4")
