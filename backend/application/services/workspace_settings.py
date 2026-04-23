from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import ENV_FILE
from backend.core.exceptions import ValidationAppError
from backend.db.models import Setting
from backend.schemas.settings import (
    SettingFieldRead,
    SettingGroupRead,
    SettingsResponse,
    SettingsUpdateRequest,
    SettingsUpdateResponse,
)
from backend.services.env_settings_registry import (
    ENV_SETTING_GROUPS,
    build_setting_label,
    classify_env_setting,
    infer_value_type,
    is_secret_env_setting,
)


@dataclass(slots=True)
class ParsedEnvEntry:
    key: str
    value: str | None


class WorkspaceSettingsService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.env_file_path = Path(ENV_FILE)

    async def list_settings(self, *, organization_id: UUID) -> SettingsResponse:
        persisted_rows = await self._load_persisted_settings(organization_id=organization_id)
        persisted_by_key = {row.key: row for row in persisted_rows}
        env_entries = self._parse_env_entries(self.env_file_path)

        fields: list[SettingFieldRead] = []
        seen_keys: set[str] = set()

        for entry in env_entries:
            persisted = persisted_by_key.get(entry.key)
            fields.append(
                SettingFieldRead(
                    key=entry.key,
                    env_name=entry.key,
                    group_id=classify_env_setting(entry.key),
                    label=build_setting_label(entry.key),
                    value=entry.value,
                    value_type=infer_value_type(entry.key, entry.value),
                    description=persisted.description if persisted is not None else None,
                    is_secret=is_secret_env_setting(entry.key),
                    source="env_file",
                    updated_at=persisted.updated_at if persisted is not None else None,
                )
            )
            seen_keys.add(entry.key)

        for row in persisted_rows:
            if row.key in seen_keys:
                continue
            fields.append(
                SettingFieldRead(
                    key=row.key,
                    env_name=row.env_name,
                    group_id=row.group_id,
                    label=row.label,
                    value=row.value,
                    value_type=row.value_type,
                    description=row.description,
                    is_secret=row.is_secret,
                    source=row.source,
                    updated_at=row.updated_at,
                )
            )

        fields.sort(key=lambda item: (item.group_id, item.label.lower()))
        groups = [
            SettingGroupRead(id=group.id, label=group.label, description=group.description)
            for group in ENV_SETTING_GROUPS
            if any(field.group_id == group.id for field in fields)
        ]
        return SettingsResponse(
            env_file_path=str(self.env_file_path),
            groups=groups,
            fields=fields,
        )

    async def update_settings(
        self,
        *,
        organization_id: UUID,
        user_id: UUID,
        payload: SettingsUpdateRequest,
    ) -> SettingsUpdateResponse:
        env_entries = self._parse_env_entries(self.env_file_path)
        env_keys = {entry.key for entry in env_entries}
        requested_updates = {
            entry.key.strip(): entry.value for entry in payload.entries if entry.key.strip()
        }
        unsupported_keys = sorted(key for key in requested_updates if key not in env_keys)
        if unsupported_keys:
            raise ValidationAppError(
                f"Unsupported settings keys: {', '.join(unsupported_keys[:5])}."
            )

        self._write_env_entries(self.env_file_path, requested_updates=requested_updates)

        persisted_rows = await self._load_persisted_settings(organization_id=organization_id)
        persisted_by_key = {row.key: row for row in persisted_rows}
        now = datetime.now(UTC)

        for key, value in requested_updates.items():
            row = persisted_by_key.get(key)
            if row is None:
                row = Setting(
                    organization_id=organization_id,
                    updated_by_user_id=user_id,
                    key=key,
                    env_name=key,
                    group_id=classify_env_setting(key),
                    label=build_setting_label(key),
                    value=value,
                    value_type=infer_value_type(key, value),
                    description=None,
                    is_secret=is_secret_env_setting(key),
                    source="env_file",
                )
                self.session.add(row)
            else:
                row.updated_by_user_id = user_id
                row.group_id = classify_env_setting(key)
                row.label = build_setting_label(key)
                row.value = value
                row.value_type = infer_value_type(key, value)
                row.is_secret = is_secret_env_setting(key)
                row.source = "env_file"
                row.updated_at = now

        await self.session.commit()
        return SettingsUpdateResponse(
            updated_count=len(requested_updates),
            saved_at=now,
        )

    async def _load_persisted_settings(self, *, organization_id: UUID) -> list[Setting]:
        result = await self.session.execute(
            select(Setting)
            .where(Setting.organization_id == organization_id)
            .order_by(Setting.group_id.asc(), Setting.label.asc())
        )
        return list(result.scalars().all())

    def _parse_env_entries(self, env_file_path: Path) -> list[ParsedEnvEntry]:
        if not env_file_path.exists():
            return []
        entries: list[ParsedEnvEntry] = []
        for raw_line in env_file_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in raw_line:
                continue
            key, raw_value = raw_line.split("=", 1)
            entries.append(ParsedEnvEntry(key=key.strip(), value=raw_value))
        return entries

    def _write_env_entries(
        self, env_file_path: Path, *, requested_updates: dict[str, str | None]
    ) -> None:
        env_file_path.parent.mkdir(parents=True, exist_ok=True)
        existing_lines = (
            env_file_path.read_text(encoding="utf-8").splitlines() if env_file_path.exists() else []
        )
        remaining_updates = dict(requested_updates)
        next_lines: list[str] = []

        for raw_line in existing_lines:
            stripped = raw_line.strip()
            if not stripped or stripped.startswith("#") or "=" not in raw_line:
                next_lines.append(raw_line)
                continue

            key, _ = raw_line.split("=", 1)
            normalized_key = key.strip()
            if normalized_key in remaining_updates:
                next_lines.append(
                    self._format_env_line(normalized_key, remaining_updates.pop(normalized_key))
                )
            else:
                next_lines.append(raw_line)

        if remaining_updates:
            if next_lines and next_lines[-1].strip():
                next_lines.append("")
            for key, value in remaining_updates.items():
                next_lines.append(self._format_env_line(key, value))

        env_file_path.write_text("\n".join(next_lines).rstrip() + "\n", encoding="utf-8")

    def _format_env_line(self, key: str, value: str | None) -> str:
        return f"{key}={'' if value is None else value}"
