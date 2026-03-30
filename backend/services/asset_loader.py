from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

import boto3
from botocore.config import Config

from backend.core.config import settings


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
        self.s3_client = boto3.client(
            "s3",
            region_name=settings.aws_region,
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            aws_session_token=settings.aws_session_token,
            config=Config(signature_version="s3v4"),
        )

    def load(self, *, storage_uri: str, mime_type: str | None = None) -> LoadedAsset:
        if storage_uri.startswith("s3://"):
            return self._load_from_s3(storage_uri=storage_uri, mime_type=mime_type)
        if storage_uri.startswith("file://"):
            path = storage_uri.replace("file://", "", 1)
            return self._load_from_local_path(local_path=path, storage_uri=storage_uri, mime_type=mime_type)
        if storage_uri.startswith("/"):
            return self._load_from_local_path(
                local_path=storage_uri,
                storage_uri=f"file://{storage_uri}",
                mime_type=mime_type,
            )
        raise ValueError(f"Unsupported storage URI: {storage_uri}")

    def _load_from_s3(self, *, storage_uri: str, mime_type: str | None) -> LoadedAsset:
        without_scheme = storage_uri.replace("s3://", "", 1)
        bucket_name, storage_key = without_scheme.split("/", 1)
        suffix = Path(storage_key).suffix
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        tmp.close()

        self.s3_client.download_file(bucket_name, storage_key, tmp.name)
        file_size_bytes = os.path.getsize(tmp.name)
        return LoadedAsset(
            local_path=tmp.name,
            storage_uri=storage_uri,
            mime_type=mime_type,
            filename=Path(storage_key).name,
            file_size_bytes=file_size_bytes,
            temporary=True,
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
