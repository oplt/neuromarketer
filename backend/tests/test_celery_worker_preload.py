from __future__ import annotations

from backend import celery_app


def test_scoring_worker_does_not_preload_tribe_runtime(monkeypatch) -> None:
    called = {"runtime": 0}

    class _RuntimeStub:
        cache_folder = "/tmp/cache"

        def get_requested_device(self) -> str:
            return "cpu"

        def load(self) -> None:
            called["runtime"] += 1

    monkeypatch.setattr(celery_app.settings, "celery_worker_role", "scoring")
    monkeypatch.setattr(celery_app, "get_shared_tribe_runtime", lambda: _RuntimeStub())
    monkeypatch.setattr(celery_app.settings, "tribe_preload_on_worker_startup", False)

    celery_app.preload_tribe_runtime()
    assert called["runtime"] == 0


def test_inference_worker_can_preload_tribe_runtime(monkeypatch) -> None:
    called = {"runtime": 0}

    class _RuntimeStub:
        cache_folder = "/tmp/cache"

        def get_requested_device(self) -> str:
            return "cpu"

        def get_resolved_device(self) -> str:
            return "cpu"

        def load(self) -> None:
            called["runtime"] += 1

    monkeypatch.setattr(celery_app.settings, "celery_worker_role", "inference")
    monkeypatch.setattr(celery_app, "get_shared_tribe_runtime", lambda: _RuntimeStub())
    monkeypatch.setattr(celery_app.settings, "tribe_preload_on_worker_startup", False)

    celery_app.preload_tribe_runtime()
    assert called["runtime"] == 1
