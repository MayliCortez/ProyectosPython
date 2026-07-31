"""Errores de negocio. Las capas exteriores los traducen a códigos HTTP."""

from __future__ import annotations


class DomainError(Exception):
    """Raíz de todos los errores de negocio."""

    code = "domain_error"

    def __init__(self, message: str, *, details: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class NotFoundError(DomainError):
    """La entidad solicitada no existe o no es visible para el solicitante."""

    code = "not_found"


class ValidationError(DomainError):
    """Los datos aportados no cumplen una invariante del dominio."""

    code = "validation_error"


class ConflictError(DomainError):
    """La operación choca con el estado actual de la entidad."""

    code = "conflict"


class PermissionDeniedError(DomainError):
    """El actor no pertenece a la organización dueña del recurso."""

    code = "permission_denied"


class InvalidTransitionError(ConflictError):
    """Transición de estado no permitida por la máquina de estados."""

    code = "invalid_transition"

    def __init__(self, entity: str, current: str, target: str) -> None:
        super().__init__(
            f"{entity} no puede pasar de '{current}' a '{target}'",
            details={"entity": entity, "current": current, "target": target},
        )


class ModuleDependencyError(ConflictError):
    """El grafo de módulos quedaría inconsistente."""

    code = "module_dependency_error"


class AgentExecutionError(DomainError):
    """Un agente no pudo completar su etapa."""

    code = "agent_execution_error"

    def __init__(self, agent: str, message: str) -> None:
        super().__init__(f"[{agent}] {message}", details={"agent": agent})
        self.agent = agent
