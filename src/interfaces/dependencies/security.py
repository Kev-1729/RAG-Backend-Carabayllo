from typing import cast
from uuid import UUID

from fastapi import Depends, HTTPException, Request

from src.container.security import get_conversation_tokens
from src.domain.exceptions import (
    InvalidConversationTokenError,
    RequestLimitUnavailableError,
)
from src.domain.ports import ConversationTokens, RequestLimiter


def authorize_conversation(
    tokens: ConversationTokens, token: str | None, conversation_id: UUID | None = None
) -> UUID:
    try:
        identifier = tokens.verify(token or "")
    except InvalidConversationTokenError as error:
        raise HTTPException(
            status_code=403, detail="Acceso a la conversación no autorizado."
        ) from error
    if conversation_id is not None and identifier != conversation_id:
        raise HTTPException(
            status_code=403, detail="Acceso a la conversación no autorizado."
        )
    return identifier


async def enforce_request_limit(
    request: Request, tokens: ConversationTokens = Depends(get_conversation_tokens)
) -> None:
    limiter = cast(RequestLimiter, request.app.state.request_limiter)
    client = request.client.host if request.client else "unknown"
    scopes = [("requests", request.app.state.api_requests_per_minute)]
    if request.url.path.rstrip("/") in {"/query", "/query/stream"}:
        scopes.append(("queries", request.app.state.api_queries_per_minute))
    try:
        for scope, limit in scopes:
            if not await limiter.allow(tokens.request_key(client, scope), limit):
                raise HTTPException(
                    status_code=429,
                    detail="Demasiadas solicitudes. Intenta en un minuto.",
                    headers={"Retry-After": "60"},
                )
    except RequestLimitUnavailableError as error:
        raise HTTPException(
            status_code=503, detail="El servicio no está disponible."
        ) from error
