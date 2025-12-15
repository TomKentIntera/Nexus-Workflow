from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

from minio import Minio
from minio.error import S3Error

from ..config import get_settings


class MinioConfigError(RuntimeError):
    """Raised when MinIO is not configured correctly."""


class MinioFetchError(RuntimeError):
    """Raised when an object cannot be fetched from MinIO."""


@dataclass(frozen=True)
class MinioObject:
    bucket: str
    object_name: str
    content_type: Optional[str]
    data: bytes


def _build_minio_client() -> Minio:
    settings = get_settings()
    if not settings.minio_endpoint:
        raise MinioConfigError("WF_MINIO_ENDPOINT is not configured in the API service .env")
    if not settings.minio_access_key or not settings.minio_secret_key:
        raise MinioConfigError(
            "WF_MINIO_ACCESS_KEY / WF_MINIO_SECRET_KEY are not configured in the API service .env"
        )

    parsed = urlparse(str(settings.minio_endpoint))
    if not parsed.hostname:
        raise MinioConfigError("WF_MINIO_ENDPOINT must include a hostname (e.g. http://minio:9000)")
    endpoint = parsed.netloc or parsed.hostname
    secure = parsed.scheme == "https"

    return Minio(
        endpoint=endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=secure,
    )


def get_object_bytes(*, object_name: str, bucket: str | None = None) -> MinioObject:
    settings = get_settings()
    bucket_name = bucket or settings.minio_bucket
    client = _build_minio_client()

    try:
        response = client.get_object(bucket_name, object_name)
        try:
            data = response.read()
            content_type = response.getheader("Content-Type")
        finally:
            response.close()
            response.release_conn()
    except S3Error as exc:
        raise MinioFetchError(f"MinIO error fetching '{bucket_name}/{object_name}': {exc}") from exc
    except Exception as exc:  # pragma: no cover
        raise MinioFetchError(f"Error fetching '{bucket_name}/{object_name}' from MinIO: {exc}") from exc

    return MinioObject(
        bucket=bucket_name,
        object_name=object_name,
        content_type=content_type,
        data=data,
    )

