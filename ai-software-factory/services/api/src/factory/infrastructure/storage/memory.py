"""Almacenamiento en memoria: pruebas y demostraciones locales."""

from __future__ import annotations

from factory.domain.errors import NotFoundError


class InMemoryObjectStorage:
    """Implementación de `ObjectStorage` respaldada por un diccionario."""

    def __init__(self) -> None:
        self._objects: dict[str, bytes] = {}

    async def put(self, key: str, data: bytes, *, content_type: str = "application/zip") -> str:
        self._objects[key] = data
        return key

    async def get(self, key: str) -> bytes:
        if key not in self._objects:
            raise NotFoundError(f"El objeto {key!r} no existe")
        return self._objects[key]

    async def delete(self, key: str) -> None:
        self._objects.pop(key, None)

    async def exists(self, key: str) -> bool:
        return key in self._objects

    async def presigned_url(self, key: str, *, expires_seconds: int = 3600) -> str:
        if key not in self._objects:
            raise NotFoundError(f"El objeto {key!r} no existe")
        return f"memory://{key}?expires={expires_seconds}"

    @property
    def keys(self) -> list[str]:
        return sorted(self._objects)
