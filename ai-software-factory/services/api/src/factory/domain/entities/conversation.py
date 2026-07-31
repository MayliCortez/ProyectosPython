"""Conversación con la IA: el canal por el que se crea y se modifica un proyecto."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from factory.domain.errors import ValidationError
from factory.domain.value_objects import ClarifyingQuestion, new_id, utcnow


class MessageRole(StrEnum):
    """Autor de un mensaje dentro de la conversación."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


@dataclass(slots=True)
class Message:
    """Turno individual de la conversación."""

    conversation_id: str
    role: MessageRole
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=new_id)
    created_at: datetime = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        if not self.content.strip():
            raise ValidationError("Un mensaje no puede estar vacío")


@dataclass(slots=True)
class Conversation:
    """Hilo de mensajes de un proyecto, con las preguntas pendientes de respuesta."""

    project_id: str
    messages: list[Message] = field(default_factory=list)
    pending_questions: list[ClarifyingQuestion] = field(default_factory=list)
    answers: dict[str, str] = field(default_factory=dict)
    id: str = field(default_factory=new_id)
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)

    # ── Mensajes ──────────────────────────────────────────────────────────────

    def add_message(
        self,
        role: MessageRole,
        content: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> Message:
        message = Message(
            conversation_id=self.id,
            role=role,
            content=content,
            metadata=metadata or {},
        )
        self.messages.append(message)
        self.updated_at = utcnow()
        return message

    def history(self, limit: int | None = None) -> list[Message]:
        """Mensajes en orden cronológico; `limit` devuelve solo los más recientes."""
        return self.messages[-limit:] if limit else list(self.messages)

    @property
    def user_prompt(self) -> str:
        """Concatena lo que ha pedido el usuario, que es la entrada del analista."""
        return "\n\n".join(m.content for m in self.messages if m.role is MessageRole.USER)

    # ── Preguntas de aclaración ───────────────────────────────────────────────

    def ask(self, questions: list[ClarifyingQuestion]) -> None:
        """Registra preguntas nuevas sin duplicar las ya pendientes."""
        known = {q.id for q in self.pending_questions}
        self.pending_questions.extend(q for q in questions if q.id not in known)
        self.updated_at = utcnow()

    def answer(self, question_id: str, answer: str) -> None:
        """Guarda una respuesta y retira la pregunta de la lista de pendientes."""
        if not any(q.id == question_id for q in self.pending_questions):
            raise ValidationError(
                f"La pregunta {question_id!r} no está pendiente",
                details={"question_id": question_id},
            )
        if not answer.strip():
            raise ValidationError("La respuesta no puede estar vacía")
        self.answers[question_id] = answer.strip()
        self.pending_questions = [q for q in self.pending_questions if q.id != question_id]
        self.updated_at = utcnow()

    @property
    def has_blocking_questions(self) -> bool:
        """Hay preguntas obligatorias sin responder: no se puede especificar todavía."""
        return any(q.required for q in self.pending_questions)

    def answers_summary(self) -> str:
        """Texto plano con las respuestas, listo para inyectar en el prompt del agente."""
        if not self.answers:
            return ""
        return "\n".join(f"- {qid}: {answer}" for qid, answer in sorted(self.answers.items()))
