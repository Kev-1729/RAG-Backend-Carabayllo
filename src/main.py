from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.config import get_settings
from src.container.answer import conversation_query_resources
from src.domain.exceptions import (
    ConversationNotFoundError,
    ConversationUnavailableError,
    EmbeddingUnavailableError,
    LLMUnavailableError,
    RetrievalUnavailableError,
)
from src.interfaces.routers import conversations, query


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    async with conversation_query_resources() as use_case:
        application.state.conversation_query = use_case
        try:
            yield
        finally:
            del application.state.conversation_query


def create_application() -> FastAPI:
    application = FastAPI(
        title="RAG Carabayllo",
        description="Sistema de RAG para la Municipalidad de Carabayllo",
        version="1.0.0",
        lifespan=lifespan,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().parsed_cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    application.include_router(query.router)
    application.include_router(conversations.router)

    @application.exception_handler(ConversationNotFoundError)
    async def conversation_not_found(
        _: Request, __: ConversationNotFoundError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=404, content={"detail": "La conversación no existe."}
        )

    @application.exception_handler(LLMUnavailableError)
    @application.exception_handler(EmbeddingUnavailableError)
    @application.exception_handler(RetrievalUnavailableError)
    @application.exception_handler(ConversationUnavailableError)
    async def service_unavailable(_: Request, __: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={
                "detail": "El asistente no está disponible. Intenta en unos minutos."
            },
        )

    return application


app = create_application()
