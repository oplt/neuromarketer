from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from backend.services.document_text_extractor import DEFAULT_ANALYSIS_ALLOWED_TEXT_MIME_TYPES

ENV_FILE = Path(__file__).resolve().parents[1] / ".env"
EnvironmentName = Literal["development", "staging", "production", "test"]
LogFormatName = Literal["auto", "pretty", "json"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        env_ignore_empty=True,
    )

    app_name: str = "NeuroMarketer API"
    app_env: EnvironmentName = Field(
        default="development",
        validation_alias=AliasChoices("ENVIRONMENT", "APP_ENV"),
    )
    app_version: str = "0.3.0"
    api_v1_prefix: str = "/api/v1"
    debug: bool = False
    service_name: str = Field(default="neuromarketer-api", validation_alias="SERVICE_NAME")
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    log_format: LogFormatName = Field(default="auto", validation_alias="LOG_FORMAT")
    log_to_file: bool = Field(default=False, validation_alias="LOG_TO_FILE")
    log_file_path: str = Field(default="./logs/app.log", validation_alias="LOG_FILE_PATH")
    log_file_max_bytes: int = Field(default=10 * 1024 * 1024, validation_alias="LOG_FILE_MAX_BYTES")
    log_file_backup_count: int = Field(default=5, validation_alias="LOG_FILE_BACKUP_COUNT")
    otel_enabled: bool = Field(default=False, validation_alias="OTEL_ENABLED")
    otel_service_name: str | None = Field(default=None, validation_alias="OTEL_SERVICE_NAME")
    otel_exporter_otlp_endpoint: str | None = Field(default=None, validation_alias="OTEL_EXPORTER_OTLP_ENDPOINT")

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
    session_idle_ttl_minutes: int = Field(default=60 * 24, validation_alias="SESSION_IDLE_TTL_MINUTES")
    session_touch_interval_seconds: int = Field(default=60, validation_alias="SESSION_TOUCH_INTERVAL_SECONDS")
    mfa_challenge_ttl_minutes: int = Field(default=10, validation_alias="MFA_CHALLENGE_TTL_MINUTES")
    invite_ttl_hours: int = Field(default=24 * 7, validation_alias="INVITE_TTL_HOURS")
    sso_enforcement_default: bool = Field(default=False, validation_alias="SSO_ENFORCEMENT_DEFAULT")

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
        default_factory=lambda: list(DEFAULT_ANALYSIS_ALLOWED_TEXT_MIME_TYPES),
        validation_alias="ANALYSIS_ALLOWED_TEXT_MIME_TYPES",
    )
    analysis_max_text_characters: int = Field(default=50_000, validation_alias="ANALYSIS_MAX_TEXT_CHARACTERS")

    celery_broker_url: str = Field(default="redis://localhost:6379/0", validation_alias="CELERY_BROKER_URL")
    celery_result_backend: str = Field(
        default="redis://localhost:6379/1",
        validation_alias="CELERY_RESULT_BACKEND",
    )
    celery_inference_queue: str = Field(default="analysis-inference", validation_alias="CELERY_INFERENCE_QUEUE")
    celery_scoring_queue: str = Field(default="analysis-scoring", validation_alias="CELERY_SCORING_QUEUE")
    celery_worker_role: str = Field(default="default", validation_alias="CELERY_WORKER_ROLE")
    celery_soft_time_limit_seconds: int = Field(default=900, validation_alias="CELERY_SOFT_TIME_LIMIT_SECONDS")
    celery_time_limit_seconds: int = Field(default=1200, validation_alias="CELERY_TIME_LIMIT_SECONDS")
    celery_job_stale_after_seconds: int = Field(default=1800, validation_alias="CELERY_JOB_STALE_AFTER_SECONDS")
    analysis_progress_snapshot_refresh_seconds: float = Field(
        default=5.0,
        validation_alias="ANALYSIS_PROGRESS_SNAPSHOT_REFRESH_SECONDS",
    )

    tribe_model_repo_id: str = Field(default="facebook/tribev2", validation_alias="TRIBE_MODEL_REPO_ID")
    tribe_checkpoint_name: str = Field(default="best.ckpt", validation_alias="TRIBE_CHECKPOINT_NAME")
    tribe_cache_folder: str = Field(default="./cache/tribev2", validation_alias="TRIBE_CACHE_FOLDER")
    asset_cache_folder: str = Field(default="./cache/assets", validation_alias="ASSET_CACHE_FOLDER")
    tribe_runtime_output_cache_folder: str = Field(
        default="./cache/tribev2/runtime-output",
        validation_alias="TRIBE_RUNTIME_OUTPUT_CACHE_FOLDER",
    )
    tribe_device: str = Field(default="auto", validation_alias="TRIBE_DEVICE")
    tribe_text_feature_model_name: str = Field(
        default="microsoft/Phi-3-mini-4k-instruct",
        validation_alias=AliasChoices("TRIBE_TEXT_FEATURE_MODEL_NAME", "TRIBE_TEXT_MODEL_NAME"),
    )
    tribe_feature_cluster: str | None = Field(default=None, validation_alias="TRIBE_FEATURE_CLUSTER")
    tribe_hf_token: str | None = Field(
        default=None,
        validation_alias=AliasChoices("TRIBE_HF_TOKEN", "HF_TOKEN", "HUGGINGFACE_HUB_TOKEN"),
    )
    tribe_video_feature_frequency_hz: float | None = Field(
        default=None,
        validation_alias="TRIBE_VIDEO_FEATURE_FREQUENCY_HZ",
    )
    tribe_video_max_imsize: int | None = Field(
        default=None,
        validation_alias="TRIBE_VIDEO_MAX_IMSIZE",
    )
    tribe_preload_on_worker_startup: bool = Field(default=True, validation_alias="TRIBE_PRELOAD_ON_WORKER_STARTUP")
    tribe_validate_binaries_on_worker_startup: bool = Field(
        default=True,
        validation_alias="TRIBE_VALIDATE_BINARIES_ON_WORKER_STARTUP",
    )
    tribe_runtime_output_cache_enabled: bool = Field(
        default=True,
        validation_alias="TRIBE_RUNTIME_OUTPUT_CACHE_ENABLED",
    )
    tribe_runtime_output_cache_max_bytes: int = Field(
        default=5 * 1024 * 1024 * 1024,
        validation_alias="TRIBE_RUNTIME_OUTPUT_CACHE_MAX_BYTES",
    )
    tribe_runtime_output_cache_max_age_hours: int = Field(
        default=24 * 7,
        validation_alias="TRIBE_RUNTIME_OUTPUT_CACHE_MAX_AGE_HOURS",
    )
    tribe_runtime_output_cache_cleanup_interval_minutes: int = Field(
        default=15,
        validation_alias="TRIBE_RUNTIME_OUTPUT_CACHE_CLEANUP_INTERVAL_MINUTES",
    )
    tribe_enable_roi_summary: bool = Field(default=False, validation_alias="TRIBE_ENABLE_ROI_SUMMARY")

    llm_provider: Literal["ollama", "openai_compatible", "vllm", "lm_studio"] = Field(
        default="ollama",
        validation_alias="LLM_PROVIDER",
    )
    llm_base_url: str = Field(default="http://localhost:11434", validation_alias="LLM_BASE_URL")
    llm_model: str = Field(default="gemma3:27b", validation_alias="LLM_MODEL")
    llm_api_key: str | None = Field(default=None, validation_alias="LLM_API_KEY")
    llm_timeout_seconds: int = Field(default=120, validation_alias="LLM_TIMEOUT_SECONDS")
    llm_max_tokens: int = Field(default=1400, validation_alias="LLM_MAX_TOKENS")
    llm_analysis_scoring_max_tokens: int = Field(
        default=1400,
        validation_alias="LLM_ANALYSIS_SCORING_MAX_TOKENS",
    )
    llm_temperature: float = Field(default=0.2, validation_alias="LLM_TEMPERATURE")
    llm_top_p: float = Field(default=0.9, validation_alias="LLM_TOP_P")
    llm_ollama_think: bool = Field(default=False, validation_alias="LLM_OLLAMA_THINK")
    llm_router_providers_json: list[dict[str, Any]] = Field(
        default_factory=list,
        validation_alias="LLM_ROUTER_PROVIDERS_JSON",
    )
    llm_routing_modes_json: dict[str, list[str]] = Field(
        default_factory=dict,
        validation_alias="LLM_ROUTING_MODES_JSON",
    )
    llm_mode_request_budgets_json: dict[str, float] = Field(
        default_factory=dict,
        validation_alias="LLM_MODE_REQUEST_BUDGETS_JSON",
    )
    llm_request_budget_usd: float = Field(default=0.25, validation_alias="LLM_REQUEST_BUDGET_USD")
    llm_retry_max_attempts: int = Field(default=2, validation_alias="LLM_RETRY_MAX_ATTEMPTS")
    llm_retry_backoff_seconds: float = Field(default=1.0, validation_alias="LLM_RETRY_BACKOFF_SECONDS")
    llm_circuit_breaker_failure_threshold: int = Field(
        default=3,
        validation_alias="LLM_CIRCUIT_BREAKER_FAILURE_THRESHOLD",
    )
    llm_circuit_breaker_reset_seconds: int = Field(
        default=300,
        validation_alias="LLM_CIRCUIT_BREAKER_RESET_SECONDS",
    )
    llm_cost_input_per_1k_tokens: float = Field(default=0.0, validation_alias="LLM_COST_INPUT_PER_1K_TOKENS")
    llm_cost_output_per_1k_tokens: float = Field(default=0.0, validation_alias="LLM_COST_OUTPUT_PER_1K_TOKENS")
    llm_processing_stale_after_seconds: int = Field(
        default=900,
        validation_alias="LLM_PROCESSING_STALE_AFTER_SECONDS",
    )

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

    @field_validator("llm_router_providers_json", mode="before")
    @classmethod
    def _parse_llm_router_providers_json(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                return []
            return parsed if isinstance(parsed, list) else []
        return value

    @field_validator("llm_routing_modes_json", "llm_mode_request_budgets_json", mode="before")
    @classmethod
    def _parse_llm_routing_json(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return {}
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                return {}
            return parsed if isinstance(parsed, dict) else {}
        return value

    @field_validator("api_v1_prefix")
    @classmethod
    def _validate_api_prefix(cls, value: str) -> str:
        normalized = value.strip() or "/api/v1"
        if not normalized.startswith("/"):
            normalized = f"/{normalized}"
        return normalized.rstrip("/") or "/api/v1"

    @field_validator("app_env", mode="before")
    @classmethod
    def _normalize_app_env(cls, value: object) -> object:
        if not isinstance(value, str):
            return value

        normalized = value.strip().lower()
        aliases = {
            "local": "development",
            "dev": "development",
            "development": "development",
            "stage": "staging",
            "staging": "staging",
            "prod": "production",
            "production": "production",
            "test": "test",
            "testing": "test",
        }
        return aliases.get(normalized, value)

    @model_validator(mode="after")
    def _block_insecure_production_defaults(self) -> "Settings":
        if self.app_env == "production":
            insecure_secrets = ("dev-session-secret", "CHANGE_ME_USE_openssl_rand_hex_64", "")
            if self.session_secret in insecure_secrets or len(self.session_secret) < 32:
                raise ValueError(
                    "SESSION_SECRET must be set to a strong random value (>=32 chars) in production. "
                    "Generate one with: openssl rand -hex 64"
                )
        return self

    @field_validator("log_format", mode="before")
    @classmethod
    def _normalize_log_format(cls, value: object) -> object:
        if not isinstance(value, str):
            return value

        normalized = value.strip().lower()
        aliases = {
            "auto": "auto",
            "console": "pretty",
            "pretty": "pretty",
            "json": "json",
        }
        return aliases.get(normalized, value)

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
