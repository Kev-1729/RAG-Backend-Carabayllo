from typing import cast

from fastapi import Request

from src.application.answer.conversation_query import ConversationQuery
from src.application.answer.submit_rating import SubmitRating


def get_conversation_query(request: Request) -> ConversationQuery:
    return cast(ConversationQuery, request.app.state.conversation_query)


def get_submit_rating(request: Request) -> SubmitRating:
    return cast(SubmitRating, request.app.state.submit_rating)
