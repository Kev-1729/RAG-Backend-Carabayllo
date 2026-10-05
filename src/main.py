from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.config import settings
from src.domain.exceptions import LLMUnavailableError
from src.interfaces.routers import query


def create_application() -> FastAPI:
    application = FastAPI(
        title="RAG Carabayllo",
        description="Sistema de RAG para la Municipalidad de Carabayllo",
        version="1.0.0",
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.parsed_cors_origins,
        allow_methods=["POST"],
        allow_headers=["*"],
    )

    application.include_router(query.router)

    @application.exception_handler(LLMUnavailableError)
    async def llm_unavailable(_: Request, __: LLMUnavailableError) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={
                "detail": "El asistente no está disponible. Intenta en unos minutos."
            },
        )

    return application


app = create_application()
