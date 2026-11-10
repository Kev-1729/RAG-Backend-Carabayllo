import json
import logging
from collections.abc import AsyncGenerator
from contextlib import aclosing

from fastapi import APIRouter, Depends

from src.application.answer.conversation_query import ConversationQuery
from src.domain.entities import Answer, Query
from src.domain.exceptions import (
    ConversationNotFoundError,
    ConversationUnavailableError,
    EmbeddingUnavailableError,
    LLMUnavailableError,
    RetrievalUnavailableError,
)
from src.interfaces.dependencies.answer import get_conversation_query
from src.interfaces.schemas.query import QueryRequest, QueryResponse, SourceResponse
from src.interfaces.streaming import EventStreamResponse

router = APIRouter(prefix="/query", tags=["query"])
logger = logging.getLogger(__name__)

_SERVICE_ERRORS = (
    ConversationUnavailableError,
    EmbeddingUnavailableError,
    LLMUnavailableError,
    RetrievalUnavailableError,
)


@router.post("", response_model=QueryResponse)
async def answer_query(
    body: QueryRequest,
    use_case: ConversationQuery = Depends(get_conversation_query),
) -> QueryResponse:
    answer = await use_case.execute(
        Query(text=body.question, conversation_id=body.conversation_id)
    )
    return _query_response(answer)


@router.post(
    "/stream",
    status_code=200,
    response_class=EventStreamResponse,
    responses={
        404: {"description": "Conversación inexistente"},
        503: {"description": "Servicio no disponible"},
    },
)
async def stream_query(
    body: QueryRequest,
    use_case: ConversationQuery = Depends(get_conversation_query),
) -> EventStreamResponse:
    query = Query(text=body.question, conversation_id=body.conversation_id)
    return EventStreamResponse(_query_events(use_case, query))


async def _query_events(
    use_case: ConversationQuery, query: Query
) -> AsyncGenerator[bytes, None]:
    started = False
    answer = None
    try:
        async with aclosing(use_case.stream(query)) as events:
            async for event in events:
                if isinstance(event, str):
                    started = True
                    yield _sse("delta", {"text": event})
                else:
                    answer = event
                    break
        if answer is None:
            raise LLMUnavailableError()
        yield _sse("complete", _query_response(answer).model_dump(mode="json"))
    except ConversationNotFoundError:
        if not started:
            raise
        yield _sse(
            "error",
            {"code": "conversation_not_found", "detail": "La conversación no existe."},
        )
    except _SERVICE_ERRORS:
        if not started:
            raise
        yield _sse(
            "error",
            {
                "code": "service_unavailable",
                "detail": "El asistente no está disponible. Intenta en unos minutos.",
            },
        )
    except Exception:
        if not started:
            raise
        logger.exception("Error al transmitir la respuesta")
        yield _sse(
            "error",
            {"code": "internal_error", "detail": "No se pudo completar la respuesta."},
        )


def _sse(event: str, payload: dict[str, object]) -> bytes:
    return (
        f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n".encode()
    )


def _query_response(answer: Answer) -> QueryResponse:
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
