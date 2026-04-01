from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import AuthenticatedRequestContext, require_authenticated_context
from backend.application.services.workspace_settings import WorkspaceSettingsService
from backend.db.session import get_db
from backend.schemas.settings import SettingsResponse, SettingsUpdateRequest, SettingsUpdateResponse

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/env", response_model=SettingsResponse)
async def get_workspace_env_settings(
    db: AsyncSession = Depends(get_db),
    auth: AuthenticatedRequestContext = Depends(require_authenticated_context),
) -> SettingsResponse:
    return await WorkspaceSettingsService(db).list_settings(
        organization_id=auth.organization.id,
    )


@router.put("/env", response_model=SettingsUpdateResponse)
async def update_workspace_env_settings(
    payload: SettingsUpdateRequest,
    db: AsyncSession = Depends(get_db),
    auth: AuthenticatedRequestContext = Depends(require_authenticated_context),
) -> SettingsUpdateResponse:
    return await WorkspaceSettingsService(db).update_settings(
        organization_id=auth.organization.id,
        user_id=auth.user.id,
        payload=payload,
    )
