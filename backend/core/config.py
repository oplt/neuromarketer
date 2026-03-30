from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        env_ignore_empty=True,
    )

    app_name: str = "NeuroMarketer API"
    app_env: Literal["local", "dev", "staging", "prod", "test"] = "dev"
    app_version: str = "0.3.0"
    api_v1_prefix: str = "/api/v1"
    debug: bool = False
    log_level: str = "INFO"

    database_url: str = Field(validation_alias="DATABASE_URL")
    database_echo: bool = False
    database_auto_create: bool = False
    database_pool_pre_ping: bool = True

    cors_allow_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://localhost:5173"]
    )
    cors_allow_credentials: bool = True

    session_secret: str = Field(
        default="dev-session-secret",
        validation_alias=AliasChoices("SESSION_SECRET", "JWT_SECRET"),
    )
    session_ttl_minutes: int = Field(
        default=60 * 24 * 7,
        validation_alias=AliasChoices("SESSION_TTL_MINUTES", "JWT_EXP_MINUTES"),
    )

    aws_region: str = Field(default="eu-west-1", validation_alias="AWS_REGION")
    s3_bucket_name: str = Field(default="neuromarketing-dev", validation_alias="S3_BUCKET_NAME")
    s3_endpoint_url: str | None = Field(default=None, validation_alias="S3_ENDPOINT_URL")
    s3_public_base_url: str | None = Field(default=None, validation_alias="S3_PUBLIC_BASE_URL")
    aws_access_key_id: str | None = Field(default=None, validation_alias="AWS_ACCESS_KEY_ID")
    aws_secret_access_key: str | None = Field(default=None, validation_alias="AWS_SECRET_ACCESS_KEY")
    aws_session_token: str | None = Field(default=None, validation_alias="AWS_SESSION_TOKEN")
    local_storage_root: str = Field(default="./data", validation_alias="LOCAL_STORAGE_ROOT")
    r2_account_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("CLOUDFLARE_R2_ACCOUNT_ID", "R2_ACCOUNT_ID"),
    )
    r2_access_key_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("CLOUDFLARE_R2_ACCESS_KEY_ID", "R2_ACCESS_KEY_ID"),
    )
    r2_secret_access_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("CLOUDFLARE_R2_SECRET_ACCESS_KEY", "R2_SECRET_ACCESS_KEY"),
    )
    r2_bucket_name: str | None = Field(
        default=None,
        validation_alias=AliasChoices("CLOUDFLARE_R2_BUCKET", "R2_BUCKET_NAME"),
    )
    r2_public_base_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("CLOUDFLARE_R2_PUBLIC_BASE_URL", "R2_PUBLIC_BASE_URL"),
    )
    r2_endpoint_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("CLOUDFLARE_R2_ENDPOINT_URL", "R2_ENDPOINT_URL"),
    )
    upload_presign_expires_seconds: int = Field(default=900, validation_alias="UPLOAD_PRESIGN_EXPIRES_SECONDS")

    upload_max_size_bytes: int = Field(default=250 * 1024 * 1024, validation_alias="UPLOAD_MAX_SIZE_BYTES")
    allowed_upload_mime_prefixes: list[str] = Field(
        default_factory=lambda: ["image/", "video/", "audio/", "text/", "application/json"],
        validation_alias="ALLOWED_UPLOAD_MIME_PREFIXES",
    )
    analysis_allowed_video_mime_types: list[str] = Field(
        default_factory=lambda: ["video/mp4", "video/quicktime", "video/webm"],
        validation_alias="ANALYSIS_ALLOWED_VIDEO_MIME_TYPES",
    )
    analysis_allowed_audio_mime_types: list[str] = Field(
        default_factory=lambda: ["audio/mpeg", "audio/mp4", "audio/wav", "audio/x-wav", "audio/webm"],
        validation_alias="ANALYSIS_ALLOWED_AUDIO_MIME_TYPES",
    )
    analysis_allowed_text_mime_types: list[str] = Field(
        default_factory=lambda: ["text/plain"],
        validation_alias="ANALYSIS_ALLOWED_TEXT_MIME_TYPES",
    )
    analysis_max_text_characters: int = Field(default=50_000, validation_alias="ANALYSIS_MAX_TEXT_CHARACTERS")

    celery_broker_url: str = Field(default="redis://localhost:6379/0", validation_alias="CELERY_BROKER_URL")
    celery_result_backend: str = Field(
        default="redis://localhost:6379/1",
        validation_alias="CELERY_RESULT_BACKEND",
    )
    celery_soft_time_limit_seconds: int = Field(default=900, validation_alias="CELERY_SOFT_TIME_LIMIT_SECONDS")
    celery_time_limit_seconds: int = Field(default=1200, validation_alias="CELERY_TIME_LIMIT_SECONDS")
    celery_job_stale_after_seconds: int = Field(default=1800, validation_alias="CELERY_JOB_STALE_AFTER_SECONDS")

    tribe_model_repo_id: str = Field(default="facebook/tribev2", validation_alias="TRIBE_MODEL_REPO_ID")
    tribe_checkpoint_name: str = Field(default="best.ckpt", validation_alias="TRIBE_CHECKPOINT_NAME")
    tribe_cache_folder: str = Field(default="./cache/tribev2", validation_alias="TRIBE_CACHE_FOLDER")
    tribe_device: str = Field(default="auto", validation_alias="TRIBE_DEVICE")
    tribe_feature_cluster: str | None = Field(default=None, validation_alias="TRIBE_FEATURE_CLUSTER")
    tribe_hf_token: str | None = Field(
        default=None,
        validation_alias=AliasChoices("TRIBE_HF_TOKEN", "HF_TOKEN", "HUGGINGFACE_HUB_TOKEN"),
    )
    tribe_preload_on_worker_startup: bool = Field(default=True, validation_alias="TRIBE_PRELOAD_ON_WORKER_STARTUP")
    tribe_validate_binaries_on_worker_startup: bool = Field(
        default=True,
        validation_alias="TRIBE_VALIDATE_BINARIES_ON_WORKER_STARTUP",
    )
    tribe_enable_roi_summary: bool = Field(default=False, validation_alias="TRIBE_ENABLE_ROI_SUMMARY")

    @field_validator("cors_allow_origins", mode="before")
    @classmethod
    def _parse_cors_allow_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return cls._parse_listish_value(value)
        return value

    @field_validator("allowed_upload_mime_prefixes", mode="before")
    @classmethod
    def _parse_allowed_upload_mime_prefixes(cls, value: object) -> object:
        if isinstance(value, str):
            return cls._parse_listish_value(value)
        return value

    @field_validator(
        "analysis_allowed_video_mime_types",
        "analysis_allowed_audio_mime_types",
        "analysis_allowed_text_mime_types",
        mode="before",
    )
    @classmethod
    def _parse_analysis_allowed_mime_types(cls, value: object) -> object:
        if isinstance(value, str):
            return cls._parse_listish_value(value)
        return value

    @field_validator("api_v1_prefix")
    @classmethod
    def _validate_api_prefix(cls, value: str) -> str:
        normalized = value.strip() or "/api/v1"
        if not normalized.startswith("/"):
            normalized = f"/{normalized}"
        return normalized.rstrip("/") or "/api/v1"

    @staticmethod
    def _parse_listish_value(raw_value: str) -> list[str]:
        stripped = raw_value.strip()
        if not stripped:
            return []
        if stripped.startswith("["):
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        return [item.strip().strip("\"'") for item in stripped.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
