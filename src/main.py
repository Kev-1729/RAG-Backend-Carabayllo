from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.config import get_settings
from src.container.answer import answer_services
from src.domain.exceptions import (
    ConversationNotFoundError,
    ConversationUnavailableError,
    EmbeddingUnavailableError,
    InvalidRatingError,
    LLMUnavailableError,
    MessageNotFoundError,
    RatingAlreadyExistsError,
    RatingUnavailableError,
    RetrievalUnavailableError,
)
from src.interfaces.routers import conversations, query, ratings


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    async with answer_services() as services:
        application.state.conversation_query = services.conversation_query
        application.state.submit_rating = services.submit_rating
        try:
            yield
        finally:
            del application.state.conversation_query
            del application.state.submit_rating


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
    application.include_router(ratings.router)

    @application.exception_handler(MessageNotFoundError)
    async def message_not_found(_: Request, __: MessageNotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=404, content={"detail": "El mensaje no existe."}
        )

    @application.exception_handler(InvalidRatingError)
    async def invalid_rating(_: Request, __: InvalidRatingError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "detail": "Solo se califican respuestas del asistente con 1 a 5 estrellas."
            },
        )

    @application.exception_handler(RatingAlreadyExistsError)
    async def rating_exists(_: Request, __: RatingAlreadyExistsError) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={"detail": "Esta respuesta ya tiene una calificación."},
        )

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
    @application.exception_handler(RatingUnavailableError)
    async def service_unavailable(_: Request, __: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={
                "detail": "El asistente no está disponible. Intenta en unos minutos."
            },
        )

    return application


app = create_application()
