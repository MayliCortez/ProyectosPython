"""Almacenamiento compatible con S3 (AWS S3, MinIO, R2…)."""

from __future__ import annotations

import asyncio
import logging
from functools import partial
from typing import Any

import boto3
from botocore.exceptions import ClientError

from factory.domain.errors import NotFoundError

logger = logging.getLogger(__name__)


class S3ObjectStorage:
    """Implementación de `ObjectStorage` sobre boto3.

    boto3 es síncrono; cada operación se delega al *executor* por defecto para no
    bloquear el bucle de eventos. Es suficiente porque los bundles se escriben una vez
    por construcción, no en el camino caliente de las peticiones.
    """

    def __init__(
        self,
        *,
        bucket: str,
        endpoint_url: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        region: str = "us-east-1",
    ) -> None:
        self._bucket = bucket
        self._client: Any = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
        )

    async def _run(self, func: Any, *args: Any, **kwargs: Any) -> Any:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, partial(func, *args, **kwargs))

    async def ensure_bucket(self) -> None:
        """Crea el bucket si no existe. Idempotente."""
        try:
            await self._run(self._client.head_bucket, Bucket=self._bucket)
        except ClientError:
            logger.info("Creando el bucket %s", self._bucket)
            await self._run(self._client.create_bucket, Bucket=self._bucket)

    async def put(self, key: str, data: bytes, *, content_type: str = "application/zip") -> str:
        await self._run(
            self._client.put_object,
            Bucket=self._bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
        )
        return key

    async def get(self, key: str) -> bytes:
        try:
            response = await self._run(self._client.get_object, Bucket=self._bucket, Key=key)
        except ClientError as exc:
            raise NotFoundError(f"El objeto {key!r} no existe") from exc
        return bytes(response["Body"].read())

    async def delete(self, key: str) -> None:
        await self._run(self._client.delete_object, Bucket=self._bucket, Key=key)

    async def exists(self, key: str) -> bool:
        try:
            await self._run(self._client.head_object, Bucket=self._bucket, Key=key)
        except ClientError:
            return False
        return True

    async def presigned_url(self, key: str, *, expires_seconds: int = 3600) -> str:
        url = await self._run(
            self._client.generate_presigned_url,
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=expires_seconds,
        )
        return str(url)
