from uuid import UUID

from fastapi import APIRouter, Depends, Query

from src.application.answer.conversation_query import ConversationQuery
from src.interfaces.dependencies.answer import get_conversation_query
from src.interfaces.schemas.query import MessageResponse

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("/{conversation_id}", response_model=list[MessageResponse])
async def get_history(
    conversation_id: UUID,
    limit: int = Query(default=50, ge=1, le=100),
    use_case: ConversationQuery = Depends(get_conversation_query),
) -> list[MessageResponse]:
    return [
        MessageResponse(
            id=m.id, role=m.role, content=m.content, created_at=m.created_at
        )
        for m in await use_case.history(conversation_id, limit)
    ]
