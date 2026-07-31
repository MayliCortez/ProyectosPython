"""Puerto de almacenamiento de objetos compatible con S3."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ObjectStorage(Protocol):
    """Guarda y recupera los bundles de proyectos generados."""

    async def put(self, key: str, data: bytes, *, content_type: str = "application/zip") -> str:
        """Guarda el objeto y devuelve su clave definitiva."""
        ...

    async def get(self, key: str) -> bytes:
        """Recupera el contenido del objeto."""
        ...

    async def delete(self, key: str) -> None:
        """Elimina el objeto si existe."""
        ...

    async def exists(self, key: str) -> bool:
        """Indica si la clave existe."""
        ...

    async def presigned_url(self, key: str, *, expires_seconds: int = 3600) -> str:
        """URL temporal de descarga directa para el navegador."""
        ...
