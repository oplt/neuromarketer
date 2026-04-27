from __future__ import annotations

import asyncio
import io
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from starlette.requests import Request
from starlette.datastructures import Headers, UploadFile

from backend.api import dependencies as auth_deps
from backend.api.dependencies import (
    AuthenticatedClaimsContext,
    AuthenticatedOrganization,
    AuthenticatedProject,
    AuthenticatedRequestContext,
    AuthenticatedUser,
)
from backend.api.router import analysis as analysis_router
from backend.api.router import creative_versions as creative_versions_router
from backend.api.router import predict as predict_router
from backend.api.router import uploads as uploads_router
from backend.core.exceptions import ValidationAppError
from backend.core.security import create_session_token, verify_session_token


def _make_request(
    *, headers: dict[str, str] | None = None, client_host: str = "127.0.0.1"
) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": Headers(headers or {}).raw,
            "client": (client_host, 1234),
        }
    )


def _build_auth_context() -> AuthenticatedRequestContext:
    return AuthenticatedRequestContext(
        claims=SimpleNamespace(),
        user=AuthenticatedUser(
            id=uuid4(),
            email="user@example.com",
            is_active=True,
            deleted_at=None,
        ),
        organization=AuthenticatedOrganization(
            id=uuid4(),
            is_active=True,
            name="Org",
            slug="org",
        ),
        default_project=AuthenticatedProject(
            id=uuid4(),
            name="Default",
        ),
        session=SimpleNamespace(id=uuid4()),
        session_token="token",
    )


def test_require_authenticated_session_skips_default_project_lookup(monkeypatch) -> None:
    auth_deps._auth_cache.clear()
    auth_deps._session_cache.clear()

    now = int(datetime.now(UTC).timestamp())
    session_id = uuid4()
    user_id = uuid4()
    org_id = uuid4()
    token = create_session_token(
        user_id=user_id,
        organization_id=org_id,
        email="user@example.com",
        session_id=session_id,
        expires_at_epoch=now + 600,
    )
    claims = verify_session_token(token)
    claims_ctx = AuthenticatedClaimsContext(claims=claims, session_token=token)

    user_row = SimpleNamespace(
        id=user_id,
        email="user@example.com",
        is_active=True,
        deleted_at=None,
    )
    org_row = SimpleNamespace(
        id=org_id,
        is_active=True,
        name="Org",
        slug="org",
    )
    session_row = SimpleNamespace(id=session_id, updated_at=datetime.now(UTC))

    async def fake_get_user_and_organization(db, *, user_id, organization_id):
        return user_row, org_row

    class _FakeAuthService:
        def __init__(self, db) -> None:
            self.db = db

        async def validate_session_token(self, **kwargs):
            return session_row

    monkeypatch.setattr(auth_deps.crud, "get_user_and_organization", fake_get_user_and_organization)
    monkeypatch.setattr(auth_deps, "AuthApplicationService", _FakeAuthService)

    context = asyncio.run(auth_deps.require_authenticated_session(claims_ctx, object()))
    assert context.user.id == user_id
    assert context.organization.id == org_id
    assert context.session.id == session_id


def test_create_analysis_job_returns_created_response_without_refetch(monkeypatch) -> None:
    response_payload = SimpleNamespace(job=SimpleNamespace(id=uuid4()))

    class _FakeAnalysisService:
        def __init__(self, db) -> None:
            self.db = db

        async def create_analysis_job(self, **kwargs):
            return response_payload

        async def get_analysis_job(self, **kwargs):
            raise AssertionError("should not refetch analysis job")

    dispatched: list = []

    async def fake_dispatch(job_id):
        dispatched.append(job_id)

    monkeypatch.setattr(analysis_router, "AnalysisApplicationService", _FakeAnalysisService)
    monkeypatch.setattr(analysis_router, "dispatch_prediction_job", fake_dispatch)

    auth = _build_auth_context()
    payload = SimpleNamespace(
        asset_id=uuid4(),
        objective=None,
        goal_template=None,
        channel=None,
        audience_segment=None,
    )
    result = asyncio.run(
        analysis_router.create_analysis_job(payload, _make_request(), object(), auth)
    )
    assert result is response_payload
    assert dispatched == [response_payload.job.id]


def test_direct_upload_rejects_oversized_payload_before_processing(monkeypatch) -> None:
    auth = _build_auth_context()
    oversized = str((10 * 1024 * 1024) + 1)
    request = _make_request(headers={"content-length": oversized})

    async def fake_resolve_project_id(*, db, auth, requested_project_id):
        return requested_project_id

    class _FailService:
        def __init__(self, db) -> None:
            raise AssertionError("service should not be created for oversized request")

    monkeypatch.setattr(uploads_router, "_resolve_project_id", fake_resolve_project_id)
    monkeypatch.setattr(uploads_router, "UploadApplicationService", _FailService)

    try:
        asyncio.run(
            uploads_router.direct_upload(
                request=request,
                project_id=str(auth.default_project.id),
                creative_id=None,
                creative_version_id=None,
                artifact_kind="creative_source",
                file=UploadFile(
                    filename="video.mp4", file=io.BytesIO(b"small"), headers=Headers({})
                ),
                db=object(),
                auth=auth,
            )
        )
        raise AssertionError("Expected ValidationAppError for oversized direct upload.")
    except ValidationAppError as exc_info:
        assert exc_info.status_code == 413


def _route_requires_auth(router, route_path: str, method: str) -> bool:
    for route in router.routes:
        if route.path == route_path and method in route.methods:
            return any(
                dependency.call is auth_deps.require_authenticated_context
                for dependency in route.dependant.dependencies
            )
    return False


def test_legacy_endpoints_require_authenticated_context() -> None:
    assert _route_requires_auth(predict_router.router, "/predictions", "POST")
    assert _route_requires_auth(uploads_router.router, "/uploads/direct", "POST")
    assert _route_requires_auth(
        creative_versions_router.router,
        "/creative-versions/from-artifact/{artifact_id}",
        "POST",
    )


def test_sse_fallback_poll_interval_is_relaxed() -> None:
    assert analysis_router.SSE_FALLBACK_POLL_SECONDS >= 3.0
