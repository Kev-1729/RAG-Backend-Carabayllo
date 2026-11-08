from typing import cast

from fastapi import Request

from src.application.answer.conversation_query import ConversationQuery


def get_conversation_query(request: Request) -> ConversationQuery:
    return cast(ConversationQuery, request.app.state.conversation_query)
