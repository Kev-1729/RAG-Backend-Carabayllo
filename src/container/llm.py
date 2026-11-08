from functools import lru_cache

from src.config import get_settings
from src.domain.ports import LLM
from src.infrastructure.llm.anthropic_llm import AnthropicLLM


@lru_cache
def get_llm() -> LLM:
    loaded = get_settings()
    return AnthropicLLM(
        api_key=loaded.anthropic_api_key.get_secret_value(),
        model=loaded.llm_model,
    )
