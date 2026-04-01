from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

import boto3
from boto3.s3.transfer import TransferConfig
from botocore.config import Config
from botocore.exceptions import ClientError

from backend.core.config import settings
from backend.core.exceptions import ConfigurationAppError
from backend.core.logging import get_logger, log_exception, summarize_storage_reference

logger = get_logger(__name__)


@dataclass(slots=True)
class ObjectStorageSettings:
    bucket_name: str
    region: str
    endpoint_url: str | None
    public_base_url: str | None
    access_key_id: str | None
    secret_access_key: str | None
    session_token: str | None
    provider: str


@dataclass(slots=True)
class UploadedObject:
    bucket_name: str
    storage_key: str
    storage_uri: str
    file_size_bytes: int
    sha256: str


@dataclass(slots=True)
class ObjectHead:
    bucket_name: str
    storage_key: str
    file_size_bytes: int
    content_type: str | None
    etag: str | None


def resolve_object_storage_settings() -> ObjectStorageSettings:
    use_r2 = bool(settings.r2_bucket_name or settings.r2_account_id or settings.r2_endpoint_url)
    endpoint_url = settings.s3_endpoint_url
    region = settings.aws_region
    access_key_id = settings.aws_access_key_id
    secret_access_key = settings.aws_secret_access_key
    public_base_url = settings.s3_public_base_url
    bucket_name = settings.s3_bucket_name

    if use_r2:
        endpoint_url = (
            f"https://{settings.r2_account_id}.r2.cloudflarestorage.com"
            if settings.r2_account_id
            else settings.r2_endpoint_url
        )
        region = "auto"
        access_key_id = settings.r2_access_key_id
        secret_access_key = settings.r2_secret_access_key
        public_base_url = settings.r2_public_base_url
        bucket_name = settings.r2_bucket_name

        if not endpoint_url or not bucket_name or not access_key_id or not secret_access_key:
            raise ConfigurationAppError(
                "Cloudflare R2 is enabled but the bucket, endpoint, or S3-compatible access keys are missing."
            )
        if access_key_id.startswith("cfat_") or secret_access_key.startswith("cfat_"):
            raise ConfigurationAppError(
                "Cloudflare R2 credentials are misconfigured. Use an R2 S3 Access Key ID and Secret Access Key, not a Cloudflare API token."
            )
        if len(access_key_id) != 32:
            raise ConfigurationAppError(
                "Cloudflare R2 access key ID is invalid. R2 S3 Access Key IDs are 32 characters long."
            )

    return ObjectStorageSettings(
        bucket_name=bucket_name,
        region=region,
        endpoint_url=endpoint_url,
        public_base_url=public_base_url,
        access_key_id=access_key_id,
        secret_access_key=secret_access_key,
        session_token=None if use_r2 else settings.aws_session_token,
        provider="cloudflare-r2" if use_r2 else "s3-compatible",
    )


def build_s3_client():
    storage_settings = resolve_object_storage_settings()
    return boto3.client(
        "s3",
        region_name=storage_settings.region,
        endpoint_url=storage_settings.endpoint_url,
        aws_access_key_id=storage_settings.access_key_id,
        aws_secret_access_key=storage_settings.secret_access_key,
        aws_session_token=storage_settings.session_token,
        config=Config(signature_version="s3v4"),
    )


class ObjectStorageService:
    def __init__(self) -> None:
        storage_settings = resolve_object_storage_settings()
        self.bucket_name = storage_settings.bucket_name
        self.region = storage_settings.region
        self.endpoint_url = storage_settings.endpoint_url
        self.public_base_url = storage_settings.public_base_url
        self.provider = storage_settings.provider
        self.client = build_s3_client()
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
        if not mime_type:
            return False
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

    def build_analysis_object_key(
        self,
        *,
        user_id: str,
        asset_id: str,
        original_filename: str,
    ) -> str:
        filename = self._sanitize_filename(original_filename)
        suffix = Path(filename).suffix or ".bin"
        return f"raw/{user_id}/{asset_id}/original{suffix.lower()}"

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

            def close(self) -> None:
                self.inner.close()

        wrapper = HashingFileWrapper(fileobj)
        extra_args: dict[str, str] | None = {"ContentType": content_type} if content_type else None

        try:
            self.client.upload_fileobj(
                Fileobj=wrapper,
                Bucket=bucket_name,
                Key=storage_key,
                ExtraArgs=extra_args,
                Config=self.transfer_config,
            )
        except ClientError as exc:
            error = exc.response.get("Error", {})
            code = str(error.get("Code") or "Unknown")
            message = str(error.get("Message") or "Object storage upload failed.")
            if self.provider == "cloudflare-r2":
                raise ConfigurationAppError(f"Cloudflare R2 upload failed: {message} ({code}).") from exc
            raise

        return UploadedObject(
            bucket_name=bucket_name,
            storage_key=storage_key,
            storage_uri=f"s3://{bucket_name}/{storage_key}",
            file_size_bytes=total_bytes,
            sha256=hasher.hexdigest(),
        )

    def delete_object(self, *, bucket_name: str, storage_key: str) -> None:
        self.client.delete_object(Bucket=bucket_name, Key=storage_key)

    def head_object(self, *, bucket_name: str, storage_key: str) -> ObjectHead:
        response = self.client.head_object(Bucket=bucket_name, Key=storage_key)
        return ObjectHead(
            bucket_name=bucket_name,
            storage_key=storage_key,
            file_size_bytes=int(response.get("ContentLength") or 0),
            content_type=response.get("ContentType"),
            etag=(response.get("ETag") or "").strip('"') or None,
        )

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
                ExpiresIn=expires_in_seconds or settings.upload_presign_expires_seconds,
            )
        except Exception as exc:
            log_exception(
                logger,
                "presigned_upload_failed",
                exc,
                provider=self.provider,
                status="failed",
                **summarize_storage_reference(bucket_name, storage_key),
            )
            return None

    def generate_presigned_get_url(
        self,
        *,
        bucket_name: str,
        storage_key: str,
        expires_in_seconds: int = 3600,
    ) -> str | None:
        try:
            return self.client.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket_name, "Key": storage_key},
                ExpiresIn=expires_in_seconds,
            )
        except Exception as exc:
            log_exception(
                logger,
                "presigned_download_failed",
                exc,
                provider=self.provider,
                status="failed",
                **summarize_storage_reference(bucket_name, storage_key),
            )
            return None

    def get_object_bytes(
        self,
        *,
        bucket_name: str,
        storage_key: str,
    ) -> tuple[bytes, str | None]:
        response = self.client.get_object(Bucket=bucket_name, Key=storage_key)
        body = response["Body"].read()
        return body, response.get("ContentType")

    def build_object_url(self, *, bucket_name: str, storage_key: str) -> str:
        if self.public_base_url:
            return f"{self.public_base_url.rstrip('/')}/{storage_key}"
        if self.endpoint_url:
            return f"{self.endpoint_url.rstrip('/')}/{bucket_name}/{storage_key}"
        return f"https://{bucket_name}.s3.{self.region}.amazonaws.com/{storage_key}"

    def object_exists(self, *, bucket_name: str, storage_key: str) -> bool:
        try:
            self.client.head_object(Bucket=bucket_name, Key=storage_key)
            return True
        except ClientError:
            return False


S3StorageService = ObjectStorageService
