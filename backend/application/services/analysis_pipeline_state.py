from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal

from backend.db.models import JobStatus

AnalysisExecutionPhase = Literal[
    "queued",
    "inference_running",
    "inference_completed",
    "scoring_queued",
    "scoring_running",
    "completed",
    "failed",
    "canceled",
]

VALID_ANALYSIS_EXECUTION_PHASES: tuple[AnalysisExecutionPhase, ...] = (
    "queued",
    "inference_running",
    "inference_completed",
    "scoring_queued",
    "scoring_running",
    "completed",
    "failed",
    "canceled",
)


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _normalize_phase(value: object) -> str:
    if not isinstance(value, str):
        return ""
    normalized = value.strip().lower()
    return normalized if normalized in VALID_ANALYSIS_EXECUTION_PHASES else ""


def _is_stale(updated_at: datetime | None, *, stale_after_seconds: int, now: datetime) -> bool:
    if updated_at is None:
        return False
    return updated_at < now - timedelta(seconds=max(0, stale_after_seconds))


def _set_execution_phase(job, *, phase: AnalysisExecutionPhase, now: datetime | None = None) -> None:
    timestamp = now or _now_utc()
    runtime_params = dict(job.runtime_params or {})
    runtime_params["analysis_execution_phase"] = {
        "phase": phase,
        "updated_at": timestamp.isoformat(),
    }
    if phase == "completed":
        runtime_params.pop("analysis_partial_result", None)
    job.runtime_params = runtime_params
    job.execution_phase = phase
    job.execution_phase_updated_at = timestamp


def can_acquire_inference(job, *, stale_after_seconds: int) -> bool:
    if job.status in {JobStatus.CANCELED, JobStatus.FAILED}:
        return False
    if job.prediction is not None:
        return False

    now = _now_utc()
    if job.status == JobStatus.RUNNING:
        if job.started_at is None:
            return True
        return _is_stale(job.started_at, stale_after_seconds=stale_after_seconds, now=now)

    return job.status in {JobStatus.QUEUED, JobStatus.PREPROCESSING}


def can_acquire_scoring(job, *, stale_after_seconds: int) -> bool:
    if job.status in {JobStatus.CANCELED, JobStatus.SUCCEEDED, JobStatus.FAILED}:
        return False
    if job.prediction is None:
        return False
    if job.analysis_result_record is not None:
        return False

    now = _now_utc()
    phase_name = _normalize_phase(job.execution_phase)
    if phase_name == "scoring_queued":
        return True
    if phase_name == "scoring_running":
        return _is_stale(
            job.execution_phase_updated_at,
            stale_after_seconds=stale_after_seconds,
            now=now,
        )
    return False


def transition_to_inference_running(job) -> None:
    now = _now_utc()
    job.status = JobStatus.RUNNING
    job.started_at = now
    job.completed_at = None
    job.error_message = None
    _set_execution_phase(job, phase="inference_running", now=now)


def transition_to_inference_completed(job) -> None:
    _set_execution_phase(job, phase="inference_completed")


def transition_to_scoring_queued(job) -> None:
    _set_execution_phase(job, phase="scoring_queued")


def transition_to_scoring_running(job) -> None:
    _set_execution_phase(job, phase="scoring_running")


def transition_to_completed(job) -> None:
    now = _now_utc()
    job.status = JobStatus.SUCCEEDED
    job.error_message = None
    job.completed_at = now
    _set_execution_phase(job, phase="completed", now=now)


def transition_to_failed(job, *, error_message: str) -> None:
    now = _now_utc()
    job.status = JobStatus.FAILED
    job.error_message = error_message
    job.completed_at = now
    _set_execution_phase(job, phase="failed", now=now)


def transition_to_canceled(job, *, error_message: str | None = None) -> None:
    now = _now_utc()
    job.status = JobStatus.CANCELED
    job.error_message = error_message
    job.completed_at = now
    _set_execution_phase(job, phase="canceled", now=now)


def transition_to_queued(job) -> None:
    now = _now_utc()
    job.status = JobStatus.QUEUED
    job.error_message = None
    job.started_at = None
    job.completed_at = None
    _set_execution_phase(job, phase="queued", now=now)
