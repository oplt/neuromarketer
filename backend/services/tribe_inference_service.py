from __future__ import annotations

import time
from dataclasses import dataclass

from backend.core.log_context import bound_log_context
from backend.core.exceptions import ValidationAppError
from backend.core.logging import duration_ms, get_logger, log_event, log_exception
from backend.db.models import CreativeVersion
from backend.services.asset_loader import AssetLoader, LoadedAsset
from backend.services.preprocess import PreprocessService
from backend.services.tribe_runtime import TribeRuntimeInput, TribeRuntimeOutput, get_shared_tribe_runtime

logger = get_logger(__name__)


@dataclass(slots=True)
class TribeInferenceExecution:
    modality: str
    runtime_output: TribeRuntimeOutput
    source_label: str | None
    inference_duration_seconds: float


class TribeInferenceService:
    def __init__(self) -> None:
        self.asset_loader: AssetLoader | None = None
        self.preprocess = PreprocessService()
        self.runtime = get_shared_tribe_runtime()

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

    def assert_ready_for_inference(self, *, creative_version: CreativeVersion, modality: str) -> None:
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
            raise ValidationAppError(f"{modality.title()} creative versions require source_uri for TRIBE inference.")

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
                if modality in {"video", "audio"}:
                    loaded_asset = self._load_asset(creative_version, modality=modality)
                elif modality == "text" and not (creative_version.raw_text and creative_version.raw_text.strip()):
                    loaded_asset = self._load_asset(creative_version, modality=modality)

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
                finished_at = time.perf_counter()
                log_event(
                    logger,
                    "tribe_inference_finished",
                    creative_version_id=str(creative_version.id),
                    modality=modality,
                    source_label=source_label,
                    duration_ms=duration_ms(inference_started_at, finished_at),
                    segment_count=int((runtime_output.reduced_feature_vector or {}).get("segment_count", 0)),
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

    def _load_asset(self, creative_version: CreativeVersion, *, modality: str) -> LoadedAsset:
        return self._asset_loader().load(
            storage_uri=str(creative_version.source_uri),
            mime_type=creative_version.mime_type,
        )

    def _resolve_source_label(self, *, creative_version: CreativeVersion) -> str | None:
        if creative_version.raw_text and creative_version.raw_text.strip():
            return "Inline text input"
        if creative_version.source_uri:
            return creative_version.source_uri.rsplit("/", 1)[-1]
        return None
