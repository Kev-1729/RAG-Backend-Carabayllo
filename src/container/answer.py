from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass

from src.application.answer.answer_query import AnswerQuery
from src.application.answer.conversation_query import ConversationQuery
from src.application.answer.submit_rating import SubmitRating
from src.config import get_settings
from src.domain.ports import RequestLimiter
from src.infrastructure.db.chunk_retriever import SqlAlchemyChunkRetriever
from src.infrastructure.db.conversation_repository import (
    SqlAlchemyConversationRepository,
)
from src.infrastructure.db.database import create_engine, create_session_factory
from src.infrastructure.db.models import EMBEDDING_DIMENSION
from src.infrastructure.db.rating_repository import SqlAlchemyRatingRepository
from src.infrastructure.db.request_limiter import SqlAlchemyRequestLimiter
from src.infrastructure.embeddings.voyage_embedder import VoyageEmbedder
from src.infrastructure.llm.anthropic_llm import AnthropicLLM


@dataclass(frozen=True)
class AnswerServices:
    conversation_query: ConversationQuery
    submit_rating: SubmitRating
    request_limiter: RequestLimiter


@asynccontextmanager
async def answer_services() -> AsyncIterator[AnswerServices]:
    settings = get_settings()
    async with AsyncExitStack() as stack:
        engine = create_engine(settings.database_url.get_secret_value())
        stack.push_async_callback(engine.dispose)
        llm = AnthropicLLM(
            api_key=settings.anthropic_api_key.get_secret_value(),
            model=settings.llm_model,
        )
        stack.push_async_callback(llm.aclose)
        session_factory = create_session_factory(engine)
        answer_query = AnswerQuery(
            llm=llm,
            embedder=VoyageEmbedder(
                api_key=settings.voyage_api_key.get_secret_value(),
                model=settings.embedding_model,
                dimension=EMBEDDING_DIMENSION,
            ),
            retriever=SqlAlchemyChunkRetriever(session_factory),
            max_distance=settings.retrieval_max_distance,
        )
        yield AnswerServices(
            ConversationQuery(
                answer_query, SqlAlchemyConversationRepository(session_factory)
            ),
            SubmitRating(SqlAlchemyRatingRepository(session_factory)),
            SqlAlchemyRequestLimiter(session_factory),
        )
