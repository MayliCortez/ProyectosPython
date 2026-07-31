"""Almacenamiento de artefactos generados."""

from factory.infrastructure.storage.memory import InMemoryObjectStorage
from factory.infrastructure.storage.s3 import S3ObjectStorage

__all__ = ["InMemoryObjectStorage", "S3ObjectStorage"]
