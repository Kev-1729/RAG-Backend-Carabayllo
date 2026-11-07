from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

from src.application.answer.answer_query import AnswerQuery
from src.config import get_settings
from src.infrastructure.db.chunk_retriever import SqlAlchemyChunkRetriever
from src.infrastructure.db.database import create_engine, create_session_factory
from src.infrastructure.db.models import EMBEDDING_DIMENSION
from src.infrastructure.embeddings.voyage_embedder import VoyageEmbedder
from src.infrastructure.llm.anthropic_llm import AnthropicLLM


@asynccontextmanager
async def answer_query_resources() -> AsyncIterator[AnswerQuery]:
    settings = get_settings()
    async with AsyncExitStack() as stack:
        engine = create_engine(settings.database_url.get_secret_value())
        stack.push_async_callback(engine.dispose)
        llm = AnthropicLLM(
            api_key=settings.anthropic_api_key.get_secret_value(),
            model=settings.llm_model,
        )
        stack.push_async_callback(llm.aclose)
        yield AnswerQuery(
            llm=llm,
            embedder=VoyageEmbedder(
                api_key=settings.voyage_api_key.get_secret_value(),
                model=settings.embedding_model,
                dimension=EMBEDDING_DIMENSION,
            ),
            retriever=SqlAlchemyChunkRetriever(create_session_factory(engine)),
            max_distance=settings.retrieval_max_distance,
        )
