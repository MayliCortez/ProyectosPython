"""Registro, inicio de sesión y perfil del usuario autenticado."""

from __future__ import annotations

from fastapi import APIRouter, status

from factory.application.services.auth_service import AuthResult
from factory.interfaces.http.deps import AuthServiceDep, CurrentUser
from factory.interfaces.http.schemas import LoginRequest, RegisterRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["autenticación"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, auth: AuthServiceDep) -> TokenResponse:
    """Crea la organización y su primer usuario, que queda como propietario."""
    result = await auth.register(
        email=payload.email,
        password=payload.password,
        organization_name=payload.organization_name,
        full_name=payload.full_name,
    )
    return _token_response(result)


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, auth: AuthServiceDep) -> TokenResponse:
    """Emite un token para un usuario existente."""
    result = await auth.login(email=payload.email, password=payload.password)
    return _token_response(result)


@router.get("/me")
async def me(user: CurrentUser) -> dict[str, str]:
    """Perfil del usuario del token."""
    return {
        "id": user.id,
        "email": str(user.email),
        "full_name": user.full_name,
        "role": str(user.role),
        "organization_id": user.organization_id,
    }


def _token_response(result: AuthResult) -> TokenResponse:
    """Traduce el resultado del servicio a la respuesta pública."""
    return TokenResponse(
        access_token=result.token,
        expires_in=result.expires_in,
        user_id=result.user_id,
        organization_id=result.organization_id,
        role=result.role,
        email=result.email,
    )
