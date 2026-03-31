from __future__ import annotations

import importlib
import os
import shutil
import tempfile
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any

import numpy as np

from backend.core.config import settings
from backend.core.exceptions import (
    ConfigurationAppError,
    DependencyAppError,
    UnsupportedModalityAppError,
    ValidationAppError,
)
from backend.core.logging import get_logger
from backend.services.text_preprocess import TextPreprocessService

logger = get_logger(__name__)

SUPPORTED_TRIBE_MODALITIES = frozenset({"video", "audio", "text"})
UNSUPPORTED_TRIBE_MODALITIES = {
    "image": "The public TRIBE v2 inference API does not expose an official image-only path.",
    "html": "HTML creatives are not yet transformed into an official TRIBE v2-supported text/audio/video payload.",
    "url": "URL creatives are not yet fetched and transformed into an official TRIBE v2-supported payload.",
    "binary": "Binary assets do not map to a supported TRIBE v2 inference path.",
}


@dataclass(slots=True)
class TribeRuntimeInput:
    modality: str
    local_path: str | None = None
    mime_type: str | None = None
    raw_text: str | None = None
    metadata_json: dict[str, Any] | None = None
    request_context: dict[str, Any] | None = None


@dataclass(slots=True)
class TribeRuntimeOutput:
    raw_brain_response_uri: str | None
    raw_brain_response_summary: dict[str, Any]
    reduced_feature_vector: dict[str, Any]
    region_activation_summary: dict[str, Any]
    provenance_json: dict[str, Any]


