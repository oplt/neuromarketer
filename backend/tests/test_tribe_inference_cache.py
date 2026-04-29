from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta

from backend.services.tribe_inference_service import TribeInferenceService


def _write_cache_entry(
    path, *, created_at: datetime, last_accessed_at: datetime, payload: dict, size_bytes: int = 128
):
    path.write_text(
        json.dumps(
            {
                "cache_version": 1,
                "created_at": created_at.isoformat(),
                "last_accessed_at": last_accessed_at.isoformat(),
                "size_bytes": size_bytes,
                "payload": payload,
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def test_runtime_cache_cleanup_removes_expired_entries(tmp_path):
    service = TribeInferenceService()
    service.runtime_output_cache_enabled = True
    service.runtime_output_cache_folder = tmp_path
    service.runtime_output_cache_max_age = timedelta(hours=1)
    service.runtime_output_cache_max_bytes = 10_000
    service.runtime_output_cache_cleanup_interval_seconds = 0
    TribeInferenceService._last_cache_cleanup_monotonic = 0.0

    expired_path = tmp_path / "expired.json"
    fresh_path = tmp_path / "fresh.json"
    now = datetime.now(UTC)
    _write_cache_entry(
        expired_path,
        created_at=now - timedelta(hours=3),
        last_accessed_at=now - timedelta(hours=2),
        payload={"reduced_feature_vector": {"segment_count": 1}},
    )
    _write_cache_entry(
        fresh_path,
        created_at=now,
        last_accessed_at=now,
        payload={"reduced_feature_vector": {"segment_count": 2}},
    )

    service._maybe_cleanup_runtime_cache()

    assert not expired_path.exists()
    assert fresh_path.exists()


def test_runtime_cache_cleanup_enforces_max_size_by_oldest_access(tmp_path):
    service = TribeInferenceService()
    service.runtime_output_cache_enabled = True
    service.runtime_output_cache_folder = tmp_path
    service.runtime_output_cache_max_age = timedelta(hours=24)
    service.runtime_output_cache_max_bytes = 200
    service.runtime_output_cache_cleanup_interval_seconds = 0
    TribeInferenceService._last_cache_cleanup_monotonic = 0.0

    now = datetime.now(UTC)
    oldest_path = tmp_path / "oldest.json"
    newest_path = tmp_path / "newest.json"
    _write_cache_entry(
        oldest_path,
        created_at=now - timedelta(minutes=10),
        last_accessed_at=now - timedelta(minutes=10),
        payload={"reduced_feature_vector": {"segment_count": 1}},
        size_bytes=150,
    )
    _write_cache_entry(
        newest_path,
        created_at=now - timedelta(minutes=1),
        last_accessed_at=now - timedelta(minutes=1),
        payload={"reduced_feature_vector": {"segment_count": 2}},
        size_bytes=150,
    )

    service._maybe_cleanup_runtime_cache()

    assert not oldest_path.exists()
    assert newest_path.exists()


def test_extractor_cache_cleanup_removes_expired_entries(tmp_path):
    service = TribeInferenceService()
    service.extractor_cache_cleanup_enabled = True
    service.extractor_cache_root = tmp_path
    service.extractor_cache_max_age = timedelta(hours=1)
    service.extractor_cache_max_bytes = 10_000
    service.extractor_cache_cleanup_interval_seconds = 0
    TribeInferenceService._last_extractor_cache_cleanup_monotonic = 0.0

    cache_dir = tmp_path / "neuralset.extractors.text.HuggingFaceText._get_data,release" / "bucket"
    cache_dir.mkdir(parents=True, exist_ok=True)
    expired_path = cache_dir / "expired-info.jsonl"
    fresh_path = cache_dir / "fresh-info.jsonl"
    expired_path.write_text("expired", encoding="utf-8")
    fresh_path.write_text("fresh", encoding="utf-8")

    now_timestamp = datetime.now(UTC).timestamp()
    os.utime(expired_path, (now_timestamp - 3 * 3600, now_timestamp - 3 * 3600))
    os.utime(fresh_path, (now_timestamp, now_timestamp))

    service._maybe_cleanup_extractor_cache()

    assert not expired_path.exists()
    assert fresh_path.exists()


def test_extractor_cache_cleanup_enforces_size_by_oldest_access(tmp_path):
    service = TribeInferenceService()
    service.extractor_cache_cleanup_enabled = True
    service.extractor_cache_root = tmp_path
    service.extractor_cache_max_age = timedelta(hours=24)
    service.extractor_cache_max_bytes = 200
    service.extractor_cache_cleanup_interval_seconds = 0
    TribeInferenceService._last_extractor_cache_cleanup_monotonic = 0.0

    cache_dir = tmp_path / "neuralset.extractors.text.HuggingFaceText._get_data,release" / "bucket"
    cache_dir.mkdir(parents=True, exist_ok=True)
    oldest_path = cache_dir / "oldest-info.jsonl"
    newest_path = cache_dir / "newest-info.jsonl"
    oldest_path.write_bytes(b"a" * 150)
    newest_path.write_bytes(b"b" * 150)

    now_timestamp = datetime.now(UTC).timestamp()
    os.utime(oldest_path, (now_timestamp - 600, now_timestamp - 600))
    os.utime(newest_path, (now_timestamp - 60, now_timestamp - 60))

    service._maybe_cleanup_extractor_cache()

    assert not oldest_path.exists()
    assert newest_path.exists()


def test_extractor_cache_startup_purge_removes_existing_entries(tmp_path):
    service = TribeInferenceService()
    service.extractor_cache_cleanup_enabled = True
    service.extractor_cache_root = tmp_path
    service.extractor_cache_purge_on_startup = True
    TribeInferenceService._extractor_cache_startup_purged = False

    cache_dir = tmp_path / "neuralset.extractors.text.HuggingFaceText._get_data,release" / "bucket"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cached_info = cache_dir / "cached-info.jsonl"
    cached_info.write_text("cached", encoding="utf-8")

    service._purge_extractor_cache_on_startup_if_enabled()

    assert not cached_info.exists()
