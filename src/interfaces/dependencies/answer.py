from typing import cast

from fastapi import Request

from src.application.answer.answer_query import AnswerQuery


def get_answer_query(request: Request) -> AnswerQuery:
    return cast(AnswerQuery, request.app.state.answer_query)
