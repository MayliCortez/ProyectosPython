"""Puertos de seguridad: hash de contraseñas y emisión de tokens."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from factory.domain.entities import User


@runtime_checkable
class PasswordHasher(Protocol):
    """Deriva y verifica hashes de contraseña."""

    def hash(self, password: str) -> str: ...

    def verify(self, password: str, encoded: str) -> bool: ...


@runtime_checkable
class Claims(Protocol):
    """Identidad extraída de un token ya verificado."""

    @property
    def user_id(self) -> str: ...

    @property
    def organization_id(self) -> str: ...

    @property
    def role(self) -> str: ...


@runtime_checkable
class TokenIssuer(Protocol):
    """Emite y valida los tokens de sesión."""

    def issue(self, user: User) -> tuple[str, int]:
        """Devuelve `(token, segundos_de_validez)`."""
        ...

    def verify(self, token: str) -> Claims:
        """Devuelve las reclamaciones verificadas; lanza si el token no es válido."""
        ...
