from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from backend.application.services.analysis_pipeline_state import (
    can_acquire_inference,
    can_acquire_scoring,
    transition_to_completed,
    transition_to_scoring_running,
)
from backend.db.models import JobStatus


def _job(**overrides):
    now = datetime.now(UTC)
    defaults = {
        "status": JobStatus.QUEUED,
        "started_at": None,
        "completed_at": None,
        "error_message": None,
        "runtime_params": {},
        "execution_phase": "queued",
        "execution_phase_updated_at": now,
        "prediction": None,
        "analysis_result_record": None,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_can_acquire_inference_blocks_running_non_stale():
    job = _job(status=JobStatus.RUNNING, started_at=datetime.now(UTC) - timedelta(seconds=5))
    assert can_acquire_inference(job, stale_after_seconds=60) is False


def test_can_acquire_inference_allows_running_stale():
    job = _job(status=JobStatus.RUNNING, started_at=datetime.now(UTC) - timedelta(seconds=120))
    assert can_acquire_inference(job, stale_after_seconds=60) is True


def test_can_acquire_scoring_blocks_without_prediction():
    job = _job(status=JobStatus.RUNNING, execution_phase="scoring_queued", prediction=None)
    assert can_acquire_scoring(job, stale_after_seconds=60) is False


def test_can_acquire_scoring_allows_queued_prediction():
    job = _job(
        status=JobStatus.RUNNING,
        execution_phase="scoring_queued",
        prediction=SimpleNamespace(id="pred"),
        analysis_result_record=None,
    )
    assert can_acquire_scoring(job, stale_after_seconds=60) is True


def test_transition_to_completed_clears_partial_snapshot():
    job = _job(
        status=JobStatus.RUNNING,
        runtime_params={"analysis_partial_result": {"job_id": "x"}},
    )
    transition_to_completed(job)
    assert job.status == JobStatus.SUCCEEDED
    assert "analysis_partial_result" not in job.runtime_params


def test_transition_to_scoring_running_sets_phase_metadata():
    job = _job(status=JobStatus.RUNNING, execution_phase="scoring_queued")
    transition_to_scoring_running(job)
    phase_payload = (job.runtime_params or {}).get("analysis_execution_phase") or {}
    assert phase_payload.get("phase") == "scoring_running"
