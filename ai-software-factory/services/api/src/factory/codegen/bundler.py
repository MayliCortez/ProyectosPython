"""Empaqueta los artefactos generados en un ZIP reproducible."""

from __future__ import annotations

import io
import zipfile
from collections.abc import Iterable

from factory.domain.value_objects import Artifact

#: Fecha fija para que dos builds con el mismo contenido produzcan el mismo ZIP.
_FIXED_TIMESTAMP = (2026, 1, 1, 0, 0, 0)


def bundle_artifacts(artifacts: Iterable[Artifact], *, root: str = "") -> bytes:
    """Comprime los artefactos en un ZIP determinista.

    El determinismo importa: permite comparar dos construcciones por hash y saber si
    el resultado cambió realmente, sin ruido de marcas de tiempo.
    """
    prefix = f"{root.strip('/')}/" if root else ""
    buffer = io.BytesIO()

    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for artifact in sorted(artifacts, key=lambda item: item.path):
            info = zipfile.ZipInfo(f"{prefix}{artifact.path}", date_time=_FIXED_TIMESTAMP)
            info.external_attr = (0o755 if artifact.path.endswith(".sh") else 0o644) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, artifact.content.encode("utf-8"))

    return buffer.getvalue()
