from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EnvSettingGroup:
    id: str
    label: str
    description: str


ENV_SETTING_GROUPS: tuple[EnvSettingGroup, ...] = (
    EnvSettingGroup(
        "application", "Application", "Core service identity, logging, and runtime flags."
    ),
    EnvSettingGroup("database", "Database", "Database connectivity and persistence settings."),
    EnvSettingGroup(
        "security", "Security", "Session, JWT, and secret material used by the backend."
    ),
    EnvSettingGroup("queue", "Queue", "Celery, Redis, and background job timing configuration."),
    EnvSettingGroup("storage", "Storage", "Object storage, upload, and CDN-related settings."),
    EnvSettingGroup("analysis", "Analysis", "Upload validation and analysis-surface constraints."),
    EnvSettingGroup(
        "tribe", "TRIBE", "TRIBE runtime, checkpoint, and feature extraction controls."
    ),
    EnvSettingGroup("llm", "LLM", "Model routing, provider, and evaluation limits."),
    EnvSettingGroup("cloudflare", "Cloudflare", "Cloudflare and R2 connectivity values."),
    EnvSettingGroup("misc", "Misc", "Values that do not fit a more specific control group."),
)

GROUPS_BY_ID = {group.id: group for group in ENV_SETTING_GROUPS}

BOOLEAN_SUFFIXES = (
    "enabled",
    "debug",
    "preload_on_worker_startup",
    "validate_binaries_on_worker_startup",
    "think",
)
INTEGER_SUFFIXES = (
    "minutes",
    "seconds",
    "hours",
    "bytes",
    "characters",
    "tokens",
    "imsize",
)
FLOAT_SUFFIXES = ("frequency_hz", "temperature", "top_p")


def classify_env_setting(key: str) -> str:
    normalized = key.strip().upper()
    if normalized.startswith(("APP_", "API_", "ENVIRONMENT", "DEBUG", "LOG_", "OTEL_", "SERVICE_")):
        return "application"
    if normalized.startswith("DATABASE_"):
        return "database"
    if normalized.startswith(("SESSION_", "JWT_", "MFA_", "INVITE_", "SSO_")):
        return "security"
    if normalized.startswith("CELERY_"):
        return "queue"
    if normalized.startswith(
        ("AWS_", "S3_", "R2_", "CLOUDFLARE_R2_", "LOCAL_STORAGE_", "UPLOAD_PRESIGN_")
    ):
        return "storage"
    if normalized.startswith(("UPLOAD_MAX_", "ALLOWED_UPLOAD_", "ANALYSIS_")):
        return "analysis"
    if normalized.startswith("TRIBE_"):
        return "tribe"
    if normalized.startswith("LLM_"):
        return "llm"
    if normalized.startswith("CLOUDFLARE_"):
        return "cloudflare"
    return "misc"


def infer_value_type(key: str, value: str | None) -> str:
    normalized = key.strip().lower()
    if normalized.endswith(BOOLEAN_SUFFIXES):
        return "boolean"
    if normalized.endswith(FLOAT_SUFFIXES):
        return "float"
    if normalized.endswith(INTEGER_SUFFIXES):
        return "integer"
    stripped_value = (value or "").strip()
    if stripped_value.startswith("[") and stripped_value.endswith("]"):
        return "json"
    return "string"


def is_secret_env_setting(key: str) -> bool:
    normalized = key.strip().upper()
    secret_markers = (
        "SECRET",
        "TOKEN",
        "PASSWORD",
        "API_KEY",
        "ACCESS_KEY",
        "PRIVATE_KEY",
        "DATABASE_URL",
        "JWT_SECRET",
        "SESSION_SECRET",
    )
    return any(marker in normalized for marker in secret_markers)


def build_setting_label(key: str) -> str:
    parts = key.strip().replace("-", "_").split("_")
    return " ".join(part.capitalize() for part in parts if part)
