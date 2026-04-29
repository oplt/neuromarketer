from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from backend.core.config import settings
from backend.core.exceptions import ValidationAppError
from backend.core.log_context import bound_log_context
from backend.core.logging import duration_ms, get_logger, log_event, log_exception
from backend.core.metrics import metrics
from backend.db.models import CreativeVersion
from backend.services.asset_loader import AssetLoader, LoadedAsset
from backend.services.preprocess import PreprocessService
from backend.services.tribe_runtime import (
    TribeRuntimeInput,
    TribeRuntimeOutput,
    get_shared_tribe_runtime,
)

logger = get_logger(__name__)
CACHE_FORMAT_VERSION = 1
CACHE_TOUCH_MIN_INTERVAL = timedelta(minutes=5)


@dataclass(slots=True)
class TribeInferenceExecution:
    modality: str
    runtime_output: TribeRuntimeOutput
    source_label: str | None
    inference_duration_seconds: float


class TribeInferenceService:
    _last_cache_cleanup_monotonic: float = 0.0
    _last_extractor_cache_cleanup_monotonic: float = 0.0
    _extractor_cache_startup_purged: bool = False

    def __init__(self) -> None:
        self.asset_loader: AssetLoader | None = None
        self.preprocess = PreprocessService()
        self.runtime = get_shared_tribe_runtime()
        self.runtime_output_cache_enabled = settings.tribe_runtime_output_cache_enabled
        self.runtime_output_cache_folder = Path(
            settings.tribe_runtime_output_cache_folder
        ).expanduser()
        self.runtime_output_cache_max_bytes = max(0, settings.tribe_runtime_output_cache_max_bytes)
        self.runtime_output_cache_max_age = timedelta(
            hours=max(0, settings.tribe_runtime_output_cache_max_age_hours)
        )
        self.runtime_output_cache_cleanup_interval_seconds = max(
            0,
            settings.tribe_runtime_output_cache_cleanup_interval_minutes * 60,
        )
        self.extractor_cache_cleanup_enabled = settings.tribe_extractor_cache_cleanup_enabled
        self.extractor_cache_root = self.runtime.cache_folder.resolve(strict=False)
        self.extractor_cache_max_bytes = max(0, settings.tribe_extractor_cache_max_bytes)
        self.extractor_cache_max_age = timedelta(
            hours=max(0, settings.tribe_extractor_cache_max_age_hours)
        )
        self.extractor_cache_cleanup_interval_seconds = max(
            0,
            settings.tribe_extractor_cache_cleanup_interval_minutes * 60,
        )
        self.extractor_cache_purge_on_startup = settings.tribe_extractor_cache_purge_on_startup
        self._purge_extractor_cache_on_startup_if_enabled()

    def _asset_loader(self) -> AssetLoader:
        if self.asset_loader is None:
            self.asset_loader = AssetLoader()
        return self.asset_loader

    def resolve_modality(self, creative_version: CreativeVersion) -> str:
        preprocessing_summary = creative_version.preprocessing_summary or {}
        modality = preprocessing_summary.get("modality")
        if isinstance(modality, str) and modality:
            return modality
        if creative_version.raw_text:
            return "text"
        return self.preprocess.detect_modality(filename=None, mime_type=creative_version.mime_type)

    def assert_ready_for_inference(
        self, *, creative_version: CreativeVersion, modality: str
    ) -> None:
        self.runtime.assert_supported_modality(modality)

        if modality == "text":
            if creative_version.raw_text and creative_version.raw_text.strip():
                return
            if creative_version.source_uri:
                return
            raise ValidationAppError(
                "Text creative versions require raw_text or a text source_uri for TRIBE inference."
            )

        if modality in {"video", "audio"} and not creative_version.source_uri:
            raise ValidationAppError(
                f"{modality.title()} creative versions require source_uri for TRIBE inference."
            )

    def run_for_version(
        self,
        *,
        creative_version: CreativeVersion,
        request_payload: dict,
        runtime_params: dict,
    ) -> TribeInferenceExecution:
        modality = self.resolve_modality(creative_version)
        self.assert_ready_for_inference(creative_version=creative_version, modality=modality)

        loaded_asset: LoadedAsset | None = None
        source_label = self._resolve_source_label(creative_version=creative_version)
        inference_started_at = time.perf_counter()

        with bound_log_context(
            creative_version_id=str(creative_version.id),
            modality=modality,
        ):
            try:
                self._maybe_cleanup_extractor_cache()
                cache_key = self._build_runtime_cache_key(
                    creative_version=creative_version,
                    modality=modality,
                )
                cached_output = self._load_cached_runtime_output(cache_key)
                if cached_output is not None:
                    finished_at = time.perf_counter()
                    metrics.increment(
                        "tribe_runtime_cache_hits_total",
                        labels={"modality": modality},
                    )
                    log_event(
                        logger,
                        "tribe_inference_cache_hit",
                        creative_version_id=str(creative_version.id),
                        modality=modality,
                        source_label=source_label,
                        cache_key=cache_key,
                        duration_ms=duration_ms(inference_started_at, finished_at),
                        status="cached",
                    )
                    return TribeInferenceExecution(
                        modality=modality,
                        runtime_output=cached_output,
                        source_label=source_label,
                        inference_duration_seconds=finished_at - inference_started_at,
                    )

                if modality in {"video", "audio"} or (
                    modality == "text"
                    and not (creative_version.raw_text and creative_version.raw_text.strip())
                ):
                    asset_load_started_at = time.perf_counter()
                    loaded_asset = self._load_asset(creative_version, modality=modality)
                    metrics.observe(
                        "prediction_job_stage_seconds",
                        time.perf_counter() - asset_load_started_at,
                        labels={"stage": "asset_load", "modality": modality},
                    )

                runtime_input = TribeRuntimeInput(
                    modality=modality,
                    local_path=loaded_asset.local_path if loaded_asset else None,
                    mime_type=creative_version.mime_type,
                    raw_text=creative_version.raw_text if modality == "text" else None,
                    metadata_json=creative_version.extracted_metadata or {},
                    request_context={
                        "request_payload": request_payload,
                        "runtime_params": runtime_params,
                    },
                )

                log_event(
                    logger,
                    "tribe_inference_started",
                    creative_version_id=str(creative_version.id),
                    modality=modality,
                    source_label=source_label,
                    status="started",
                )
                runtime_output = self.runtime.infer(runtime_input)
                self._store_cached_runtime_output(cache_key, runtime_output)
                finished_at = time.perf_counter()
                log_event(
                    logger,
                    "tribe_inference_finished",
                    creative_version_id=str(creative_version.id),
                    modality=modality,
                    source_label=source_label,
                    duration_ms=duration_ms(inference_started_at, finished_at),
                    segment_count=int(
                        (runtime_output.reduced_feature_vector or {}).get("segment_count", 0)
                    ),
                    status="succeeded",
                )

                return TribeInferenceExecution(
                    modality=modality,
                    runtime_output=runtime_output,
                    source_label=source_label,
                    inference_duration_seconds=finished_at - inference_started_at,
                )
            except Exception as exc:
                finished_at = time.perf_counter()
                log_exception(
                    logger,
                    "tribe_inference_failed",
                    exc,
                    creative_version_id=str(creative_version.id),
                    modality=modality,
                    source_label=source_label,
                    duration_ms=duration_ms(inference_started_at, finished_at),
                    status="failed",
                )
                raise
            finally:
                if loaded_asset is not None:
                    loaded_asset.cleanup()

    def _build_runtime_cache_key(self, *, creative_version: CreativeVersion, modality: str) -> str:
        preprocessing_summary = dict(creative_version.preprocessing_summary or {})
        preprocessing_version = (
            preprocessing_summary.get("preprocessing_version")
            or preprocessing_summary.get("schema_version")
            or preprocessing_summary.get("version")
        )
        cache_identity = {
            "creative_version_id": str(creative_version.id),
            "sha256": creative_version.sha256,
            "source_uri": creative_version.source_uri,
            "raw_text_sha256": hashlib.sha256(
                (creative_version.raw_text or "").encode("utf-8")
            ).hexdigest(),
            "mime_type": creative_version.mime_type,
            "modality": modality,
            "preprocessing_version": preprocessing_version,
            "model_repo_id": self.runtime.model_repo_id,
            "checkpoint_name": self.runtime.checkpoint_name,
            "requested_device": self.runtime.get_requested_device(),
            "text_feature_model_name": self.runtime.text_feature_model_name,
            "feature_cluster": self.runtime.feature_cluster,
        }
        encoded = json.dumps(cache_identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _resolve_runtime_cache_path(self, cache_key: str) -> Path:
        return self.runtime_output_cache_folder / f"{cache_key}.json"

    def _load_cached_runtime_output(self, cache_key: str) -> TribeRuntimeOutput | None:
        if not self.runtime_output_cache_enabled:
            return None

        cache_path = self._resolve_runtime_cache_path(cache_key)
        if not cache_path.is_file():
            return None

        try:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception as exc:
            log_exception(
                logger,
                "tribe_inference_cache_read_failed",
                exc,
                cache_key=cache_key,
                cache_path=str(cache_path),
                level="warning",
                status="ignored",
            )
            return None

        if not isinstance(payload, dict):
            return None

        runtime_payload = (
            payload.get("payload") if isinstance(payload.get("payload"), dict) else payload
        )
        self._touch_runtime_cache_entry(cache_path, payload)

        return TribeRuntimeOutput(
            raw_brain_response_uri=runtime_payload.get("raw_brain_response_uri"),
            raw_brain_response_summary=self._coerce_mapping(
                runtime_payload.get("raw_brain_response_summary")
            ),
            reduced_feature_vector=self._coerce_mapping(
                runtime_payload.get("reduced_feature_vector")
            ),
            region_activation_summary=self._coerce_mapping(
                runtime_payload.get("region_activation_summary")
            ),
            provenance_json=self._coerce_mapping(runtime_payload.get("provenance_json")),
        )

    def _store_cached_runtime_output(
        self, cache_key: str, runtime_output: TribeRuntimeOutput
    ) -> None:
        if not self.runtime_output_cache_enabled:
            return

        cache_path = self._resolve_runtime_cache_path(cache_key)
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            now_iso = datetime.now(UTC).isoformat()
            payload = {
                "cache_version": CACHE_FORMAT_VERSION,
                "created_at": now_iso,
                "last_accessed_at": now_iso,
                "payload": {
                    "raw_brain_response_uri": runtime_output.raw_brain_response_uri,
                    "raw_brain_response_summary": runtime_output.raw_brain_response_summary,
                    "reduced_feature_vector": runtime_output.reduced_feature_vector,
                    "region_activation_summary": runtime_output.region_activation_summary,
                    "provenance_json": runtime_output.provenance_json,
                },
            }
            self._write_runtime_cache_document_atomic(
                cache_path=cache_path,
                encoded_payload=self._encode_runtime_cache_document(payload),
            )
            self._maybe_cleanup_runtime_cache()
        except Exception as exc:
            log_exception(
                logger,
                "tribe_inference_cache_write_failed",
                exc,
                cache_key=cache_key,
                cache_path=str(cache_path),
                level="warning",
                status="ignored",
            )

    def _touch_runtime_cache_entry(self, cache_path: Path, payload: dict[str, Any]) -> None:
        if "payload" not in payload:
            return

        last_accessed_at = self._parse_cache_timestamp(payload.get("last_accessed_at"))
        now = datetime.now(UTC)
        if (
            last_accessed_at is not None
            and now - last_accessed_at < CACHE_TOUCH_MIN_INTERVAL
        ):
            return

        try:
            next_payload = dict(payload)
            next_payload["last_accessed_at"] = now.isoformat()
            self._write_runtime_cache_document_atomic(
                cache_path=cache_path,
                encoded_payload=self._encode_runtime_cache_document(next_payload),
            )
        except Exception as exc:
            log_exception(
                logger,
                "tribe_inference_cache_touch_failed",
                exc,
                cache_path=str(cache_path),
                level="warning",
                status="ignored",
            )

    def run_cache_cleanup(
        self,
        *,
        purge_extractor: bool = False,
        purge_runtime: bool = False,
    ) -> dict[str, Any]:
        runtime_before = self._collect_runtime_cache_entries()
        extractor_before = self._collect_extractor_cache_entries()

        if purge_runtime:
            self._purge_runtime_cache(reason="manual_purge")
        else:
            self._maybe_cleanup_runtime_cache(force=True)
        if purge_extractor:
            self._purge_extractor_cache(reason="manual_purge")
        else:
            self._maybe_cleanup_extractor_cache(force=True)

        runtime_after = self._collect_runtime_cache_entries()
        extractor_after = self._collect_extractor_cache_entries()
        return {
            "runtime": {
                "before_files": len(runtime_before),
                "after_files": len(runtime_after),
                "before_bytes": sum(item["size_bytes"] for item in runtime_before),
                "after_bytes": sum(item["size_bytes"] for item in runtime_after),
                "purged": purge_runtime,
            },
            "extractor": {
                "before_files": len(extractor_before),
                "after_files": len(extractor_after),
                "before_bytes": sum(item["size_bytes"] for item in extractor_before),
                "after_bytes": sum(item["size_bytes"] for item in extractor_after),
                "purged": purge_extractor,
            },
        }

    def _purge_runtime_cache(self, *, reason: str) -> None:
        cleanup_started_at = time.perf_counter()
        evicted_files = 0
        evicted_bytes = 0
        try:
            for entry in self._collect_runtime_cache_entries():
                evicted_files += 1
                evicted_bytes += entry["size_bytes"]
                self._delete_runtime_cache_path(entry["path"], reason=reason)
            log_event(
                logger,
                "tribe_runtime_cache_manual_purge_completed",
                cache_folder=str(self.runtime_output_cache_folder),
                evicted_file_count=evicted_files,
                evicted_bytes=evicted_bytes,
                duration_ms=duration_ms(cleanup_started_at, time.perf_counter()),
                status="completed",
            )
        except Exception as exc:
            log_exception(
                logger,
                "tribe_runtime_cache_manual_purge_failed",
                exc,
                cache_folder=str(self.runtime_output_cache_folder),
                level="warning",
                status="ignored",
            )

    def _maybe_cleanup_runtime_cache(self, *, force: bool = False) -> None:
        if not self.runtime_output_cache_enabled:
            return

        now_monotonic = time.monotonic()
        last_cleanup = self.__class__._last_cache_cleanup_monotonic
        if (
            not force
            and self.runtime_output_cache_cleanup_interval_seconds > 0
            and now_monotonic - last_cleanup < self.runtime_output_cache_cleanup_interval_seconds
        ):
            return

        self.__class__._last_cache_cleanup_monotonic = now_monotonic
        self._cleanup_runtime_cache_entries()

    def _cleanup_runtime_cache_entries(self) -> None:
        cleanup_started_at = time.perf_counter()
        evicted_files = 0
        evicted_bytes = 0

        try:
            entries = self._collect_runtime_cache_entries()
            now = datetime.now(UTC)
            retained_entries: list[dict[str, Any]] = []

            for entry in entries:
                if (
                    self.runtime_output_cache_max_age > timedelta(0)
                    and now - entry["last_accessed_at"] > self.runtime_output_cache_max_age
                ):
                    evicted_files += 1
                    evicted_bytes += entry["size_bytes"]
                    self._delete_runtime_cache_path(entry["path"], reason="expired")
                    continue
                retained_entries.append(entry)

            total_bytes = sum(entry["size_bytes"] for entry in retained_entries)
            if (
                self.runtime_output_cache_max_bytes > 0
                and total_bytes > self.runtime_output_cache_max_bytes
            ):
                for entry in sorted(
                    retained_entries,
                    key=lambda item: (item["last_accessed_at"], item["created_at"]),
                ):
                    if total_bytes <= self.runtime_output_cache_max_bytes:
                        break
                    total_bytes -= entry["size_bytes"]
                    evicted_files += 1
                    evicted_bytes += entry["size_bytes"]
                    self._delete_runtime_cache_path(entry["path"], reason="size_limit")

            metrics.observe(
                "tribe_runtime_cache_cleanup_seconds", time.perf_counter() - cleanup_started_at
            )
            remaining_entries = self._collect_runtime_cache_entries()
            log_event(
                logger,
                "tribe_runtime_cache_cleanup_completed",
                cache_folder=str(self.runtime_output_cache_folder),
                retained_file_count=len(remaining_entries),
                evicted_file_count=evicted_files,
                evicted_bytes=evicted_bytes,
                max_bytes=self.runtime_output_cache_max_bytes,
                max_age_hours=int(self.runtime_output_cache_max_age.total_seconds() // 3600),
                duration_ms=duration_ms(cleanup_started_at, time.perf_counter()),
                status="completed",
            )
        except Exception as exc:
            log_exception(
                logger,
                "tribe_runtime_cache_cleanup_failed",
                exc,
                cache_folder=str(self.runtime_output_cache_folder),
                level="warning",
                status="ignored",
            )

    def _purge_extractor_cache_on_startup_if_enabled(self) -> None:
        if not self.extractor_cache_cleanup_enabled or not self.extractor_cache_purge_on_startup:
            return
        if self.__class__._extractor_cache_startup_purged:
            return

        self.__class__._extractor_cache_startup_purged = True
        self._purge_extractor_cache(reason="startup_purge")

    def _maybe_cleanup_extractor_cache(self, *, force: bool = False) -> None:
        if not self.extractor_cache_cleanup_enabled:
            return

        now_monotonic = time.monotonic()
        last_cleanup = self.__class__._last_extractor_cache_cleanup_monotonic
        if (
            not force
            and self.extractor_cache_cleanup_interval_seconds > 0
            and now_monotonic - last_cleanup < self.extractor_cache_cleanup_interval_seconds
        ):
            return

        self.__class__._last_extractor_cache_cleanup_monotonic = now_monotonic
        self._cleanup_extractor_cache_entries()

    def _cleanup_extractor_cache_entries(self) -> None:
        cleanup_started_at = time.perf_counter()
        evicted_files = 0
        evicted_bytes = 0

        try:
            entries = self._collect_extractor_cache_entries()
            now = datetime.now(UTC)
            retained_entries: list[dict[str, Any]] = []

            for entry in entries:
                if (
                    self.extractor_cache_max_age > timedelta(0)
                    and now - entry["last_accessed_at"] > self.extractor_cache_max_age
                ):
                    evicted_files += 1
                    evicted_bytes += entry["size_bytes"]
                    self._delete_extractor_cache_path(entry["path"], reason="expired")
                    continue
                retained_entries.append(entry)

            total_bytes = sum(entry["size_bytes"] for entry in retained_entries)
            if self.extractor_cache_max_bytes > 0 and total_bytes > self.extractor_cache_max_bytes:
                for entry in sorted(
                    retained_entries,
                    key=lambda item: (item["last_accessed_at"], item["created_at"]),
                ):
                    if total_bytes <= self.extractor_cache_max_bytes:
                        break
                    total_bytes -= entry["size_bytes"]
                    evicted_files += 1
                    evicted_bytes += entry["size_bytes"]
                    self._delete_extractor_cache_path(entry["path"], reason="size_limit")

            self._cleanup_empty_extractor_dirs()
            metrics.observe(
                "tribe_extractor_cache_cleanup_seconds",
                time.perf_counter() - cleanup_started_at,
            )
            remaining_entries = self._collect_extractor_cache_entries()
            log_event(
                logger,
                "tribe_extractor_cache_cleanup_completed",
                cache_root=str(self.extractor_cache_root),
                retained_file_count=len(remaining_entries),
                evicted_file_count=evicted_files,
                evicted_bytes=evicted_bytes,
                max_bytes=self.extractor_cache_max_bytes,
                max_age_hours=int(self.extractor_cache_max_age.total_seconds() // 3600),
                duration_ms=duration_ms(cleanup_started_at, time.perf_counter()),
                status="completed",
            )
        except Exception as exc:
            log_exception(
                logger,
                "tribe_extractor_cache_cleanup_failed",
                exc,
                cache_root=str(self.extractor_cache_root),
                level="warning",
                status="ignored",
            )

    def _purge_extractor_cache(self, *, reason: str) -> None:
        cleanup_started_at = time.perf_counter()
        evicted_files = 0
        evicted_bytes = 0
        event_name = (
            "tribe_extractor_cache_startup_purge_completed"
            if reason == "startup_purge"
            else "tribe_extractor_cache_manual_purge_completed"
        )
        failed_event_name = (
            "tribe_extractor_cache_startup_purge_failed"
            if reason == "startup_purge"
            else "tribe_extractor_cache_manual_purge_failed"
        )

        try:
            for entry in self._collect_extractor_cache_entries():
                evicted_files += 1
                evicted_bytes += entry["size_bytes"]
                self._delete_extractor_cache_path(entry["path"], reason=reason)
            self._cleanup_empty_extractor_dirs()
            log_event(
                logger,
                event_name,
                cache_root=str(self.extractor_cache_root),
                evicted_file_count=evicted_files,
                evicted_bytes=evicted_bytes,
                duration_ms=duration_ms(cleanup_started_at, time.perf_counter()),
                status="completed",
            )
        except Exception as exc:
            log_exception(
                logger,
                failed_event_name,
                exc,
                cache_root=str(self.extractor_cache_root),
                level="warning",
                status="ignored",
            )

    def _collect_extractor_cache_entries(self) -> list[dict[str, Any]]:
        if not self.extractor_cache_root.exists():
            return []

        entries: list[dict[str, Any]] = []
        for extractor_root in self._extractor_cache_directories():
            for cache_path in extractor_root.rglob("*"):
                resolved_path = cache_path.resolve()
                if not self._is_extractor_cache_path_safe(resolved_path):
                    continue
                if not resolved_path.is_file():
                    continue
                stat = resolved_path.stat()
                entries.append(
                    {
                        "path": resolved_path,
                        "created_at": datetime.fromtimestamp(stat.st_ctime, tz=UTC),
                        "last_accessed_at": datetime.fromtimestamp(stat.st_mtime, tz=UTC),
                        "size_bytes": max(int(stat.st_size), 0),
                    }
                )
        return entries

    def _extractor_cache_directories(self) -> list[Path]:
        if not self.extractor_cache_root.exists():
            return []
        return [
            entry.resolve()
            for entry in self.extractor_cache_root.glob("neuralset.extractors.*")
            if entry.is_dir()
        ]

    def _cleanup_empty_extractor_dirs(self) -> None:
        for extractor_root in self._extractor_cache_directories():
            nested_paths = sorted(
                extractor_root.rglob("*"),
                key=lambda path: len(path.parts),
                reverse=True,
            )
            for candidate in nested_paths:
                if not candidate.is_dir():
                    continue
                if any(candidate.iterdir()):
                    continue
                candidate.rmdir()
            if extractor_root.exists() and not any(extractor_root.iterdir()):
                extractor_root.rmdir()

    def _delete_extractor_cache_path(self, cache_path: Path, *, reason: str) -> None:
        resolved_path = cache_path.resolve()
        if not self._is_extractor_cache_path_safe(resolved_path):
            log_event(
                logger,
                "tribe_extractor_cache_delete_blocked",
                cache_path=str(resolved_path),
                reason=reason,
                level="warning",
                status="blocked",
            )
            return

        resolved_path.unlink(missing_ok=True)
        metrics.increment("tribe_extractor_cache_evictions_total", labels={"reason": reason})

    def _is_extractor_cache_path_safe(self, cache_path: Path) -> bool:
        try:
            cache_path.relative_to(self.extractor_cache_root)
            return any(
                cache_path.relative_to(root).parts
                for root in self._extractor_cache_directories()
                if cache_path.is_relative_to(root)
            )
        except ValueError:
            return False

    def _collect_runtime_cache_entries(self) -> list[dict[str, Any]]:
        cache_root = self.runtime_output_cache_folder.resolve()
        if not cache_root.exists():
            return []

        entries: list[dict[str, Any]] = []
        for cache_path in cache_root.glob("*.json"):
            resolved_path = cache_path.resolve()
            if not self._is_runtime_cache_path_safe(resolved_path):
                continue
            if not resolved_path.is_file():
                continue

            stat = resolved_path.stat()
            created_at = datetime.fromtimestamp(stat.st_ctime, tz=UTC)
            last_accessed_at = datetime.fromtimestamp(stat.st_mtime, tz=UTC)
            size_bytes = int(stat.st_size)

            try:
                payload = json.loads(resolved_path.read_text(encoding="utf-8"))
            except Exception:
                payload = None

            if isinstance(payload, dict):
                created_at = self._parse_cache_timestamp(payload.get("created_at")) or created_at
                last_accessed_at = (
                    self._parse_cache_timestamp(payload.get("last_accessed_at")) or last_accessed_at
                )
                size_bytes = int(payload.get("size_bytes") or size_bytes)

            entries.append(
                {
                    "path": resolved_path,
                    "created_at": created_at,
                    "last_accessed_at": last_accessed_at,
                    "size_bytes": max(size_bytes, 0),
                }
            )
        return entries

    def _delete_runtime_cache_path(self, cache_path: Path, *, reason: str) -> None:
        resolved_path = cache_path.resolve()
        if not self._is_runtime_cache_path_safe(resolved_path):
            log_event(
                logger,
                "tribe_runtime_cache_delete_blocked",
                cache_path=str(resolved_path),
                reason=reason,
                level="warning",
                status="blocked",
            )
            return

        resolved_path.unlink(missing_ok=True)
        metrics.increment("tribe_runtime_cache_evictions_total", labels={"reason": reason})

    @staticmethod
    def _encode_runtime_cache_document(payload: dict[str, Any]) -> str:
        next_payload = dict(payload)
        next_payload["size_bytes"] = 0
        encoded = json.dumps(next_payload, sort_keys=True)
        next_payload["size_bytes"] = len(encoded.encode("utf-8"))
        return json.dumps(next_payload, sort_keys=True)

    def _write_runtime_cache_document_atomic(
        self,
        *,
        cache_path: Path,
        encoded_payload: str,
    ) -> None:
        temp_path = cache_path.with_suffix(
            f"{cache_path.suffix}.{os.getpid()}.{time.monotonic_ns()}.tmp"
        )
        temp_path.write_text(encoded_payload, encoding="utf-8")
        temp_path.replace(cache_path)

    def _is_runtime_cache_path_safe(self, cache_path: Path) -> bool:
        try:
            cache_path.relative_to(self.runtime_output_cache_folder.resolve())
            return True
        except ValueError:
            return False

    @staticmethod
    def _parse_cache_timestamp(value: Any) -> datetime | None:
        if not isinstance(value, str) or not value.strip():
            return None
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)

    def _load_asset(self, creative_version: CreativeVersion, *, modality: str) -> LoadedAsset:
        return self._asset_loader().load(
            storage_uri=str(creative_version.source_uri),
            mime_type=creative_version.mime_type,
        )

    def resolve_source_label(self, *, creative_version: CreativeVersion) -> str | None:
        return self._resolve_source_label(creative_version=creative_version)

    def runtime_output_from_prediction(self, prediction) -> TribeRuntimeOutput:
        return TribeRuntimeOutput(
            raw_brain_response_uri=prediction.raw_brain_response_uri,
            raw_brain_response_summary=dict(prediction.raw_brain_response_summary or {}),
            reduced_feature_vector=dict(prediction.reduced_feature_vector or {}),
            region_activation_summary=dict(prediction.region_activation_summary or {}),
            provenance_json=dict(prediction.provenance_json or {}),
        )

    def _resolve_source_label(self, *, creative_version: CreativeVersion) -> str | None:
        if creative_version.raw_text and creative_version.raw_text.strip():
            return "Inline text input"
        if creative_version.source_uri:
            return creative_version.source_uri.rsplit("/", 1)[-1]
        return None

    @staticmethod
    def _coerce_mapping(value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}
