from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from backend.core.config import settings
from backend.services.tribe_runtime import (
    TribeRuntime,
    TribeRuntimeInput,
    _ensure_tribe_model_from_pretrained_strips_hub_kwargs,
)


class _ExplodingTextModel:
    def get_events_dataframe(
        self, *args, **kwargs
    ):  # pragma: no cover - this should never be called
        raise AssertionError(
            "Text inference should not call tribev2.get_events_dataframe(text_path=...)"
        )


def test_prepare_text_events_bypasses_whisperx_text_path() -> None:
    runtime = TribeRuntime()

    events, temp_path = runtime._prepare_text_events(
        model=_ExplodingTextModel(),
        payload=TribeRuntimeInput(
            modality="text",
            raw_text="Hello world. This PDF should be analyzed directly as text.",
        ),
    )

    assert temp_path is None
    assert not events.empty
    assert "Word" in set(events["type"].unique())
    word_events = events[events["type"] == "Word"]
    assert word_events["context"].astype(str).str.len().min() > 0
    assert list(word_events["text"].head(3)) == ["Hello", "world", "This"]


def test_text_events_standardize_without_legacy_missing_class_kwarg(monkeypatch) -> None:
    calls: list[dict] = []

    def fake_standardize_events(events, **kwargs):
        calls.append(kwargs)
        return events

    monkeypatch.setitem(sys.modules, "neuralset", SimpleNamespace())
    monkeypatch.setitem(sys.modules, "neuralset.events", SimpleNamespace())
    monkeypatch.setitem(
        sys.modules,
        "neuralset.events.utils",
        SimpleNamespace(standardize_events=fake_standardize_events),
    )

    runtime = TribeRuntime()
    events = runtime._build_text_events_dataframe("Read this now. Try the product today.")

    assert not events.empty
    assert calls == [{}]


def test_runtime_config_update_overrides_gated_default_text_model(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        settings,
        "tribe_text_feature_model_name",
        "microsoft/Phi-3-mini-4k-instruct",
    )
    monkeypatch.setattr(TribeRuntime, "_project_root", lambda self: tmp_path)

    runtime = TribeRuntime()
    config_update = runtime._build_runtime_config_update("cpu")

    assert config_update["data.text_feature.model_name"] == "microsoft/Phi-3-mini-4k-instruct"
    assert config_update["data.text_feature.device"] == "cpu"


def test_runtime_resolves_relative_local_text_feature_model_path(
    monkeypatch, tmp_path: Path
) -> None:
    local_model = tmp_path / "models" / "phi3-mini-4k-instruct"
    local_model.mkdir(parents=True)

    monkeypatch.setattr(settings, "tribe_text_feature_model_name", "models/phi3-mini-4k-instruct")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(TribeRuntime, "_project_root", lambda self: tmp_path)

    runtime = TribeRuntime()

    assert runtime.text_feature_model_name == str(local_model.resolve())


def test_runtime_falls_back_to_bundled_local_phi3_model(monkeypatch, tmp_path: Path) -> None:
    local_model = tmp_path / "models" / "phi3-mini-4k-instruct"
    local_model.mkdir(parents=True)

    monkeypatch.setattr(
        settings, "tribe_text_feature_model_name", "microsoft/Phi-3-mini-4k-instruct"
    )
    monkeypatch.setattr(TribeRuntime, "_project_root", lambda self: tmp_path)

    runtime = TribeRuntime()

    assert runtime.text_feature_model_name == str(local_model.resolve())


def test_runtime_resolves_relative_cache_folder_under_project_root(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(settings, "tribe_cache_folder", "./cache/tribev2")
    monkeypatch.setattr(TribeRuntime, "_project_root", lambda self: tmp_path)

    runtime = TribeRuntime()

    assert runtime.cache_folder == (tmp_path / "cache" / "tribev2").resolve()


def test_runtime_does_not_log_cache_fallback_for_project_relative_path(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(settings, "tribe_cache_folder", "./cache/tribev2")
    monkeypatch.setattr(TribeRuntime, "_project_root", lambda self: tmp_path)

    with patch("backend.services.tribe_runtime.log_event") as log_event_mock:
        runtime = TribeRuntime()

    assert runtime.cache_folder == (tmp_path / "cache" / "tribev2").resolve()
    fallback_events = [
        call
        for call in log_event_mock.call_args_list
        if len(call.args) >= 2 and call.args[1] == "tribe_cache_folder_fallback"
    ]
    assert fallback_events == []


def test_local_model_path_patch_accepts_existing_directories(monkeypatch, tmp_path: Path) -> None:
    local_model = tmp_path / "models" / "phi3-mini-4k-instruct"
    local_model.mkdir(parents=True)

    class _FakeHuggingFaceMixin:
        def __init__(self, model_name: str) -> None:
            self.model_name = model_name

        def repo_exists(self) -> bool:
            return False

    original_import_module = importlib.import_module
    fake_module = SimpleNamespace(HuggingFaceMixin=_FakeHuggingFaceMixin)

    def fake_import_module(name: str):
        if name == "neuralset.extractors.base":
            return fake_module
        return original_import_module(name)

    monkeypatch.setattr(importlib, "import_module", fake_import_module)
    monkeypatch.setattr(TribeRuntime, "_local_hf_model_path_patch_applied", False)
    monkeypatch.setattr(TribeRuntime, "_project_root", lambda self: tmp_path)

    runtime = TribeRuntime()
    runtime._enable_local_huggingface_model_paths()

    assert _FakeHuggingFaceMixin(str(local_model)).repo_exists() is True
    assert _FakeHuggingFaceMixin("facebook/tribev2").repo_exists() is False


def test_prediction_error_mentions_text_model_for_gated_repo() -> None:
    runtime = TribeRuntime()

    message = runtime._format_prediction_error(
        RuntimeError(
            "Cannot access gated repo for url https://huggingface.co/meta-llama/Llama-3.2-3B/resolve/main/config.json"
        )
    )

    assert "configured Hugging Face feature model is gated" in message
    assert runtime.text_feature_model_name in message
    assert "TRIBE_TEXT_FEATURE_MODEL_NAME" in message


def test_tribe_from_pretrained_hub_token_patch_is_idempotent() -> None:
    from tribev2.demo_utils import TribeModel

    patch_attr = "_neuromarketer_strip_hf_token_kwargs_applied"
    _ensure_tribe_model_from_pretrained_strips_hub_kwargs()
    assert getattr(TribeModel, patch_attr, False) is True
    _ensure_tribe_model_from_pretrained_strips_hub_kwargs()
    assert getattr(TribeModel, patch_attr, False) is True


def test_format_load_error_explains_token_kwarg_rejection() -> None:
    runtime = TribeRuntime()
    message = runtime._format_load_error(
        TypeError("TribeModel.from_pretrained() got an unexpected keyword argument 'token'")
    )
    assert "token" in message.lower()
    assert "HF_TOKEN" in message
