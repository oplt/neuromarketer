from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass
from pathlib import Path

from backend.core.config import settings
from backend.core.logging import duration_ms, get_logger, log_event, log_exception
from backend.services.storage import build_s3_client

logger = get_logger(__name__)


@dataclass(slots=True)
class LoadedAsset:
    local_path: str
    storage_uri: str
    mime_type: str | None
    filename: str
    file_size_bytes: int | None
    temporary: bool = False

    def cleanup(self) -> None:
        if self.temporary and os.path.exists(self.local_path):
            os.unlink(self.local_path)


class AssetLoader:
    def __init__(self) -> None:
        self.s3_client = build_s3_client()
        self._cache_dir = Path(settings.asset_cache_folder).expanduser()
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    def load(self, *, storage_uri: str, mime_type: str | None = None) -> LoadedAsset:
        started_at = time.perf_counter()
        try:
            if storage_uri.startswith("s3://"):
                loaded_asset = self._load_from_s3(storage_uri=storage_uri, mime_type=mime_type)
            elif storage_uri.startswith("file://"):
                path = storage_uri.replace("file://", "", 1)
                loaded_asset = self._load_from_local_path(
                    local_path=path, storage_uri=storage_uri, mime_type=mime_type
                )
            elif storage_uri.startswith("/"):
                loaded_asset = self._load_from_local_path(
                    local_path=storage_uri,
                    storage_uri=f"file://{storage_uri}",
                    mime_type=mime_type,
                )
            else:
                raise ValueError(f"Unsupported storage URI: {storage_uri}")

            finished_at = time.perf_counter()
            log_event(
                logger,
                "asset_loaded",
                storage_uri=storage_uri,
                mime_type=mime_type,
                filename=loaded_asset.filename,
                file_size_bytes=loaded_asset.file_size_bytes,
                duration_ms=duration_ms(started_at, finished_at),
                status="succeeded",
            )
            return loaded_asset
        except Exception as exc:
            finished_at = time.perf_counter()
            log_exception(
                logger,
                "asset_load_failed",
                exc,
                storage_uri=storage_uri,
                mime_type=mime_type,
                duration_ms=duration_ms(started_at, finished_at),
                status="failed",
            )
            raise

    def _load_from_s3(self, *, storage_uri: str, mime_type: str | None) -> LoadedAsset:
        without_scheme = storage_uri.replace("s3://", "", 1)
        bucket_name, storage_key = without_scheme.split("/", 1)
        suffix = Path(storage_key).suffix
        uri_hash = hashlib.sha256(storage_uri.encode()).hexdigest()[:24]
        cached_path = self._cache_dir / f"{uri_hash}{suffix}"

        if cached_path.exists():
            log_event(
                logger, "asset_cache_hit", storage_uri=storage_uri, local_path=str(cached_path)
            )
            return LoadedAsset(
                local_path=str(cached_path),
                storage_uri=storage_uri,
                mime_type=mime_type,
                filename=Path(storage_key).name,
                file_size_bytes=cached_path.stat().st_size,
                temporary=False,
            )

        self.s3_client.download_file(bucket_name, storage_key, str(cached_path))
        log_event(logger, "asset_cache_miss", storage_uri=storage_uri, local_path=str(cached_path))
        return LoadedAsset(
            local_path=str(cached_path),
            storage_uri=storage_uri,
            mime_type=mime_type,
            filename=Path(storage_key).name,
            file_size_bytes=cached_path.stat().st_size,
            temporary=False,
        )

    def remove_cached_asset(self, *, storage_uri: str) -> list[str]:
        removed_paths: list[str] = []
        for cached_path in self._candidate_cached_paths(storage_uri=storage_uri):
            if not cached_path.exists():
                continue
            try:
                cached_path.unlink()
                removed_paths.append(str(cached_path))
            except OSError as exc:
                log_exception(
                    logger,
                    "asset_cache_delete_failed",
                    exc,
                    storage_uri=storage_uri,
                    local_path=str(cached_path),
                    status="failed",
                )
        if removed_paths:
            log_event(
                logger,
                "asset_cache_deleted",
                storage_uri=storage_uri,
                removed_count=len(removed_paths),
                removed_paths=removed_paths,
                status="deleted",
            )
        return removed_paths

    def _candidate_cached_paths(self, *, storage_uri: str) -> list[Path]:
        uri_hash = hashlib.sha256(storage_uri.encode()).hexdigest()[:24]
        parsed_path = storage_uri.replace("s3://", "", 1).split("/", 1)[-1]
        suffix = Path(parsed_path).suffix
        candidates = []
        if suffix:
            candidates.append(self._cache_dir / f"{uri_hash}{suffix}")
        candidates.extend(self._cache_dir.glob(f"{uri_hash}.*"))
        # Preserve deterministic order while removing duplicates.
        return list(dict.fromkeys(candidates))

    def purge_cache(self) -> dict[str, int]:
        file_paths = [path for path in self._cache_dir.glob("*") if path.is_file()]
        deleted_files = 0
        deleted_bytes = 0
        for file_path in file_paths:
            try:
                deleted_bytes += int(file_path.stat().st_size)
                file_path.unlink(missing_ok=True)
                deleted_files += 1
            except OSError as exc:
                log_exception(
                    logger,
                    "asset_cache_purge_file_failed",
                    exc,
                    local_path=str(file_path),
                    status="failed",
                )

        log_event(
            logger,
            "asset_cache_purged",
            cache_dir=str(self._cache_dir),
            deleted_file_count=deleted_files,
            deleted_bytes=deleted_bytes,
            status="completed",
        )
        return {
            "before_files": len(file_paths),
            "after_files": len([path for path in self._cache_dir.glob("*") if path.is_file()]),
            "deleted_files": deleted_files,
            "deleted_bytes": deleted_bytes,
        }

    def _load_from_local_path(
        self,
        *,
        local_path: str,
        storage_uri: str,
        mime_type: str | None,
    ) -> LoadedAsset:
        path = Path(local_path)
        if not path.exists():
            raise FileNotFoundError(f"Asset not found: {local_path}")
        return LoadedAsset(
            local_path=str(path),
            storage_uri=storage_uri,
            mime_type=mime_type,
            filename=path.name,
            file_size_bytes=path.stat().st_size,
            temporary=False,
        )
