from __future__ import annotations

import warnings

from celery.app.control import DuplicateNodenameWarning

from backend import tasks


class _InspectorStub:
    def __init__(self) -> None:
        self.active_queue_calls = 0

    def ping(self):
        warnings.warn(
            DuplicateNodenameWarning("Received multiple replies from node name: celery@test."),
            stacklevel=1,
        )
        return {"celery@test": {"ok": "pong"}}

    def active_queues(self):
        self.active_queue_calls += 1
        return {
            "celery@test": [
                {"name": "analysis-scoring"},
            ]
        }


def test_has_active_workers_suppresses_duplicate_node_warning(monkeypatch) -> None:
    inspector = _InspectorStub()
    monkeypatch.setattr(tasks, "_is_broker_reachable", lambda timeout_seconds=0.25: True)
    monkeypatch.setattr(tasks.celery_app.control, "inspect", lambda timeout=0.4: inspector)

    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        assert tasks._has_active_workers("analysis-scoring") is True

    assert inspector.active_queue_calls == 1
    assert not any(issubclass(item.category, DuplicateNodenameWarning) for item in captured)
