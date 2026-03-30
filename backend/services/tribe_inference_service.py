from __future__ import annotations

import time
from dataclasses import dataclass

from backend.core.exceptions import ValidationAppError
from backend.core.logging import get_logger
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
        self.asset_loader = AssetLoader()
        self.preprocess = PreprocessService()
        self.runtime = get_shared_tribe_runtime()

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

        try:
            if modality in {"video", "audio"}:
                loaded_asset = self._load_asset(creative_version, modality=modality)
            elif modality == "text" and not (creative_version.raw_text and creative_version.raw_text.strip()):
                loaded_asset = self._load_asset(creative_version, modality=modality)

            logger.info(
                "Preprocessing complete for TRIBE inference input.",
                extra={
                    "event": "analysis_preprocessing_complete",
                    "extra_fields": {
                        "creative_version_id": str(creative_version.id),
                        "modality": modality,
                        "source_label": source_label,
                        "has_local_asset": loaded_asset is not None,
                    },
                },
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

            inference_started_at = time.perf_counter()
            runtime_output = self.runtime.infer(runtime_input)
            inference_duration_seconds = time.perf_counter() - inference_started_at

            logger.info(
                "TRIBE inference finished.",
                extra={
                    "event": "tribe_inference_finished",
                    "extra_fields": {
                        "creative_version_id": str(creative_version.id),
                        "modality": modality,
                        "source_label": source_label,
                        "duration_seconds": round(inference_duration_seconds, 3),
                        "segment_count": int(
                            (runtime_output.reduced_feature_vector or {}).get("segment_count", 0)
                        ),
                    },
                },
            )

            return TribeInferenceExecution(
                modality=modality,
                runtime_output=runtime_output,
                source_label=source_label,
                inference_duration_seconds=inference_duration_seconds,
            )
        finally:
            if loaded_asset is not None:
                loaded_asset.cleanup()

    def _load_asset(self, creative_version: CreativeVersion, *, modality: str) -> LoadedAsset:
        logger.info(
            "Fetching media from object storage for TRIBE inference.",
            extra={
                "event": "tribe_media_fetch_started",
                "extra_fields": {
                    "creative_version_id": str(creative_version.id),
                    "modality": modality,
                    "source_uri": creative_version.source_uri,
                },
            },
        )
        loaded_asset = self.asset_loader.load(
            storage_uri=str(creative_version.source_uri),
            mime_type=creative_version.mime_type,
        )
        logger.info(
            "Fetched media for TRIBE inference.",
            extra={
                "event": "tribe_media_fetch_finished",
                "extra_fields": {
                    "creative_version_id": str(creative_version.id),
                    "modality": modality,
                    "source_uri": creative_version.source_uri,
                    "local_path": loaded_asset.local_path,
                    "file_size_bytes": loaded_asset.file_size_bytes,
                },
            },
        )
        return loaded_asset

    def _resolve_source_label(self, *, creative_version: CreativeVersion) -> str | None:
        if creative_version.raw_text and creative_version.raw_text.strip():
            return "Inline text input"
        if creative_version.source_uri:
            return creative_version.source_uri.rsplit("/", 1)[-1]
        return None
