from src.application.answer.answer_query import AnswerQuery
from src.container.answer import build_answer_query


def get_answer_query() -> AnswerQuery:
    return build_answer_query()
