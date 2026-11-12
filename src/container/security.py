from functools import lru_cache

from src.config import get_settings
from src.domain.ports import ConversationTokens
from src.infrastructure.conversation_tokens import HmacConversationTokens


@lru_cache
def get_conversation_tokens() -> ConversationTokens:
    return HmacConversationTokens(get_settings().api_access_secret.get_secret_value())
