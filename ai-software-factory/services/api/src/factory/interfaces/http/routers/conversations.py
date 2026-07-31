"""Chat con la IA sobre un proyecto."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter

from factory.interfaces.http.deps import ConversationServiceDep, CurrentUser
from factory.interfaces.http.schemas import (
    AnswerRequest,
    ConversationResponse,
    SendMessageRequest,
)

router = APIRouter(prefix="/projects/{project_id}/conversation", tags=["conversación"])


@router.get("", response_model=ConversationResponse)
async def get_conversation(
    project_id: str, user: CurrentUser, conversations: ConversationServiceDep
) -> ConversationResponse:
    """Historial completo y preguntas pendientes."""
    view = await conversations.get(user=user, project_id=project_id)
    return ConversationResponse(**asdict(view))


@router.post("/messages", response_model=ConversationResponse)
async def send_message(
    project_id: str,
    payload: SendMessageRequest,
    user: CurrentUser,
    conversations: ConversationServiceDep,
) -> ConversationResponse:
    """Envía un mensaje y vuelve a analizar los requisitos con la respuesta incluida."""
    view = await conversations.send_message(
        user=user, project_id=project_id, content=payload.content
    )
    return ConversationResponse(**asdict(view))


@router.post("/answers", response_model=ConversationResponse)
async def answer_question(
    project_id: str,
    payload: AnswerRequest,
    user: CurrentUser,
    conversations: ConversationServiceDep,
) -> ConversationResponse:
    """Responde a una pregunta de aclaración pendiente."""
    view = await conversations.answer(
        user=user,
        project_id=project_id,
        question_id=payload.question_id,
        answer=payload.answer,
    )
    return ConversationResponse(**asdict(view))
