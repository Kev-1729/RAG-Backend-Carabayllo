from fastapi import APIRouter, Depends

from src.application.answer.conversation_query import ConversationQuery
from src.domain.entities import Query
from src.interfaces.dependencies.answer import get_conversation_query
from src.interfaces.schemas.query import QueryRequest, QueryResponse, SourceResponse

router = APIRouter(prefix="/query", tags=["query"])


@router.post("", response_model=QueryResponse)
async def answer_query(
    body: QueryRequest,
    use_case: ConversationQuery = Depends(get_conversation_query),
) -> QueryResponse:
    answer = await use_case.execute(
        Query(text=body.question, conversation_id=body.conversation_id)
    )
    if answer.conversation_id is None or answer.message_id is None:
        raise RuntimeError("Conversation response is missing persistence identifiers")
    return QueryResponse(
        answer=answer.text,
        conversation_id=answer.conversation_id,
        message_id=answer.message_id,
        sources=[
            SourceResponse(document=source.document, page=source.page)
            for source in answer.sources
        ],
    )
