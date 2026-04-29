from __future__ import annotations

import importlib
import inspect
import io
import gc
import os
import re
import shutil
import tempfile
import time
import warnings
from collections import Counter, deque
from contextlib import ExitStack, contextmanager, redirect_stderr, redirect_stdout
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
from backend.core.logging import duration_ms, get_logger, log_event, log_exception
from backend.services.text_preprocess import TextPreprocessService

logger = get_logger(__name__)

# tribev2's TribeModel.from_pretrained does not accept HF ``token`` / legacy ``use_auth_token``.
# Some hub helpers or wrappers inject those kwargs; strip them once on the live class.
_TRIBE_FROM_PRETRAINED_PATCH_ATTR = "_neuromarketer_strip_hf_token_kwargs_applied"


@contextmanager
def _disable_tqdm():
    old = os.environ.get("TQDM_DISABLE")
    os.environ["TQDM_DISABLE"] = "1"
    try:
        yield
    finally:
        if old is None:
            os.environ.pop("TQDM_DISABLE", None)
        else:
            os.environ["TQDM_DISABLE"] = old


@contextmanager
def _suppress_progress_output():
    # Some TRIBE/neuralset paths invoke tqdm with implicit stdio writes.
    # In daemonized Celery workers stdout/stderr can become invalid pipes,
    # so force in-memory streams during inference prep/predict.
    with ExitStack() as stack:
        stack.enter_context(_disable_tqdm())
        stack.enter_context(redirect_stdout(io.StringIO()))
        stack.enter_context(redirect_stderr(io.StringIO()))
        yield


