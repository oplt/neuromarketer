from __future__ import annotations

import asyncio
from uuid import uuid4

from backend import tasks
from backend.core.exceptions import DependencyAppError
from backend.schemas.evaluators import EvaluationMode


def test_dispatch_uses_apply_async_when_in_process_disabled(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    def fake_apply_async(*, args, queue):
        calls.append({"args": args, "queue": queue})

    def fail_if_called(*args, **kwargs):
        raise AssertionError("inspect must not run when in-process fallback is disabled")

    monkeypatch.setattr(tasks.process_prediction_job_task, "apply_async", fake_apply_async)
    monkeypatch.setattr(tasks.celery_app.control, "inspect", fail_if_called)
    monkeypatch.setattr(tasks.settings, "enable_in_process_jobs", False)

    dispatch_mode = asyncio.run(tasks.dispatch_prediction_job(uuid4()))
    assert dispatch_mode == "celery"
    assert len(calls) == 1


def test_dispatch_prediction_job_in_process_when_no_inference_workers(monkeypatch) -> None:
    scheduled: list[object] = []

    def fail_apply_async(**kwargs):
        raise AssertionError("apply_async must not run when no workers consume the inference queue")

    monkeypatch.setattr(tasks.settings, "enable_in_process_jobs", True)
    monkeypatch.setattr(tasks, "_celery_workers_listen_to_queue", lambda queue_name: False)
    monkeypatch.setattr(tasks.process_prediction_job_task, "apply_async", fail_apply_async)
    monkeypatch.setattr(tasks, "_schedule_prediction_job_in_process", lambda job_id: scheduled.append(job_id))

    job_id = uuid4()
    dispatch_mode = asyncio.run(tasks.dispatch_prediction_job(job_id))
    assert dispatch_mode == "in_process"
    assert scheduled == [job_id]


def test_dispatch_prediction_job_celery_when_inference_workers_present(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    def fake_apply_async(*, args, queue):
        calls.append({"args": args, "queue": queue})

    scheduled: list[object] = []

    monkeypatch.setattr(tasks.settings, "enable_in_process_jobs", True)
    monkeypatch.setattr(tasks, "_celery_workers_listen_to_queue", lambda queue_name: True)
    monkeypatch.setattr(tasks.process_prediction_job_task, "apply_async", fake_apply_async)
    monkeypatch.setattr(tasks, "_schedule_prediction_job_in_process", lambda job_id: scheduled.append(job_id))

    dispatch_mode = asyncio.run(tasks.dispatch_prediction_job(uuid4()))
    assert dispatch_mode == "celery"
    assert len(calls) == 1
    assert scheduled == []


def test_enqueue_failure_without_in_process_fallback_raises(monkeypatch) -> None:
    def fail_apply_async(*, args, queue):
        raise RuntimeError("broker down")

    monkeypatch.setattr(tasks.process_prediction_job_task, "apply_async", fail_apply_async)
    monkeypatch.setattr(tasks.settings, "enable_in_process_jobs", False)

    try:
        asyncio.run(tasks.dispatch_prediction_job(uuid4()))
        raise AssertionError("Expected DependencyAppError when fallback is disabled.")
    except DependencyAppError:
        pass


def test_enqueue_failure_with_in_process_fallback_schedules(monkeypatch) -> None:
    scheduled: list[object] = []

    def fail_apply_async(*, args, queue):
        raise RuntimeError("broker down")

    def fake_schedule(job_id):
        scheduled.append(job_id)

    monkeypatch.setattr(tasks.process_prediction_job_task, "apply_async", fail_apply_async)
    monkeypatch.setattr(tasks, "_schedule_prediction_job_in_process", fake_schedule)
    monkeypatch.setattr(tasks.settings, "enable_in_process_jobs", True)

    dispatch_mode = asyncio.run(tasks.dispatch_prediction_job(uuid4()))
    assert dispatch_mode == "in_process"
    assert len(scheduled) == 1


def test_llm_enqueue_failure_without_fallback_raises(monkeypatch) -> None:
    def fail_apply_async(*, args, queue):
        raise RuntimeError("broker down")

    monkeypatch.setattr(tasks.process_llm_evaluation_task, "apply_async", fail_apply_async)
    monkeypatch.setattr(tasks.settings, "enable_in_process_jobs", False)

    try:
        asyncio.run(tasks.dispatch_llm_evaluation_job(uuid4(), EvaluationMode.MARKETING))
        raise AssertionError("Expected DependencyAppError when fallback is disabled.")
    except DependencyAppError:
        pass
