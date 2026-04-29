from __future__ import annotations

import asyncio
from uuid import uuid4

from backend import tasks
from backend.core.exceptions import DependencyAppError
from backend.schemas.evaluators import EvaluationMode


def test_should_use_in_process_jobs_dev_enabled(monkeypatch) -> None:
    monkeypatch.setattr(tasks.settings, "app_env", "development")
    monkeypatch.setattr(tasks.settings, "enable_in_process_jobs", True)
    monkeypatch.setattr(tasks.settings, "force_in_process_jobs", False)
    assert tasks.should_use_in_process_jobs() is True


def test_should_use_in_process_jobs_prod_disabled_without_force(monkeypatch) -> None:
    monkeypatch.setattr(tasks.settings, "app_env", "production")
    monkeypatch.setattr(tasks.settings, "enable_in_process_jobs", True)
    monkeypatch.setattr(tasks.settings, "force_in_process_jobs", False)
    assert tasks.should_use_in_process_jobs() is False


def test_should_use_in_process_jobs_prod_enabled_with_force_still_disabled(monkeypatch) -> None:
    monkeypatch.setattr(tasks.settings, "app_env", "production")
    monkeypatch.setattr(tasks.settings, "enable_in_process_jobs", True)
    monkeypatch.setattr(tasks.settings, "force_in_process_jobs", True)
    assert tasks.should_use_in_process_jobs() is False


def test_dispatch_uses_apply_async_without_inspect_hot_path(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    def fake_apply_async(*, args, queue):
        calls.append({"args": args, "queue": queue})

    def fail_if_called(*args, **kwargs):
        raise AssertionError("inspect must not run when in-process fallback is disabled")

    monkeypatch.setattr(tasks.process_prediction_job_task, "apply_async", fake_apply_async)
    monkeypatch.setattr(tasks.celery_app.control, "inspect", fail_if_called)
    monkeypatch.setattr(tasks.settings, "enable_in_process_jobs", False)
    monkeypatch.setattr(tasks.settings, "app_env", "production")

    dispatch_mode = asyncio.run(tasks.dispatch_prediction_job(uuid4()))
    assert dispatch_mode == "celery"
    assert len(calls) == 1


def test_dispatch_prediction_job_prefers_celery_even_when_in_process_enabled(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    def fake_apply_async(*, args, queue):
        calls.append({"args": args, "queue": queue})

    scheduled: list[object] = []

    monkeypatch.setattr(tasks.settings, "enable_in_process_jobs", True)
    monkeypatch.setattr(tasks.settings, "app_env", "development")
    monkeypatch.setattr(tasks.settings, "force_in_process_jobs", False)
    monkeypatch.setattr(tasks.process_prediction_job_task, "apply_async", fake_apply_async)
    monkeypatch.setattr(
        tasks,
        "_schedule_prediction_job_in_process",
        lambda job_id: scheduled.append(job_id),
    )

    dispatch_mode = asyncio.run(tasks.dispatch_prediction_job(uuid4()))
    assert dispatch_mode == "celery"
    assert len(calls) == 1
    assert scheduled == []


def test_enqueue_failure_without_in_process_fallback_raises(monkeypatch) -> None:
    def fail_apply_async(*, args, queue):
        raise RuntimeError("broker down")

    monkeypatch.setattr(tasks.process_prediction_job_task, "apply_async", fail_apply_async)
    monkeypatch.setattr(tasks.settings, "enable_in_process_jobs", False)
    monkeypatch.setattr(tasks.settings, "app_env", "production")

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
    monkeypatch.setattr(tasks.settings, "app_env", "development")
    monkeypatch.setattr(tasks.settings, "force_in_process_jobs", False)

    dispatch_mode = asyncio.run(tasks.dispatch_prediction_job(uuid4()))
    assert dispatch_mode == "in_process"
    assert len(scheduled) == 1


def test_llm_enqueue_failure_without_fallback_raises(monkeypatch) -> None:
    def fail_apply_async(*, args, queue):
        raise RuntimeError("broker down")

    monkeypatch.setattr(tasks.process_llm_evaluation_task, "apply_async", fail_apply_async)
    monkeypatch.setattr(tasks.settings, "enable_in_process_jobs", False)
    monkeypatch.setattr(tasks.settings, "app_env", "production")

    try:
        asyncio.run(tasks.dispatch_llm_evaluation_job(uuid4(), EvaluationMode.MARKETING))
        raise AssertionError("Expected DependencyAppError when fallback is disabled.")
    except DependencyAppError:
        pass


def test_dispatch_prediction_scoring_uses_celery(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    def fake_apply_async(*, args, queue):
        calls.append({"args": args, "queue": queue})

    monkeypatch.setattr(tasks.process_prediction_scoring_task, "apply_async", fake_apply_async)
    monkeypatch.setattr(tasks.settings, "enable_in_process_jobs", False)
    monkeypatch.setattr(tasks.settings, "app_env", "production")

    dispatch_mode = asyncio.run(tasks.dispatch_prediction_scoring_job(uuid4()))
    assert dispatch_mode == "celery"
    assert len(calls) == 1


def test_dispatch_analysis_asset_promotion_uses_celery(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    def fake_apply_async(*, args, queue):
        calls.append({"args": args, "queue": queue})

    monkeypatch.setattr(
        tasks.process_analysis_asset_promotion_task,
        "apply_async",
        fake_apply_async,
    )
    monkeypatch.setattr(tasks.settings, "enable_in_process_jobs", False)
    monkeypatch.setattr(tasks.settings, "app_env", "production")

    dispatch_mode = asyncio.run(
        tasks.dispatch_analysis_asset_promotion(
            upload_session_id=uuid4(),
            asset_id=uuid4(),
            user_id=uuid4(),
        )
    )
    assert dispatch_mode == "celery"
    assert len(calls) == 1
