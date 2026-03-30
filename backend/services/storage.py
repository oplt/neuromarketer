from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

import boto3
from boto3.s3.transfer import TransferConfig
from botocore.config import Config

from backend.core.config import settings


@dataclass(slots=True)
class UploadedObject:
    bucket_name: str
    storage_key: str
    storage_uri: str
    file_size_bytes: int
    sha256: str


class S3StorageService:
    def __init__(self) -> None:
        self.bucket_name = settings.s3_bucket_name
        self.region = settings.aws_region
        self.endpoint_url = settings.s3_endpoint_url
        self.public_base_url = settings.s3_public_base_url
        self.client = boto3.client(
            "s3",
            region_name=self.region,
            endpoint_url=self.endpoint_url,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            aws_session_token=settings.aws_session_token,
            config=Config(signature_version="s3v4"),
        )
        self.transfer_config = TransferConfig(
            multipart_threshold=8 * 1024 * 1024,
            multipart_chunksize=8 * 1024 * 1024,
            max_concurrency=4,
            use_threads=True,
        )

    @staticmethod
    def _sanitize_filename(filename: str) -> str:
        safe = filename.replace("\\", "_").replace("/", "_").strip()
        return safe or "upload.bin"

    @staticmethod
    def is_allowed_mime_type(mime_type: str | None) -> bool:
        if mime_type is None:
            return True
        return any(mime_type.startswith(prefix) for prefix in settings.allowed_upload_mime_prefixes)

    def build_storage_key(
        self,
        *,
        project_id: str,
        artifact_kind: str,
        original_filename: str,
    ) -> str:
        filename = self._sanitize_filename(original_filename)
        token = secrets.token_hex(8)
        ext = Path(filename).suffix
        stem = Path(filename).stem[:80] or "file"
        return f"projects/{project_id}/{artifact_kind}/{stem}-{token}{ext}"

    def upload_fileobj(
        self,
        *,
        fileobj: BinaryIO,
        bucket_name: str,
        storage_key: str,
        content_type: str | None = None,
    ) -> UploadedObject:
        hasher = hashlib.sha256()
        total_bytes = 0

        class HashingFileWrapper:
            def __init__(self, inner: BinaryIO) -> None:
                self.inner = inner

            def read(self, size: int = -1) -> bytes:
                nonlocal total_bytes
                chunk = self.inner.read(size)
                if chunk:
                    hasher.update(chunk)
                    total_bytes += len(chunk)
                return chunk

            def seek(self, offset: int, whence: int = 0) -> int:
                return self.inner.seek(offset, whence)

            def tell(self) -> int:
                return self.inner.tell()

        wrapper = HashingFileWrapper(fileobj)
        extra_args: dict[str, str] | None = {"ContentType": content_type} if content_type else None

        self.client.upload_fileobj(
            Fileobj=wrapper,
            Bucket=bucket_name,
            Key=storage_key,
            ExtraArgs=extra_args,
            Config=self.transfer_config,
        )

        return UploadedObject(
            bucket_name=bucket_name,
            storage_key=storage_key,
            storage_uri=f"s3://{bucket_name}/{storage_key}",
            file_size_bytes=total_bytes,
            sha256=hasher.hexdigest(),
        )

    def delete_object(self, *, bucket_name: str, storage_key: str) -> None:
        self.client.delete_object(Bucket=bucket_name, Key=storage_key)

    def generate_presigned_put_url(
        self,
        *,
        bucket_name: str,
        storage_key: str,
        expires_in_seconds: int = 900,
        content_type: str | None = None,
    ) -> str | None:
        params: dict[str, str] = {"Bucket": bucket_name, "Key": storage_key}
        if content_type:
            params["ContentType"] = content_type
        try:
            return self.client.generate_presigned_url(
                "put_object",
                Params=params,
                ExpiresIn=expires_in_seconds,
            )
        except Exception:
            return None

    def build_object_url(self, *, bucket_name: str, storage_key: str) -> str:
        if self.public_base_url:
            return f"{self.public_base_url.rstrip('/')}/{storage_key}"
        if self.endpoint_url:
            return f"{self.endpoint_url.rstrip('/')}/{bucket_name}/{storage_key}"
        return f"https://{bucket_name}.s3.{self.region}.amazonaws.com/{storage_key}"
