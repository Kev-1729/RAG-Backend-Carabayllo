from functools import lru_cache

from fastapi import Depends

from src.application.answer.answer_query import AnswerQuery
from src.config import settings
from src.domain.ports import LLM
from src.infrastructure.llm.anthropic_llm import AnthropicLLM


@lru_cache
def get_llm() -> LLM:
    return AnthropicLLM(
        api_key=settings.anthropic_api_key.get_secret_value(),
        model=settings.llm_model,
    )


def get_answer_query(llm: LLM = Depends(get_llm)) -> AnswerQuery:
    return AnswerQuery(llm)