def _ensure_tribe_model_from_pretrained_strips_hub_kwargs() -> None:
    """Monkey-patch tribev2 so ``from_pretrained`` ignores token-style kwargs Hub stacks may inject."""
    demo_utils = importlib.import_module("tribev2.demo_utils")
    tribe_model = getattr(demo_utils, "TribeModel", None)
    if tribe_model is None:
        return
    if getattr(tribe_model, _TRIBE_FROM_PRETRAINED_PATCH_ATTR, False):
        return

    descriptor = inspect.getattr_static(tribe_model, "from_pretrained")
    if not isinstance(descriptor, classmethod):
        return
    underlying = descriptor.__func__

    @classmethod  # type: ignore[misc]
    def from_pretrained_compat(
        cls: Any,
        checkpoint_dir: str | Path,
        checkpoint_name: str = "best.ckpt",
        cache_folder: str | Path | None = None,
        cluster: str | None = None,
        device: str = "auto",
        config_update: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        kwargs.pop("token", None)
        kwargs.pop("use_auth_token", None)
        if kwargs:
            names = ", ".join(sorted(kwargs))
            raise TypeError(
                "TribeModel.from_pretrained does not accept "
                f"{names!s}. Use HF_TOKEN in the environment."
            )
        return underlying(
            cls,
            checkpoint_dir,
            checkpoint_name=checkpoint_name,
            cache_folder=cache_folder,
            cluster=cluster,
            device=device,
            config_update=config_update,
        )

    setattr(tribe_model, _TRIBE_FROM_PRETRAINED_PATCH_ATTR, True)
    tribe_model.from_pretrained = from_pretrained_compat  # type: ignore[method-assign]


warnings.filterwarnings(
    "ignore",
    message=r"LabelEncoder: event_types has not been set.*",
    category=UserWarning,
    module=r"neuralset\.extractors\.base",
)

warnings.filterwarnings(
    "ignore",
    message=r"Missing events will be encoded using the default all-zero value.*",
    category=UserWarning,
    module=r"neuralset\.extractors\.base",
)

warnings.filterwarnings(
    "ignore",
    message=r".*torch\.cuda\.amp\.autocast.*deprecated.*",
    category=FutureWarning,
)

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
    _local_hf_model_path_patch_applied: bool = False
    _cuda_allocator_env_configured: bool = False

    def __init__(self) -> None:
        self.model_repo_id = settings.tribe_model_repo_id
        self.checkpoint_name = settings.tribe_checkpoint_name
        self.cache_folder = self._resolve_cache_folder(
            Path(settings.tribe_cache_folder).expanduser()
        )
        self.device = settings.tribe_device
        self.text_feature_model_name = self._resolve_text_feature_model_name(
            settings.tribe_text_feature_model_name
        )
        self.feature_cluster = settings.tribe_feature_cluster
        self.hf_token = settings.hf_token
        self.enable_roi_summary = settings.tribe_enable_roi_summary
        self.gc_collect_after_inference = settings.tribe_gc_collect_after_inference
        self.cuda_empty_cache_before_inference = settings.tribe_cuda_empty_cache_before_inference
        self.cuda_empty_cache_after_inference = settings.tribe_cuda_empty_cache_after_inference
        self.cuda_alloc_expandable_segments = settings.tribe_cuda_alloc_expandable_segments
        self.text_preprocessor = TextPreprocessService()
        self.model_name = self.model_repo_id
        self._configure_cuda_allocator_env_if_enabled()

    def _project_root(self) -> Path:
        return Path(__file__).resolve().parents[2]

    def _resolve_text_feature_model_name(self, configured_name: str) -> str:
        resolved_local_path = self._resolve_local_model_path(configured_name)
        if resolved_local_path is not None:
            return str(resolved_local_path)

        default_remote_model = "microsoft/Phi-3-mini-4k-instruct"
        default_local_model = self._project_root() / "models" / "phi3-mini-4k-instruct"
        if configured_name.strip() == default_remote_model and default_local_model.is_dir():
            resolved_path = default_local_model.resolve()
            log_event(
                logger,
                "tribe_text_feature_model_local_fallback",
                configured_name=configured_name,
                resolved_path=str(resolved_path),
                status="fallback",
            )
            return str(resolved_path)

        return configured_name

    def _resolve_local_model_path(self, model_name: str | None) -> Path | None:
        if not model_name or not model_name.strip():
            return None

        configured_path = Path(model_name).expanduser()
        candidates = [configured_path]
        if not configured_path.is_absolute():
            candidates.append(self._project_root() / configured_path)

        for candidate in candidates:
            if candidate.is_dir():
                return candidate.resolve()

        return None

    def _resolve_project_relative_path(self, configured_path: Path) -> Path:
        if configured_path.is_absolute():
            return configured_path.resolve(strict=False)
        return (self._project_root() / configured_path).resolve(strict=False)

    def _resolve_cache_folder(self, configured_path: Path) -> Path:
        candidates = self._candidate_cache_folders(configured_path)
        normalized_configured = self._resolve_project_relative_path(configured_path)
        errors: list[str] = []

        for candidate in candidates:
            try:
                candidate.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                errors.append(f"{candidate}: {exc}")
                continue

            if os.access(candidate, os.W_OK):
                if candidate != normalized_configured:
                    log_event(
                        logger,
                        "tribe_cache_folder_fallback",
                        level="warning",
                        configured_path=str(configured_path),
                        resolved_path=str(candidate),
                        status="fallback",
                    )
                return candidate

            errors.append(f"{candidate}: not writable")

        raise ConfigurationAppError(
            "TRIBE cache folder could not be initialized. " + "; ".join(errors)
        )

    def _candidate_cache_folders(self, configured_path: Path) -> list[Path]:
        normalized_configured = self._resolve_project_relative_path(configured_path)
        project_cache = (self._project_root() / "cache" / "tribev2").resolve(strict=False)
        temp_cache = (Path(tempfile.gettempdir()) / "neuromarketer" / "tribev2").resolve(
            strict=False
        )
        candidates = [normalized_configured, project_cache, temp_cache]
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

        missing_binaries = [
            name for name in ("uvx", "ffmpeg", "ffprobe") if shutil.which(name) is None
        ]
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
            self._enable_local_huggingface_model_paths()
            self._authenticate_huggingface()
            load_started_at = time.perf_counter()
            log_event(
                logger,
                "tribe_runtime_load_started",
                repo_id=self.model_repo_id,
                checkpoint_name=self.checkpoint_name,
                requested_device=self._get_requested_device(),
                status="started",
            )

            try:
                tribe_module = importlib.import_module("tribev2")
                model_cls = tribe_module.TribeModel
                _ensure_tribe_model_from_pretrained_strips_hub_kwargs()
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
                load_finished_at = time.perf_counter()
                log_exception(
                    logger,
                    "tribe_runtime_load_failed",
                    exc,
                    repo_id=self.model_repo_id,
                    checkpoint_name=self.checkpoint_name,
                    requested_device=self._get_requested_device(),
                    duration_ms=duration_ms(load_started_at, load_finished_at),
                    status="failed",
                )
                raise ConfigurationAppError(self._format_load_error(exc)) from exc

            self.__class__._shared_module = tribe_module
            self.__class__._shared_model = model
            self.__class__._resolved_device = self._resolve_loaded_device(model)
            load_finished_at = time.perf_counter()
            log_event(
                logger,
                "tribe_runtime_loaded",
                repo_id=self.model_repo_id,
                checkpoint_name=self.checkpoint_name,
                resolved_device=self._get_resolved_device(),
                duration_ms=duration_ms(load_started_at, load_finished_at),
                status="loaded",
            )

    def infer(self, payload: TribeRuntimeInput) -> TribeRuntimeOutput:
        self.assert_supported_modality(payload.modality)
        self.load()

        model = self._get_loaded_model()
        self._coerce_dataloader_workers_zero(model)
        temp_text_path: Path | None = None
        events: Any | None = None
        predictions: np.ndarray | None = None
        segments: list[Any] | None = None


        try:
            if self.cuda_empty_cache_before_inference:
                self._release_cuda_memory_best_effort()
            if payload.modality == "video":
                events = self._prepare_video_events(model=model, payload=payload)
            elif payload.modality == "audio":
                events = self._prepare_audio_events(model=model, payload=payload)
            elif payload.modality == "text":
                events, temp_text_path = self._prepare_text_events(model=model, payload=payload)
            else:  # pragma: no cover - guarded by assert_supported_modality
                raise UnsupportedModalityAppError(f"Unsupported TRIBE modality: {payload.modality}")

            predictions, segments = self._predict_with_fallback(
                model=model,
                events=events,
                payload=payload,
            )
            return self._postprocess_predictions(
                payload=payload,
                events=events,
                predictions=predictions,
                segments=segments,
            )

        finally:
            if temp_text_path is not None and temp_text_path.exists():
                temp_text_path.unlink(missing_ok=True)
            del events
            del predictions
            del segments
            self._cleanup_inference_memory()

    def _cleanup_inference_memory(self) -> None:
        if self.gc_collect_after_inference:
            gc.collect()
        if self.cuda_empty_cache_after_inference:
            self._release_cuda_memory_best_effort()

    def _configure_cuda_allocator_env_if_enabled(self) -> None:
        if not self.cuda_alloc_expandable_segments:
            return
        if self.__class__._cuda_allocator_env_configured:
            return
        self.__class__._cuda_allocator_env_configured = True

        current = os.environ.get("PYTORCH_CUDA_ALLOC_CONF", "").strip()
        if "expandable_segments" in current:
            return
        next_value = (
            "expandable_segments:True"
            if not current
            else f"{current},expandable_segments:True"
        )
        os.environ["PYTORCH_CUDA_ALLOC_CONF"] = next_value


    def _prepare_video_events(self, *, model: Any, payload: TribeRuntimeInput) -> Any:
        path = self._require_local_file(payload.local_path, suffix_hint="video")
        with _suppress_progress_output():
            return model.get_events_dataframe(video_path=str(path))

    def _prepare_audio_events(self, *, model: Any, payload: TribeRuntimeInput) -> Any:
        path = self._require_local_file(payload.local_path, suffix_hint="audio")
        with _suppress_progress_output():
            return model.get_events_dataframe(audio_path=str(path))

    def _prepare_text_events(
        self, *, model: Any, payload: TribeRuntimeInput
    ) -> tuple[Any, Path | None]:
        raw_text = payload.raw_text
        if not raw_text or not raw_text.strip():
            path = self._require_local_file(payload.local_path, suffix_hint="text")
            raw_text = path.read_text(encoding="utf-8", errors="ignore")

        processed = self.text_preprocessor.preprocess(raw_text)
        return self._build_text_events_dataframe(processed.normalized_text), None


    def _build_text_events_dataframe(self, text: str) -> Any:
        try:
            import pandas as pd
            from neuralset.events.utils import standardize_events
        except Exception as exc:  # pragma: no cover - dependency resolution path
            raise DependencyAppError(
                "TRIBE text event preparation dependencies are not installed."
            ) from exc

        sentences = [
            sentence.strip()
            for sentence in re.split(r"(?<=[.!?])\s+", text.strip())
            if sentence.strip()
        ]
        if not sentences:
            sentences = [text.strip()]

        rows: list[dict[str, Any]] = []
        context_window: deque[str] = deque(maxlen=160)
        start_seconds = 0.0
        sequence_id = 0

        event_vocabulary = {
            "Word",
            "Sentence",
            "Pause",
            "CTA",
            "BrandMention",
            "NumberClaim",
            "UrgencyCue",
            "Question",
        }

        cta_terms = {
            "buy",
            "shop",
            "order",
            "subscribe",
            "signup",
            "sign",
            "join",
            "download",
            "try",
            "book",
            "start",
            "claim",
            "register",
            "learn",
        }
        urgency_terms = {
            "now",
            "today",
            "limited",
            "hurry",
            "urgent",
            "soon",
            "deadline",
            "last",
            "exclusive",
            "only",
        }

        for sentence_index, sentence in enumerate(sentences):
            sentence_tokens = [
                token for token in re.findall(r"(?u)\b[\w'-]+\b", sentence) if token.strip()
            ]
            if not sentence_tokens:
                continue

            sentence_start = start_seconds
            sentence_duration = max(
                0.75,
                min(8.0, sum(max(0.18, min(0.75, len(token) * 0.045)) for token in sentence_tokens)),
            )

            rows.append(
                {
                    "type": "Sentence",
                    "event_type": "Sentence",
                    "text": sentence,
                    "context": " ".join(context_window) or sentence,
                    "start": round(sentence_start, 6),
                    "duration": round(sentence_duration, 6),
                    "timeline": "default",
                    "subject": "default",
                    "sequence_id": sequence_id,
                    "sentence_index": sentence_index,
                    "synthetic": True,
                }
            )
            sequence_id += 1

            if sentence.endswith("?"):
                rows.append(
                    {
                        "type": "Question",
                        "event_type": "Question",
                        "text": sentence,
                        "context": sentence,
                        "start": round(sentence_start, 6),
                        "duration": round(min(sentence_duration, 1.5), 6),
                        "timeline": "default",
                        "subject": "default",
                        "sequence_id": sequence_id,
                        "sentence_index": sentence_index,
                        "synthetic": True,
                    }
                )
                sequence_id += 1

            for token in sentence_tokens:
                normalized = token.strip().lower()
                context_window.append(token)
                duration_seconds = max(0.18, min(0.75, len(token) * 0.045))

                rows.append(
                    {
                        "type": "Word",
                        "event_type": "Word",
                        "text": token,
                        "context": " ".join(context_window),
                        "start": round(start_seconds, 6),
                        "duration": round(duration_seconds, 6),
                        "timeline": "default",
                        "subject": "default",
                        "sequence_id": sequence_id,
                        "sentence_index": sentence_index,
                        "synthetic": True,
                    }
                )
                sequence_id += 1

                if normalized in cta_terms:
                    rows.append(
                        {
                            "type": "CTA",
                            "event_type": "CTA",
                            "text": token,
                            "context": " ".join(context_window),
                            "start": round(start_seconds, 6),
                            "duration": round(duration_seconds, 6),
                            "timeline": "default",
                            "subject": "default",
                            "sequence_id": sequence_id,
                            "sentence_index": sentence_index,
                            "synthetic": True,
                        }
                    )
                    sequence_id += 1

                if normalized in urgency_terms:
                    rows.append(
                        {
                            "type": "UrgencyCue",
                            "event_type": "UrgencyCue",
                            "text": token,
                            "context": " ".join(context_window),
                            "start": round(start_seconds, 6),
                            "duration": round(duration_seconds, 6),
                            "timeline": "default",
                            "subject": "default",
                            "sequence_id": sequence_id,
                            "sentence_index": sentence_index,
                            "synthetic": True,
                        }
                    )
                    sequence_id += 1

                if any(char.isdigit() for char in token):
                    rows.append(
                        {
                            "type": "NumberClaim",
                            "event_type": "NumberClaim",
                            "text": token,
                            "context": " ".join(context_window),
                            "start": round(start_seconds, 6),
                            "duration": round(duration_seconds, 6),
                            "timeline": "default",
                            "subject": "default",
                            "sequence_id": sequence_id,
                            "sentence_index": sentence_index,
                            "synthetic": True,
                        }
                    )
                    sequence_id += 1

                if token[:1].isupper() and len(token) > 2 and sentence_tokens.index(token) != 0:
                    rows.append(
                        {
                            "type": "BrandMention",
                            "event_type": "BrandMention",
                            "text": token,
                            "context": " ".join(context_window),
                            "start": round(start_seconds, 6),
                            "duration": round(duration_seconds, 6),
                            "timeline": "default",
                            "subject": "default",
                            "sequence_id": sequence_id,
                            "sentence_index": sentence_index,
                            "synthetic": True,
                        }
                    )
                    sequence_id += 1

                start_seconds += duration_seconds

            if sentence_index < len(sentences) - 1:
                pause_duration = 0.35
                rows.append(
                    {
                        "type": "Pause",
                        "event_type": "Pause",
                        "text": "",
                        "context": " ".join(context_window),
                        "start": round(start_seconds, 6),
                        "duration": pause_duration,
                        "timeline": "default",
                        "subject": "default",
                        "sequence_id": sequence_id,
                        "sentence_index": sentence_index,
                        "synthetic": True,
                    }
                )
                sequence_id += 1
                start_seconds += pause_duration

        if not rows:
            raise ValidationAppError("TRIBE text inference requires at least one readable word.")

        existing_types = {row["type"] for row in rows}

        for evt in event_vocabulary:
            if evt not in existing_types:
                rows.append({
                    "type": evt,
                    "event_type": evt,
                    "text": "",
                    "context": "",
                    "start": round(start_seconds, 6),
                    "duration": 0.001,
                    "timeline": "default",
                    "subject": "default",
                    "sequence_id": sequence_id,
                    "sentence_index": -1,
                    "synthetic": True,
                    "placeholder": True,
                })
                sequence_id += 1
                start_seconds += 0.001

        events = pd.DataFrame(rows).sort_values(["start", "sequence_id"]).reset_index(drop=True)
        events.attrs["event_types"] = sorted(event_vocabulary)
        events.attrs["synthetic_event_pipeline"] = "neuromarketer_text_v2"

        return standardize_events(events)


    @staticmethod
    def _coerce_dataloader_workers_zero(model: Any) -> None:
        visited: set[int] = set()
        stack: list[Any] = [model]
        while stack:
            obj = stack.pop()
            if obj is None:
                continue
            oid = id(obj)
            if oid in visited:
                continue
            visited.add(oid)
            if hasattr(obj, "num_workers"):
                try:
                    current = getattr(obj, "num_workers", None)
                    if isinstance(current, int) and current > 0:
                        setattr(obj, "num_workers", 0)
                except Exception:
                    pass
            for name in (
                "data",
                "_model",
                "model",
                "datamodule",
                "trainer",
                "hparams",
                "module",
                "cfg",
                "config",
            ):
                child = getattr(obj, name, None)
                if child is not None and id(child) not in visited:
                    stack.append(child)

    def _predict(self, *, model: Any, events: Any) -> tuple[np.ndarray, list[Any]]:
        self._coerce_dataloader_workers_zero(model)
        try:
            with _suppress_progress_output():
                predictions, segments = model.predict(events=events)
        except Exception as exc:
            raise ValidationAppError(self._format_prediction_error(exc)) from exc

        array = np.asarray(predictions, dtype=np.float32)
        if array.ndim != 2 or array.shape[0] == 0 or array.shape[1] == 0:
            raise ValidationAppError("TRIBE v2 returned an empty prediction tensor.")
        return array, list(segments)

    def _predict_with_fallback(
        self,
        *,
        model: Any,
        events: Any,
        payload: TribeRuntimeInput,
    ) -> tuple[np.ndarray, list[Any]]:
        try:
            return self._predict(model=model, events=events)
        except ValidationAppError as exc:
            if not self._should_retry_on_cpu_after_oom(exc):
                raise

            self._release_cuda_memory_best_effort()
            log_event(
                logger,
                "tribe_runtime_oom_cpu_retry_started",
                modality=payload.modality,
                configured_device=self._get_requested_device(),
                resolved_device=self._get_resolved_device(),
                status="retrying",
            )
            cpu_model = self._load_cpu_fallback_model()
            predictions, segments = self._predict(model=cpu_model, events=events)
            log_event(
                logger,
                "tribe_runtime_oom_cpu_retry_succeeded",
                modality=payload.modality,
                status="succeeded",
            )
            return predictions, segments

    def _should_retry_on_cpu_after_oom(self, exc: Exception) -> bool:
        requested_device = (self._get_requested_device() or "").lower()
        resolved_device = (self._get_resolved_device() or "").lower()
        if "cpu" in requested_device or "cpu" in resolved_device:
            return False
        message = str(exc).lower()
        return "cuda out of memory" in message or "cublas_status_alloc_failed" in message

    def _load_cpu_fallback_model(self) -> Any:
        tribe_module = self.__class__._shared_module or importlib.import_module("tribev2")
        model_cls = tribe_module.TribeModel
        _ensure_tribe_model_from_pretrained_strips_hub_kwargs()
        return model_cls.from_pretrained(
            self.model_repo_id,
            checkpoint_name=self.checkpoint_name,
            cache_folder=str(self.cache_folder),
            cluster=self.feature_cluster,
            device="cpu",
            config_update=self._build_runtime_config_update("cpu"),
        )

    def _release_cuda_memory_best_effort(self) -> None:
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.ipc_collect()
        except Exception:
            return

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
            "feature_extractors": {
                "text_feature_model_name": self.text_feature_model_name,
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
            "feature_extractors": {
                "text_feature_model_name": self.text_feature_model_name,
            },
            "official_api_path": {
                "from_pretrained": True,
                "get_events_dataframe": True,
                "predict": True,
            },
            "contract_notes": [
                "The public TRIBE v2 API predicts average-subject responses on the fsaverage5 cortical mesh.",
                "This service stores only summaries and derived internal features, not raw cortical mesh predictions.",
                "Business-facing scores are evaluated downstream by an LLM scoring layer and are not direct TRIBE outputs.",
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
        temporal_delta = (
            np.abs(np.diff(segment_mean_activation))
            if len(segment_mean_activation) > 1
            else np.array([0.0])
        )

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

        cta_count = int(sum(count for name, count in event_types.items() if "cta" in str(name).lower()))
        urgency_count = int(
            sum(count for name, count in event_types.items() if "urgency" in str(name).lower()))
        number_claim_count = int(
            sum(count for name, count in event_types.items() if "number" in str(name).lower()))
        brand_mention_count = int(
            sum(count for name, count in event_types.items() if "brand" in str(name).lower()))
        question_count = int(
            sum(count for name, count in event_types.items() if "question" in str(name).lower()))

        derived_neural_engagement_signal = self._clip01(mean_activation / (p95_activation + 1e-6))
        derived_peak_focus_signal = self._clip01(p95_activation / (peak_activation + 1e-6))
        derived_temporal_dynamics_signal = self._clip01(
            float(temporal_delta.mean()) / (mean_activation + 1e-6)
        )
        derived_temporal_consistency_signal = self._clip01(
            1.0 - float(segment_mean_activation.std()) / (mean_activation + 1e-6)
        )
        derived_linguistic_load_signal = self._clip01(
            0.35 + (word_like_count / max(segment_count * 18, 1))
        )
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
            "creative_cta_density_signal": round(self._clip01(cta_count / max(segment_count, 1)), 6),
            "creative_urgency_density_signal": round(self._clip01(urgency_count / max(segment_count, 1)), 6),
            "creative_specificity_signal": round(self._clip01((number_claim_count + brand_mention_count) / max(segment_count * 2, 1)),6,),
            "creative_question_signal": round(self._clip01(question_count / max(segment_count, 1)),6,),
            "event_type_distribution": event_types,
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
                    self._clip01(
                        1.0
                        - abs(float(left_mean.mean()) - float(right_mean.mean()))
                        / (float(left_mean.mean() + right_mean.mean()) + 1e-6)
                    ),
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
            summary["roi_summary_warning"] = (
                "ROI summarization could not be derived from the installed TRIBE dependencies."
            )
        return summary

    def _build_roi_summary(self, averaged_prediction: np.ndarray) -> list[dict[str, Any]]:
        try:
            utils_module = importlib.import_module("tribev2.utils")
            labels = list(
                utils_module.get_topk_rois(averaged_prediction, hemi="both", mesh="fsaverage5", k=8)
            )
            roi_values = np.asarray(
                utils_module.summarize_by_roi(averaged_prediction, hemi="both", mesh="fsaverage5")
            )
            label_map = {
                label: round(float(value), 6)
                for label, value in zip(
                    utils_module.get_hcp_labels(mesh="fsaverage5", hemi="both").keys(),
                    roi_values,
                    strict=False,
                )
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
        temporal_delta = np.abs(
            np.diff(segment_mean_activation, prepend=segment_mean_activation[:1])
        )

        items: list[dict[str, Any]] = []
        for index, segment in enumerate(segments):
            start_seconds = self._coerce_float(
                getattr(segment, "start", None), default=float(index)
            )
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
                        self._clip01(
                            float(segment_mean_activation[index]) / (mean_baseline * 1.35 + 1e-6)
                        ),
                        6,
                    ),
                    "peak_focus_signal": round(
                        self._clip01(
                            float(segment_peak_activation[index]) / (peak_baseline + 1e-6)
                        ),
                        6,
                    ),
                    "temporal_change_signal": round(
                        self._clip01(float(temporal_delta[index]) / (mean_baseline + 1e-6)),
                        6,
                    ),
                    "consistency_signal": round(
                        self._clip01(
                            1.0
                            - abs(float(segment_mean_activation[index]) - mean_baseline)
                            / (mean_baseline + 1e-6)
                        ),
                        6,
                    ),
                    "hemisphere_balance_signal": round(
                        self._clip01(float(hemisphere_balance[index])), 6
                    ),
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
            for field_name, bucket in (
                ("start", start_values),
                ("duration", duration_values),
                ("stop", duration_values),
            ):
                if field_name in getattr(events, "columns", []):
                    values = [
                        self._coerce_float(value, default=0.0)
                        for value in events[field_name].tolist()
                    ]
                    if field_name == "stop":
                        if values:
                            duration_values.extend(values)
                    else:
                        bucket.extend(values)
        elif isinstance(events, list):
            counts = Counter(
                str(item.get("type", "unknown")) for item in events if isinstance(item, dict)
            )
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
            "duration_ms_estimate": int(round(max(duration_values) * 1000))
            if duration_values
            else None,
        }

    def _authenticate_huggingface(self) -> None:
        if not self.hf_token:
            return

        os.environ["HF_TOKEN"] = self.hf_token


    @classmethod
    def _enable_local_huggingface_model_paths(cls) -> None:
        if cls._local_hf_model_path_patch_applied:
            return

        try:
            base_module = importlib.import_module("neuralset.extractors.base")
            mixin_cls = base_module.HuggingFaceMixin
        except Exception:
            return

        original_repo_exists = getattr(mixin_cls, "_neuromarketer_original_repo_exists", None)
        if original_repo_exists is None:
            original_repo_exists = mixin_cls.repo_exists
            mixin_cls._neuromarketer_original_repo_exists = original_repo_exists

        if getattr(mixin_cls, "_neuromarketer_local_path_patch_applied", False):
            cls._local_hf_model_path_patch_applied = True
            return

        def repo_exists_with_local_paths(mixin_self: Any) -> bool:
            model_name = str(getattr(mixin_self, "model_name", "") or "").strip()
            if model_name:
                configured_path = Path(model_name).expanduser()
                candidates = [configured_path]
                if not configured_path.is_absolute():
                    candidates.append(Path(__file__).resolve().parents[2] / configured_path)
                if any(candidate.is_dir() for candidate in candidates):
                    return True
            return original_repo_exists(mixin_self)

        mixin_cls.repo_exists = repo_exists_with_local_paths
        mixin_cls._neuromarketer_local_path_patch_applied = True
        cls._local_hf_model_path_patch_applied = True

    def _get_loaded_model(self) -> Any:
        model = self.__class__._shared_model
        if model is None:
            raise ConfigurationAppError("TRIBE runtime was used before load() completed.")
        return model

    def _get_resolved_device(self) -> str:
        return self.__class__._resolved_device or self._get_requested_device()

    def get_requested_device(self) -> str:
        return self._get_requested_device()

    def get_resolved_device(self) -> str:
        return self._get_resolved_device()

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
            "data.text_feature.model_name": self.text_feature_model_name,
            "data.text_feature.device": requested_device,
            "data.audio_feature.device": requested_device,
            "data.image_feature.image.device": requested_device,
            "data.video_feature.image.device": requested_device,
            # Celery / threadpool: daemon contexts cannot spawn DataLoader worker processes.
            "data.num_workers": 0,
        }

        if settings.tribe_video_feature_frequency_hz is not None:
            config_update["data.video_feature.frequency"] = (
                settings.tribe_video_feature_frequency_hz
            )
        if settings.tribe_video_max_imsize is not None:
            config_update["data.video_feature.max_imsize"] = settings.tribe_video_max_imsize

        return config_update

    def _require_local_file(self, local_path: str | None, *, suffix_hint: str) -> Path:
        if not local_path:
            raise ValidationAppError(
                f"A local {suffix_hint} file path is required for TRIBE inference."
            )
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
            return max(
                0.0, self._coerce_float(stop, default=0.0) - self._coerce_float(start, default=0.0)
            )
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

    def _format_prediction_error(self, exc: Exception) -> str:
        message = str(exc).strip()
        lowered = message.lower()

        if "gated repo" in lowered or "cannot access gated repo" in lowered:
            return (
                "TRIBE v2 prediction failed because a configured Hugging Face feature model is gated. "
                f"Configured text feature model: {self.text_feature_model_name}. "
                "Set TRIBE_TEXT_FEATURE_MODEL_NAME to a public compatible model or provide HF_TOKEN with access. "
                f"Original error: {message}"
            )

        return f"TRIBE v2 prediction failed for the prepared events payload: {message}"

    def _format_load_error(self, exc: Exception) -> str:
        message = str(exc).strip()
        lowered = message.lower()

        if (
            self._resolve_local_model_path(self.text_feature_model_name) is not None
            and "does not exist" in lowered
        ):
            return (
                "Failed to load TRIBE v2 because the configured local text feature model path was rejected "
                "during runtime validation. "
                f"Configured text feature model: {self.text_feature_model_name}. "
                "Verify the directory exists inside the running API/worker environment and contains a full "
                "Hugging Face model snapshot. "
                f"Original error: {message}"
            )

        if "unexpected keyword argument 'token'" in lowered or "unexpected keyword argument 'use_auth_token'" in lowered:
            return (
                "TRIBE v2 refused a Hugging Face ``token`` / ``use_auth_token`` argument on "
                "``TribeModel.from_pretrained`` (the upstream API only uses environment variables). "
                "NeuroMarketer applies a compatibility shim on load; restart workers after upgrading. "
                "Set HF_TOKEN for gated checkpoints. "
                f"Original error: {message}"
            )

        return (
            "Failed to load TRIBE v2 from the configured checkpoint. "
            "Check model availability, Hugging Face access, and runtime dependencies. "
            f"Original error: {message}"
        )


_shared_runtime: TribeRuntime | None = None


def get_shared_tribe_runtime() -> TribeRuntime:
    global _shared_runtime
    if _shared_runtime is None:
        _shared_runtime = TribeRuntime()
    return _shared_runtime
