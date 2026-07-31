"""Emisión y verificación de tokens JWT."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt

from factory.domain.entities import User
from factory.domain.errors import PermissionDeniedError


@dataclass(frozen=True, slots=True)
class TokenClaims:
    """Contenido útil de un token ya verificado."""

    user_id: str
    organization_id: str
    role: str
    expires_at: datetime


class TokenService:
    """Firma y valida los tokens de sesión de la plataforma."""

    def __init__(self, *, secret: str, algorithm: str = "HS256", ttl_minutes: int = 720) -> None:
        self._secret = secret
        self._algorithm = algorithm
        self._ttl = timedelta(minutes=ttl_minutes)

    def issue(self, user: User) -> tuple[str, int]:
        """Devuelve `(token, segundos_de_validez)` para el usuario dado."""
        now = datetime.now(UTC)
        expires_at = now + self._ttl
        payload = {
            "sub": user.id,
            "org": user.organization_id,
            "role": str(user.role),
            "email": str(user.email),
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
        }
        token = jwt.encode(payload, self._secret, algorithm=self._algorithm)
        return token, int(self._ttl.total_seconds())

    def verify(self, token: str) -> TokenClaims:
        """Valida firma y caducidad; lanza si el token no sirve."""
        try:
            payload = jwt.decode(token, self._secret, algorithms=[self._algorithm])
        except jwt.ExpiredSignatureError as exc:
            raise PermissionDeniedError("El token ha caducado") from exc
        except jwt.PyJWTError as exc:
            raise PermissionDeniedError("Token inválido") from exc

        return TokenClaims(
            user_id=str(payload["sub"]),
            organization_id=str(payload["org"]),
            role=str(payload.get("role", "developer")),
            expires_at=datetime.fromtimestamp(payload["exp"], tz=UTC),
        )
