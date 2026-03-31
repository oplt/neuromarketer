from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from backend.core.exceptions import UnsupportedModalityAppError
from backend.services import tribe_runtime as runtime_module
from backend.services.tribe_runtime import TribeRuntime, TribeRuntimeInput


class _FakeTribeModel:
    from_pretrained_calls: list[dict] = []
    last_instance: "_FakeTribeModel | None" = None

    def __init__(self) -> None:
        self._model = SimpleNamespace(device="cpu")
        self.get_events_calls: list[dict] = []
        self.predict_calls: list[object] = []

    @classmethod
    def from_pretrained(cls, checkpoint_dir: str, **kwargs: object) -> "_FakeTribeModel":
        cls.from_pretrained_calls.append({"checkpoint_dir": checkpoint_dir, **kwargs})
        cls.last_instance = cls()
        return cls.last_instance

    def get_events_dataframe(self, **kwargs: object) -> list[dict[str, object]]:
        self.get_events_calls.append(kwargs)
        event_type = "Video"
        if "audio_path" in kwargs:
            event_type = "Audio"
        elif "text_path" in kwargs:
            event_type = "Word"
        return [
            {"type": event_type, "start": 0.0, "duration": 1.5},
            {"type": "Word", "start": 0.2, "duration": 0.3},
        ]

    def predict(self, *, events: object) -> tuple[np.ndarray, list[object]]:
        self.predict_calls.append(events)
        segments = [
            SimpleNamespace(
                start=0.0,
                duration=1.5,
                ns_events=[SimpleNamespace(type="Video"), SimpleNamespace(type="Word")],
            ),
            SimpleNamespace(
                start=1.5,
                duration=1.5,
                ns_events=[SimpleNamespace(type="Word")],
            ),
        ]
        return np.array([[0.1, -0.2, 0.4, -0.3], [0.2, -0.1, 0.5, -0.4]], dtype=np.float32), segments


class TribeRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        TribeRuntime._shared_model = None
        TribeRuntime._shared_module = None
        TribeRuntime._resolved_device = None
        runtime_module._shared_runtime = None
        _FakeTribeModel.from_pretrained_calls.clear()
        _FakeTribeModel.last_instance = None

    def _import_module(self, name: str):
        if name == "tribev2":
            return SimpleNamespace(TribeModel=_FakeTribeModel)
        raise AssertionError(f"Unexpected import: {name}")

    @patch.object(TribeRuntime, "validate_environment", autospec=True, return_value=None)
    @patch.object(TribeRuntime, "_authenticate_huggingface", autospec=True, return_value=None)
    def test_load_caches_model_per_process(self, *_: object) -> None:
        runtime = TribeRuntime()

        with (
            patch("backend.services.tribe_runtime.importlib.import_module", side_effect=self._import_module),
            patch.object(TribeRuntime, "_get_requested_device", autospec=True, return_value="cpu"),
        ):
            runtime.load()
            runtime.load()

        self.assertEqual(len(_FakeTribeModel.from_pretrained_calls), 1)
        self.assertEqual(_FakeTribeModel.from_pretrained_calls[0]["checkpoint_dir"], runtime.model_repo_id)
        self.assertEqual(_FakeTribeModel.from_pretrained_calls[0]["device"], "cpu")
        self.assertEqual(
            _FakeTribeModel.from_pretrained_calls[0]["config_update"]["data.video_feature.image.device"],
            "cpu",
        )

    @patch.object(TribeRuntime, "validate_environment", autospec=True, return_value=None)
    @patch.object(TribeRuntime, "_authenticate_huggingface", autospec=True, return_value=None)
    def test_infer_routes_video_audio_and_text_to_official_api(self, *_: object) -> None:
        runtime = TribeRuntime()

        with (
            tempfile.NamedTemporaryFile(suffix=".mp4") as video_file,
            tempfile.NamedTemporaryFile(suffix=".mp3") as audio_file,
            patch("backend.services.tribe_runtime.importlib.import_module", side_effect=self._import_module),
        ):
            video_output = runtime.infer(TribeRuntimeInput(modality="video", local_path=video_file.name))
            audio_output = runtime.infer(TribeRuntimeInput(modality="audio", local_path=audio_file.name))
            text_output = runtime.infer(TribeRuntimeInput(modality="text", raw_text="A simple launch script."))

        instance = _FakeTribeModel.last_instance
        assert instance is not None

        self.assertEqual(instance.get_events_calls[0], {"video_path": video_file.name})
        self.assertEqual(instance.get_events_calls[1], {"audio_path": audio_file.name})
        self.assertIn("text_path", instance.get_events_calls[2])
        self.assertTrue(instance.get_events_calls[2]["text_path"].endswith(".txt"))
        self.assertIn("prediction_summary", video_output.raw_brain_response_summary)
        self.assertIn("segment_features", audio_output.reduced_feature_vector)
        self.assertIn("contract_notes", text_output.provenance_json)

    def test_infer_rejects_unsupported_modalities(self) -> None:
        runtime = TribeRuntime()

        with self.assertRaises(UnsupportedModalityAppError):
            runtime.infer(TribeRuntimeInput(modality="image", local_path="/tmp/fake.png"))

    def test_auto_device_falls_back_to_cpu_when_cuda_is_unavailable(self) -> None:
        runtime = TribeRuntime()

        with patch("torch.cuda.is_available", return_value=False):
            self.assertEqual(runtime._get_requested_device(), "cpu")

    def test_runtime_config_update_includes_cpu_speed_overrides(self) -> None:
        runtime = TribeRuntime()

        with (
            patch.object(runtime_module.settings, "tribe_video_feature_frequency_hz", 0.5),
            patch.object(runtime_module.settings, "tribe_video_max_imsize", 480),
        ):
            config_update = runtime._build_runtime_config_update("cpu")

        self.assertEqual(config_update["data.video_feature.frequency"], 0.5)
        self.assertEqual(config_update["data.video_feature.max_imsize"], 480)


if __name__ == "__main__":
    unittest.main()
