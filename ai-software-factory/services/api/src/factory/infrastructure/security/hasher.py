"""Adaptador de `PasswordHasher` sobre las primitivas PBKDF2."""

from __future__ import annotations

from factory.infrastructure.security.passwords import hash_password, needs_rehash, verify_password


class Pbkdf2PasswordHasher:
    """Implementación de `PasswordHasher` con PBKDF2-SHA256."""

    def hash(self, password: str) -> str:
        return hash_password(password)

    def verify(self, password: str, encoded: str) -> bool:
        return verify_password(password, encoded)

    def needs_rehash(self, encoded: str) -> bool:
        return needs_rehash(encoded)
