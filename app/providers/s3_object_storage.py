"""S3-compatible object storage adapter for private knowledge documents."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import timedelta
from typing import Any
from uuid import uuid4

import boto3  # type: ignore[import-untyped]
from botocore.config import Config  # type: ignore[import-untyped]
from botocore.exceptions import BotoCoreError, ClientError  # type: ignore[import-untyped]

from app.config import Settings
from app.errors import ServiceUnavailableError
from app.providers.object_storage import ObjectMetadata


class S3ObjectStorageProvider:
    def __init__(self, settings: Settings) -> None:
        self._bucket = settings.object_storage_bucket
        access_key = (
            settings.object_storage_access_key.get_secret_value()
            if settings.object_storage_access_key is not None
            else None
        )
        secret_key = (
            settings.object_storage_secret_key.get_secret_value()
            if settings.object_storage_secret_key is not None
            else None
        )
        client_arguments: dict[str, Any] = {
            "region_name": settings.object_storage_region,
            "aws_access_key_id": access_key,
            "aws_secret_access_key": secret_key,
            "config": Config(
                connect_timeout=settings.object_storage_readiness_timeout_seconds,
                read_timeout=settings.object_storage_readiness_timeout_seconds,
                retries={"max_attempts": 1, "mode": "standard"},
            ),
        }
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.object_storage_endpoint,
            use_ssl=settings.object_storage_secure,
            **client_arguments,
        )
        external_endpoint = (
            settings.object_storage_external_endpoint or settings.object_storage_endpoint
        )
        self._download_client = boto3.client(
            "s3",
            endpoint_url=external_endpoint,
            use_ssl=external_endpoint.startswith("https://"),
            **client_arguments,
        )

    async def check_readiness(self) -> None:
        """以应用账户执行 put/head/delete，验证 bucket 的最小实际权限。"""

        object_key = f"health/readiness/{uuid4()}"
        stored = False
        try:
            await asyncio.to_thread(
                self._client.put_object,
                Bucket=self._bucket,
                Key=object_key,
                Body=b"ready",
                ContentType="text/plain",
            )
            stored = True
            response = await asyncio.to_thread(
                self._client.head_object,
                Bucket=self._bucket,
                Key=object_key,
            )
            if int(response["ContentLength"]) != 5:
                raise ServiceUnavailableError("object storage readiness probe failed")
            await asyncio.to_thread(
                self._client.delete_object,
                Bucket=self._bucket,
                Key=object_key,
            )
            stored = False
        except (BotoCoreError, ClientError, KeyError, TypeError, ValueError) as exc:
            raise ServiceUnavailableError("object storage is unavailable") from exc
        finally:
            if stored:
                try:
                    await asyncio.to_thread(
                        self._client.delete_object,
                        Bucket=self._bucket,
                        Key=object_key,
                    )
                except (BotoCoreError, ClientError):
                    pass

    async def put(
        self,
        object_key: str,
        content: bytes,
        content_type: str,
        *,
        metadata: Mapping[str, str] | None = None,
        checksum_sha256: str | None = None,
    ) -> ObjectMetadata:
        arguments: dict[str, Any] = {
            "Bucket": self._bucket,
            "Key": object_key,
            "Body": content,
            "ContentType": content_type,
            "Metadata": dict(metadata or {}),
        }
        if checksum_sha256 is not None:
            arguments["ChecksumAlgorithm"] = "SHA256"
        try:
            response = await asyncio.to_thread(self._client.put_object, **arguments)
        except (BotoCoreError, ClientError) as exc:
            raise ServiceUnavailableError("object storage is unavailable") from exc
        return ObjectMetadata(
            object_key=object_key,
            content_length=len(content),
            content_type=content_type,
            etag=str(response.get("ETag", "")).strip('"') or None,
            checksum_sha256=checksum_sha256,
            metadata=dict(metadata or {}),
        )

    async def get(self, object_key: str) -> bytes:
        try:
            response = await asyncio.to_thread(
                self._client.get_object, Bucket=self._bucket, Key=object_key
            )
            return await asyncio.to_thread(response["Body"].read)
        except (BotoCoreError, ClientError) as exc:
            raise ServiceUnavailableError("object storage is unavailable") from exc

    async def head(self, object_key: str) -> ObjectMetadata:
        try:
            response = await asyncio.to_thread(
                self._client.head_object, Bucket=self._bucket, Key=object_key
            )
        except (BotoCoreError, ClientError) as exc:
            raise ServiceUnavailableError("object storage is unavailable") from exc
        return ObjectMetadata(
            object_key=object_key,
            content_length=int(response["ContentLength"]),
            content_type=response.get("ContentType"),
            etag=str(response.get("ETag", "")).strip('"') or None,
            checksum_sha256=response.get("ChecksumSHA256"),
            metadata=dict(response.get("Metadata", {})),
        )

    async def delete(self, object_key: str) -> None:
        try:
            await asyncio.to_thread(self._client.delete_object, Bucket=self._bucket, Key=object_key)
        except (BotoCoreError, ClientError) as exc:
            raise ServiceUnavailableError("object storage is unavailable") from exc

    async def create_presigned_download_url(
        self, object_key: str, *, expires_in: timedelta
    ) -> str:
        try:
            return await asyncio.to_thread(
                self._download_client.generate_presigned_url,
                "get_object",
                Params={"Bucket": self._bucket, "Key": object_key},
                ExpiresIn=int(expires_in.total_seconds()),
            )
        except (BotoCoreError, ClientError) as exc:
            raise ServiceUnavailableError("object storage is unavailable") from exc
