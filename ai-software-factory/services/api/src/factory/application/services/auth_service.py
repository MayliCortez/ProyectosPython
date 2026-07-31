"""Registro, inicio de sesión y resolución del usuario a partir del token."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from factory.application.ports.security import PasswordHasher, TokenIssuer
from factory.application.ports.uow import UnitOfWork
from factory.domain.entities import Organization, User, UserRole
from factory.domain.errors import ConflictError, PermissionDeniedError
from factory.domain.value_objects import Email

UnitOfWorkFactory = Callable[[], UnitOfWork]


@dataclass(frozen=True, slots=True)
class AuthResult:
    """Credenciales emitidas tras un registro o un inicio de sesión correcto."""

    token: str
    expires_in: int
    user_id: str
    organization_id: str
    role: str
    email: str


class AuthService:
    """Autenticación de la plataforma.

    El registro crea también la organización: el primer usuario es su propietario. Los
    inicios de sesión fallidos devuelven siempre el mismo error, sin distinguir entre
    correo inexistente y contraseña incorrecta, para no filtrar qué cuentas existen.
    """

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        tokens: TokenIssuer,
        hasher: PasswordHasher,
    ) -> None:
        self._uow_factory = uow_factory
        self._tokens = tokens
        self._hasher = hasher

    async def register(
        self,
        *,
        email: str,
        password: str,
        organization_name: str,
        full_name: str = "",
    ) -> AuthResult:
        if len(password) < 8:
            raise ConflictError("La contraseña debe tener al menos 8 caracteres")

        address = Email(email)
        async with self._uow_factory() as uow:
            if await uow.users.get_by_email(str(address)) is not None:
                raise ConflictError("Ya existe una cuenta con ese correo electrónico")

            organization = Organization.create(organization_name)
            await uow.organizations.add(organization)

            user = User(
                organization_id=organization.id,
                email=address,
                password_hash=self._hasher.hash(password),
                full_name=full_name.strip(),
                role=UserRole.OWNER,
            )
            await uow.users.add(user)
            return self._issue(user)

    async def login(self, *, email: str, password: str) -> AuthResult:
        async with self._uow_factory() as uow:
            user = await uow.users.get_by_email(email.strip().lower())
            if user is None or not self._hasher.verify(password, user.password_hash):
                raise PermissionDeniedError("Credenciales incorrectas")
            if not user.is_active:
                raise PermissionDeniedError("La cuenta está desactivada")
            return self._issue(user)

    async def user_from_token(self, token: str) -> User:
        """Resuelve el usuario del token; lanza si no existe o está desactivado."""
        claims = self._tokens.verify(token)
        async with self._uow_factory() as uow:
            user = await uow.users.get(claims.user_id)
            if user is None or not user.is_active:
                raise PermissionDeniedError("El usuario del token ya no es válido")
            return user

    def _issue(self, user: User) -> AuthResult:
        token, expires_in = self._tokens.issue(user)
        return AuthResult(
            token=token,
            expires_in=expires_in,
            user_id=user.id,
            organization_id=user.organization_id,
            role=str(user.role),
            email=str(user.email),
        )