class TribeRuntime:
    """
    Production inference boundary around the public TRIBE v2 package.

    The rest of the application does not receive raw TRIBE tensors or dataframes.
    It receives a stable internal contract made of:
    - summaries of the official prediction output
    - derived internal features used by our product layer
    - provenance that distinguishes direct foundation-model outputs from heuristics
    """

    _load_lock: Lock = Lock()
    _shared_model: Any | None = None
    _shared_module: Any | None = None
    _resolved_device: str | None = None

    def __init__(self) -> None:
        self.model_repo_id = settings.tribe_model_repo_id
        self.checkpoint_name = settings.tribe_checkpoint_name
        self.cache_folder = self._resolve_cache_folder(Path(settings.tribe_cache_folder).expanduser())
        self.device = settings.tribe_device
        self.feature_cluster = settings.tribe_feature_cluster
        self.hf_token = settings.tribe_hf_token
        self.enable_roi_summary = settings.tribe_enable_roi_summary
        self.text_preprocessor = TextPreprocessService()
        self.model_name = self.model_repo_id

    def _resolve_cache_folder(self, configured_path: Path) -> Path:
        candidates = self._candidate_cache_folders(configured_path)
        errors: list[str] = []

        for candidate in candidates:
            try:
                candidate.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                errors.append(f"{candidate}: {exc}")
                continue

            if os.access(candidate, os.W_OK):
                if candidate != configured_path:
                    logger.warning(
                        "Configured TRIBE cache folder is unavailable. Using fallback cache folder.",
                        extra={
                            "event": "tribe_cache_folder_fallback",
                            "extra_fields": {
                                "configured_path": str(configured_path),
                                "resolved_path": str(candidate),
                            },
                        },
                    )
                return candidate

            errors.append(f"{candidate}: not writable")

        raise ConfigurationAppError(
            "TRIBE cache folder could not be initialized. "
            + "; ".join(errors)
        )

    def _candidate_cache_folders(self, configured_path: Path) -> list[Path]:
        project_cache = Path(__file__).resolve().parents[2] / "cache" / "tribev2"
        temp_cache = Path(tempfile.gettempdir()) / "neuromarketer" / "tribev2"
        candidates = [configured_path, project_cache, temp_cache]
        resolved: list[Path] = []

        for candidate in candidates:
            normalized = candidate.resolve(strict=False)
            if normalized not in resolved:
                resolved.append(normalized)

        return resolved

    @classmethod
    def is_supported_modality(cls, modality: str) -> bool:
        return modality in SUPPORTED_TRIBE_MODALITIES

    @classmethod
    def modality_support_detail(cls, modality: str) -> dict[str, Any]:
        if cls.is_supported_modality(modality):
            return {
                "supported": True,
                "status": "supported",
                "reason": "This modality maps directly to the public TRIBE v2 get_events_dataframe API.",
            }
        return {
            "supported": False,
            "status": "unsupported",
            "reason": UNSUPPORTED_TRIBE_MODALITIES.get(
                modality,
                "This modality is not implemented in the current TRIBE v2 integration.",
            ),
        }

    @classmethod
    def assert_supported_modality(cls, modality: str) -> None:
        if cls.is_supported_modality(modality):
            return
        detail = cls.modality_support_detail(modality)
        raise UnsupportedModalityAppError(
            f"TRIBE v2 does not support modality '{modality}' in this integration. {detail['reason']}"
        )

    def validate_environment(self) -> None:
        self.cache_folder.mkdir(parents=True, exist_ok=True)
        if not os.access(self.cache_folder, os.W_OK):
            raise ConfigurationAppError(f"TRIBE cache folder is not writable: {self.cache_folder}")

        try:
            importlib.import_module("tribev2")
        except Exception as exc:  # pragma: no cover - exercised via unit tests with patched import
            raise DependencyAppError(
                "TRIBE v2 is not importable. Install the public package and its runtime dependencies first."
            ) from exc

        if not settings.tribe_validate_binaries_on_worker_startup:
            return

        missing_binaries = [name for name in ("uvx", "ffmpeg", "ffprobe") if shutil.which(name) is None]
        if missing_binaries:
            raise DependencyAppError(
                "TRIBE v2 preprocessing requires missing system binaries: "
                + ", ".join(sorted(missing_binaries))
            )

    def load(self) -> None:
        if self.__class__._shared_model is not None:
            return

        with self.__class__._load_lock:
            if self.__class__._shared_model is not None:
                return

            self.validate_environment()
            self._authenticate_huggingface()
            load_started_at = time.perf_counter()
            logger.info(
                "Initializing shared TRIBE model.",
                extra={
                    "event": "tribe_model_init_started",
                    "extra_fields": {
                        "repo_id": self.model_repo_id,
                        "checkpoint_name": self.checkpoint_name,
                        "device": self._get_requested_device(),
                    },
                },
            )

            try:
                tribe_module = importlib.import_module("tribev2")
                model_cls = getattr(tribe_module, "TribeModel")
                requested_device = self._get_requested_device()
                model = model_cls.from_pretrained(
                    self.model_repo_id,
                    checkpoint_name=self.checkpoint_name,
                    cache_folder=str(self.cache_folder),
                    cluster=self.feature_cluster,
                    device=requested_device,
                    config_update=self._build_runtime_config_update(requested_device),
                )
            except Exception as exc:
                raise ConfigurationAppError(
                    "Failed to load TRIBE v2 from the configured checkpoint. "
                    "Check model availability, Hugging Face access, and runtime dependencies."
                ) from exc

            self.__class__._shared_module = tribe_module
            self.__class__._shared_model = model
            self.__class__._resolved_device = self._resolve_loaded_device(model)
            logger.info(
                "Shared TRIBE model initialized.",
                extra={
                    "event": "tribe_model_init_finished",
                    "extra_fields": {
                        "repo_id": self.model_repo_id,
                        "checkpoint_name": self.checkpoint_name,
                        "resolved_device": self._get_resolved_device(),
                        "duration_seconds": round(time.perf_counter() - load_started_at, 3),
                    },
                },
            )

    def infer(self, payload: TribeRuntimeInput) -> TribeRuntimeOutput:
        self.assert_supported_modality(payload.modality)
        self.load()

        model = self._get_loaded_model()
        temp_text_path: Path | None = None

        try:
            inference_started_at = time.perf_counter()
            if payload.modality == "video":
                events = self._prepare_video_events(model=model, payload=payload)
            elif payload.modality == "audio":
                events = self._prepare_audio_events(model=model, payload=payload)
            elif payload.modality == "text":
                events, temp_text_path = self._prepare_text_events(model=model, payload=payload)
            else:  # pragma: no cover - guarded by assert_supported_modality
                raise UnsupportedModalityAppError(f"Unsupported TRIBE modality: {payload.modality}")

            predictions, segments = self._predict(model=model, events=events)
            output = self._postprocess_predictions(
                payload=payload,
                events=events,
                predictions=predictions,
                segments=segments,
            )
            logger.info(
                "TRIBE runtime inference completed.",
                extra={
                    "event": "tribe_runtime_infer_finished",
                    "extra_fields": {
                        "modality": payload.modality,
                        "duration_seconds": round(time.perf_counter() - inference_started_at, 3),
                        "segment_count": int(output.reduced_feature_vector.get("segment_count", 0)),
                    },
                },
            )
            return output
        finally:
            if temp_text_path is not None and temp_text_path.exists():
                temp_text_path.unlink(missing_ok=True)

    def _prepare_video_events(self, *, model: Any, payload: TribeRuntimeInput) -> Any:
        path = self._require_local_file(payload.local_path, suffix_hint="video")
        return model.get_events_dataframe(video_path=str(path))

    def _prepare_audio_events(self, *, model: Any, payload: TribeRuntimeInput) -> Any:
        path = self._require_local_file(payload.local_path, suffix_hint="audio")
        return model.get_events_dataframe(audio_path=str(path))

    def _prepare_text_events(self, *, model: Any, payload: TribeRuntimeInput) -> tuple[Any, Path | None]:
        if payload.raw_text and payload.raw_text.strip():
            processed = self.text_preprocessor.preprocess(payload.raw_text)
            tmp = tempfile.NamedTemporaryFile("w", suffix=".txt", encoding="utf-8", delete=False)
            with tmp:
                tmp.write(processed.normalized_text)
            temp_path = Path(tmp.name)
            return model.get_events_dataframe(text_path=str(temp_path)), temp_path

        path = self._require_local_file(payload.local_path, suffix_hint="text")
        return model.get_events_dataframe(text_path=str(path)), None

    def _predict(self, *, model: Any, events: Any) -> tuple[np.ndarray, list[Any]]:
        try:
            predictions, segments = model.predict(events=events)
        except Exception as exc:
            raise ValidationAppError(
                f"TRIBE v2 prediction failed for the prepared events payload: {exc}"
            ) from exc

        array = np.asarray(predictions, dtype=np.float32)
        if array.ndim != 2 or array.shape[0] == 0 or array.shape[1] == 0:
            raise ValidationAppError("TRIBE v2 returned an empty prediction tensor.")
        return array, list(segments)

    def _postprocess_predictions(
        self,
        *,
        payload: TribeRuntimeInput,
        events: Any,
        predictions: np.ndarray,
        segments: list[Any],
    ) -> TribeRuntimeOutput:
        abs_predictions = np.abs(predictions)
        segment_mean_activation = abs_predictions.mean(axis=1)
        segment_peak_activation = abs_predictions.max(axis=1)
        vertex_count = int(predictions.shape[1])
        segment_count = int(predictions.shape[0])
        midpoint = max(1, vertex_count // 2)
        left_mean = abs_predictions[:, :midpoint].mean(axis=1)
        right_mean = abs_predictions[:, midpoint:].mean(axis=1)
        hemisphere_balance = 1.0 - np.abs(left_mean - right_mean) / (left_mean + right_mean + 1e-6)

        event_summary = self._summarize_events(events)
        segment_features = self._build_segment_features(
            segments=segments,
            segment_mean_activation=segment_mean_activation,
            segment_peak_activation=segment_peak_activation,
            hemisphere_balance=hemisphere_balance,
        )
        reduced_feature_vector = self._build_reduced_feature_vector(
            event_summary=event_summary,
            segment_mean_activation=segment_mean_activation,
            segment_peak_activation=segment_peak_activation,
            hemisphere_balance=hemisphere_balance,
            segment_features=segment_features,
        )
        region_activation_summary = self._build_region_activation_summary(
            abs_predictions=abs_predictions,
            left_mean=left_mean,
            right_mean=right_mean,
        )

        raw_brain_response_summary = {
            "foundation_model": {
                "repo_id": self.model_repo_id,
                "checkpoint_name": self.checkpoint_name,
                "mesh": "fsaverage5",
                "subject_basis": "average_subject",
                "device": self._get_resolved_device(),
            },
            "input_modality": payload.modality,
            "event_summary": event_summary,
            "prediction_summary": {
                "segment_count": segment_count,
                "vertex_count": vertex_count,
                "global_mean_abs_activation": round(float(abs_predictions.mean()), 6),
                "global_peak_abs_activation": round(float(abs_predictions.max()), 6),
                "global_std_abs_activation": round(float(abs_predictions.std()), 6),
            },
        }

        provenance_json = {
            "foundation_model": {
                "provider": "Meta",
                "package": "tribev2",
                "repo_id": self.model_repo_id,
                "checkpoint_name": self.checkpoint_name,
                "device": self._get_resolved_device(),
            },
            "official_api_path": {
                "from_pretrained": True,
                "get_events_dataframe": True,
                "predict": True,
            },
            "contract_notes": [
                "The public TRIBE v2 API predicts average-subject responses on the fsaverage5 cortical mesh.",
                "This service stores only summaries and derived internal features, not raw cortical mesh predictions.",
                "Business-facing scores are computed downstream by NeuroScoringService and are not direct TRIBE outputs.",
            ],
        }

        return TribeRuntimeOutput(
            raw_brain_response_uri=None,
            raw_brain_response_summary=raw_brain_response_summary,
            reduced_feature_vector=reduced_feature_vector,
            region_activation_summary=region_activation_summary,
            provenance_json=provenance_json,
        )

    def _build_reduced_feature_vector(
        self,
        *,
        event_summary: dict[str, Any],
        segment_mean_activation: np.ndarray,
        segment_peak_activation: np.ndarray,
        hemisphere_balance: np.ndarray,
        segment_features: list[dict[str, Any]],
    ) -> dict[str, Any]:
        mean_activation = float(segment_mean_activation.mean())
        peak_activation = float(segment_peak_activation.max())
        p95_activation = float(np.quantile(segment_peak_activation, 0.95))
        temporal_delta = np.abs(np.diff(segment_mean_activation)) if len(segment_mean_activation) > 1 else np.array([0.0])

        event_types = event_summary.get("event_types", {})
        segment_count = max(1, len(segment_features))
        event_rows = int(event_summary.get("row_count", 0))
        word_like_count = int(
            sum(count for name, count in event_types.items() if "word" in str(name).lower())
        )
        sentence_like_count = int(
            sum(count for name, count in event_types.items() if "sentence" in str(name).lower())
        )
        has_audio = int(any("audio" in str(name).lower() for name in event_types))
        has_video = int(any("video" in str(name).lower() for name in event_types))

        derived_neural_engagement_signal = self._clip01(mean_activation / (p95_activation + 1e-6))
        derived_peak_focus_signal = self._clip01(p95_activation / (peak_activation + 1e-6))
        derived_temporal_dynamics_signal = self._clip01(float(temporal_delta.mean()) / (mean_activation + 1e-6))
        derived_temporal_consistency_signal = self._clip01(
            1.0 - float(segment_mean_activation.std()) / (mean_activation + 1e-6)
        )
        derived_linguistic_load_signal = self._clip01(0.35 + (word_like_count / max(segment_count * 18, 1)))
        derived_context_density_signal = self._clip01(event_rows / max(segment_count * 8, 1))
        derived_hemisphere_balance_signal = self._clip01(float(hemisphere_balance.mean()))
        derived_audio_language_mix_signal = self._clip01(
            (0.5 if word_like_count > 0 or sentence_like_count > 0 else 0.0)
            + (0.3 if has_audio else 0.0)
            + (0.2 if has_video else 0.0)
        )

        return {
            "feature_contract_version": "tribe_v2_business_bridge_v1",
            "global_abs_mean_activation": round(mean_activation, 6),
            "global_abs_peak_activation": round(peak_activation, 6),
            "segment_count": segment_count,
            "event_row_count": event_rows,
            "derived_neural_engagement_signal": round(derived_neural_engagement_signal, 6),
            "derived_peak_focus_signal": round(derived_peak_focus_signal, 6),
            "derived_temporal_dynamics_signal": round(derived_temporal_dynamics_signal, 6),
            "derived_temporal_consistency_signal": round(derived_temporal_consistency_signal, 6),
            "derived_linguistic_load_signal": round(derived_linguistic_load_signal, 6),
            "derived_context_density_signal": round(derived_context_density_signal, 6),
            "derived_hemisphere_balance_signal": round(derived_hemisphere_balance_signal, 6),
            "derived_audio_language_mix_signal": round(derived_audio_language_mix_signal, 6),
            "segment_features": segment_features,
        }

    def _build_region_activation_summary(
        self,
        *,
        abs_predictions: np.ndarray,
        left_mean: np.ndarray,
        right_mean: np.ndarray,
    ) -> dict[str, Any]:
        summary: dict[str, Any] = {
            "derivation": (
                "Derived from aggregate fsaverage5 vertex predictions. "
                "These summaries are not exposed as direct public TRIBE semantic outputs."
            ),
            "mesh": "fsaverage5",
            "hemisphere_summary": {
                "left_mean_abs_activation": round(float(left_mean.mean()), 6),
                "right_mean_abs_activation": round(float(right_mean.mean()), 6),
                "hemisphere_balance_signal": round(
                    self._clip01(1.0 - abs(float(left_mean.mean()) - float(right_mean.mean())) / (float(left_mean.mean() + right_mean.mean()) + 1e-6)),
                    6,
                ),
            },
            "top_rois": [],
            "roi_summary_enabled": self.enable_roi_summary,
        }

        if not self.enable_roi_summary:
            return summary

        roi_items = self._build_roi_summary(abs_predictions.mean(axis=0))
        summary["top_rois"] = roi_items
        if not roi_items:
            summary["roi_summary_enabled"] = False
            summary["roi_summary_warning"] = "ROI summarization could not be derived from the installed TRIBE dependencies."
        return summary

    def _build_roi_summary(self, averaged_prediction: np.ndarray) -> list[dict[str, Any]]:
        try:
            utils_module = importlib.import_module("tribev2.utils")
            labels = list(utils_module.get_topk_rois(averaged_prediction, hemi="both", mesh="fsaverage5", k=8))
            roi_values = np.asarray(utils_module.summarize_by_roi(averaged_prediction, hemi="both", mesh="fsaverage5"))
            label_map = {
                label: round(float(value), 6)
                for label, value in zip(utils_module.get_hcp_labels(mesh="fsaverage5", hemi="both").keys(), roi_values, strict=False)
            }
            return [
                {
                    "roi": str(label),
                    "mean_activation": label_map.get(str(label)),
                    "derivation": "Derived from the public TRIBE fsaverage5 cortical prediction via HCP ROI aggregation.",
                }
                for label in labels
            ]
        except Exception:
            return []

    def _build_segment_features(
        self,
        *,
        segments: list[Any],
        segment_mean_activation: np.ndarray,
        segment_peak_activation: np.ndarray,
        hemisphere_balance: np.ndarray,
    ) -> list[dict[str, Any]]:
        mean_baseline = float(segment_mean_activation.mean())
        peak_baseline = float(segment_peak_activation.max())
        temporal_delta = np.abs(np.diff(segment_mean_activation, prepend=segment_mean_activation[:1]))

        items: list[dict[str, Any]] = []
        for index, segment in enumerate(segments):
            start_seconds = self._coerce_float(getattr(segment, "start", None), default=float(index))
            duration_seconds = self._resolve_segment_duration(segment)
            items.append(
                {
                    "segment_index": index,
                    "start_ms": int(round(start_seconds * 1000)),
                    "duration_ms": int(round(duration_seconds * 1000)),
                    "event_count": self._resolve_segment_event_count(segment),
                    "event_types": self._resolve_segment_event_types(segment),
                    "mean_abs_activation": round(float(segment_mean_activation[index]), 6),
                    "peak_abs_activation": round(float(segment_peak_activation[index]), 6),
                    "engagement_signal": round(
                        self._clip01(float(segment_mean_activation[index]) / (mean_baseline * 1.35 + 1e-6)),
                        6,
                    ),
                    "peak_focus_signal": round(
                        self._clip01(float(segment_peak_activation[index]) / (peak_baseline + 1e-6)),
                        6,
                    ),
                    "temporal_change_signal": round(
                        self._clip01(float(temporal_delta[index]) / (mean_baseline + 1e-6)),
                        6,
                    ),
                    "consistency_signal": round(
                        self._clip01(1.0 - abs(float(segment_mean_activation[index]) - mean_baseline) / (mean_baseline + 1e-6)),
                        6,
                    ),
                    "hemisphere_balance_signal": round(self._clip01(float(hemisphere_balance[index])), 6),
                }
            )
        return items

    def _summarize_events(self, events: Any) -> dict[str, Any]:
        row_count = len(events) if hasattr(events, "__len__") else 0
        event_types: dict[str, int] = {}
        start_values: list[float] = []
        duration_values: list[float] = []

        if hasattr(events, "columns") and "type" in getattr(events, "columns", []):
            try:
                counts = events["type"].value_counts().to_dict()
                event_types = {str(key): int(value) for key, value in counts.items()}
            except Exception:
                event_types = {}
            for field_name, bucket in (("start", start_values), ("duration", duration_values), ("stop", duration_values)):
                if field_name in getattr(events, "columns", []):
                    values = [self._coerce_float(value, default=0.0) for value in events[field_name].tolist()]
                    if field_name == "stop":
                        if values:
                            duration_values.extend(values)
                    else:
                        bucket.extend(values)
        elif isinstance(events, list):
            counts = Counter(str(item.get("type", "unknown")) for item in events if isinstance(item, dict))
            event_types = {key: int(value) for key, value in counts.items()}
            for item in events:
                if not isinstance(item, dict):
                    continue
                if item.get("start") is not None:
                    start_values.append(self._coerce_float(item.get("start"), default=0.0))
                if item.get("duration") is not None:
                    duration_values.append(self._coerce_float(item.get("duration"), default=0.0))

        return {
            "row_count": int(row_count),
            "event_types": event_types,
            "start_time_ms": int(round(min(start_values) * 1000)) if start_values else 0,
            "duration_ms_estimate": int(round(max(duration_values) * 1000)) if duration_values else None,
        }

    def _authenticate_huggingface(self) -> None:
        if not self.hf_token:
            return

        try:
            hub_module = importlib.import_module("huggingface_hub")
            login = getattr(hub_module, "login", None)
            if callable(login):
                login(token=self.hf_token, add_to_git_credential=False)
        except Exception as exc:
            raise ConfigurationAppError("Configured Hugging Face credentials could not be applied.") from exc

    def _get_loaded_model(self) -> Any:
        model = self.__class__._shared_model
        if model is None:
            raise ConfigurationAppError("TRIBE runtime was used before load() completed.")
        return model

    def _get_resolved_device(self) -> str:
        return self.__class__._resolved_device or self._get_requested_device()

    def _resolve_loaded_device(self, model: Any) -> str:
        inner_model = getattr(model, "_model", None)
        device = getattr(inner_model, "device", None)
        return str(device) if device is not None else self._get_requested_device()

    def _get_requested_device(self) -> str:
        requested = (self.device or "auto").strip().lower()
        if requested != "auto":
            return requested

        try:
            import torch
        except Exception:
            return "cpu"

        return "cuda" if torch.cuda.is_available() else "cpu"

    def _build_runtime_config_update(self, requested_device: str) -> dict[str, Any]:
        config_update: dict[str, Any] = {
            "data.text_feature.device": requested_device,
            "data.audio_feature.device": requested_device,
            "data.image_feature.image.device": requested_device,
            "data.video_feature.image.device": requested_device,
        }

        if settings.tribe_video_feature_frequency_hz is not None:
            config_update["data.video_feature.frequency"] = settings.tribe_video_feature_frequency_hz
        if settings.tribe_video_max_imsize is not None:
            config_update["data.video_feature.max_imsize"] = settings.tribe_video_max_imsize

        return config_update

    def _require_local_file(self, local_path: str | None, *, suffix_hint: str) -> Path:
        if not local_path:
            raise ValidationAppError(f"A local {suffix_hint} file path is required for TRIBE inference.")
        path = Path(local_path)
        if not path.is_file():
            raise ValidationAppError(f"Local file for TRIBE inference does not exist: {path}")
        return path

    def _resolve_segment_duration(self, segment: Any) -> float:
        duration = getattr(segment, "duration", None)
        if duration is not None:
            return max(0.0, self._coerce_float(duration, default=0.0))

        start = getattr(segment, "start", None)
        stop = getattr(segment, "stop", None)
        if start is not None and stop is not None:
            return max(0.0, self._coerce_float(stop, default=0.0) - self._coerce_float(start, default=0.0))
        return 0.0

    def _resolve_segment_event_count(self, segment: Any) -> int:
        events = getattr(segment, "ns_events", None)
        if events is None:
            return 0
        try:
            return len(events)
        except TypeError:
            return 0

    def _resolve_segment_event_types(self, segment: Any) -> list[str]:
        events = getattr(segment, "ns_events", None)
        if events is None:
            return []
        names: set[str] = set()
        for event in events:
            event_type = getattr(event, "type", None) or getattr(event, "name", None)
            if event_type is not None:
                names.add(str(event_type))
        return sorted(names)

    @staticmethod
    def _clip01(value: float) -> float:
        return max(0.0, min(1.0, float(value)))

    @staticmethod
    def _coerce_float(value: Any, *, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default


_shared_runtime: TribeRuntime | None = None


def get_shared_tribe_runtime() -> TribeRuntime:
    global _shared_runtime
    if _shared_runtime is None:
        _shared_runtime = TribeRuntime()
    return _shared_runtime
