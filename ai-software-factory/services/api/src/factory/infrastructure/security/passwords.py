"""Hash y verificación de contraseñas con PBKDF2-SHA256.

Se usa la biblioteca estándar en lugar de una dependencia externa: PBKDF2 con un
número alto de iteraciones y sal por usuario es adecuado y elimina una dependencia
nativa del despliegue. El formato guardado incluye el algoritmo y las iteraciones,
de modo que subir el coste más adelante no invalida los hashes existentes.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

_ALGORITHM = "pbkdf2_sha256"
_ITERATIONS = 480_000
_SALT_BYTES = 16


def hash_password(password: str, *, iterations: int = _ITERATIONS) -> str:
    """Devuelve `pbkdf2_sha256$iteraciones$sal$hash`."""
    if not password:
        raise ValueError("La contraseña no puede estar vacía")
    salt = secrets.token_hex(_SALT_BYTES)
    digest = _derive(password, salt, iterations)
    return f"{_ALGORITHM}${iterations}${salt}${digest}"


def verify_password(password: str, encoded: str) -> bool:
    """Comprueba la contraseña en tiempo constante frente a un hash almacenado."""
    try:
        algorithm, raw_iterations, salt, digest = encoded.split("$", 3)
        iterations = int(raw_iterations)
    except (ValueError, AttributeError):
        return False
    if algorithm != _ALGORITHM:
        return False
    candidate = _derive(password, salt, iterations)
    return hmac.compare_digest(candidate, digest)


def needs_rehash(encoded: str, *, iterations: int = _ITERATIONS) -> bool:
    """Indica si el hash se generó con un coste inferior al actual."""
    try:
        _, raw_iterations, _, _ = encoded.split("$", 3)
        return int(raw_iterations) < iterations
    except (ValueError, AttributeError):
        return True


def _derive(password: str, salt: str, iterations: int) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations
    ).hex()
