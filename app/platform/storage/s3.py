"""S3 / MinIO object store (optional backend).

Requires boto3 (``pip install boto3``), which is NOT a default dependency since
the platform uses local-disk storage by default. boto3 is imported lazily, so
this module loads without it; selecting the S3 backend without boto3 raises a
clear error.
"""
from __future__ import annotations

from functools import cached_property

from app.config import settings
from app.platform.observability.logging import get_logger
from app.platform.storage.base import ObjectStore

logger = get_logger(__name__)


class S3ObjectStore(ObjectStore):
    def __init__(self, bucket: str | None = None) -> None:
        self._bucket = bucket or settings.s3_bucket

    @cached_property
    def _client(self):
        try:
            import boto3
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "The S3 object-storage backend requires boto3. Install it with "
                "`pip install boto3`, or use OBJECT_STORE_BACKEND=local."
            ) from exc
        return boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint or None,
            region_name=settings.s3_region,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
        )

    def put(self, key: str, data: bytes, content_type: str | None = None) -> str:
        extra = {"ContentType": content_type} if content_type else {}
        self._client.put_object(Bucket=self._bucket, Key=key, Body=data, **extra)
        logger.info("Stored %d bytes at s3://%s/%s", len(data), self._bucket, key)
        return f"s3://{self._bucket}/{key}"

    def get(self, key: str) -> bytes:
        resp = self._client.get_object(Bucket=self._bucket, Key=key)
        return resp["Body"].read()

    def exists(self, key: str) -> bool:
        from botocore.exceptions import ClientError

        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
            return True
        except ClientError:
            return False

    def delete(self, key: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=key)

    def presigned_url(self, key: str, expires_in: int = 3600) -> str:
        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=expires_in,
        )
