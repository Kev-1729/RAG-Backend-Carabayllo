from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query

from src.application.answer.conversation_query import ConversationQuery
from src.container.security import get_conversation_tokens
from src.domain.ports import ConversationTokens
from src.interfaces.dependencies.answer import get_conversation_query
from src.interfaces.dependencies.security import (
    authorize_conversation,
    enforce_request_limit,
)
from src.interfaces.schemas.query import MessageResponse

router = APIRouter(
    prefix="/conversations",
    tags=["conversations"],
    dependencies=[Depends(enforce_request_limit)],
)


@router.get("/{conversation_id}", response_model=list[MessageResponse])
async def get_history(
    conversation_id: UUID,
    limit: int = Query(default=50, ge=1, le=100),
    use_case: ConversationQuery = Depends(get_conversation_query),
    tokens: ConversationTokens = Depends(get_conversation_tokens),
    access_token: str | None = Header(
        default=None, alias="X-Conversation-Token", max_length=101
    ),
) -> list[MessageResponse]:
    authorize_conversation(tokens, access_token, conversation_id)
    return [
        MessageResponse(
            id=m.id, role=m.role, content=m.content, created_at=m.created_at
        )
        for m in await use_case.history(conversation_id, limit)
    ]
