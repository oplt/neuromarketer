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
