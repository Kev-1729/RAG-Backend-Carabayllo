import hashlib
import hmac
from uuid import UUID

from src.domain.exceptions import InvalidConversationTokenError


class HmacConversationTokens:
    def __init__(self, secret: str) -> None:
        if len(secret) < 32:
            raise ValueError("The access secret must contain at least 32 characters")
        self._secret = secret.encode()

    def _signature(self, value: str) -> str:
        return hmac.new(self._secret, value.encode(), hashlib.sha256).hexdigest()

    def issue(self, conversation_id: UUID) -> str:
        identifier = str(conversation_id)
        return identifier + "." + self._signature("conversation-v1:" + identifier)

    def verify(self, token: str) -> UUID:
        if len(token) > 101 or not token.isascii():
            raise InvalidConversationTokenError()
        try:
            identifier, _ = token.split(".", 1)
            conversation_id = UUID(identifier)
        except ValueError as error:
            raise InvalidConversationTokenError() from error
        if not hmac.compare_digest(token, self.issue(conversation_id)):
            raise InvalidConversationTokenError()
        return conversation_id

    def request_key(self, client: str, scope: str) -> str:
        return self._signature("request-v1:" + scope + ":" + client)
