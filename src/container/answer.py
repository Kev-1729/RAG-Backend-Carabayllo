from src.application.answer.answer_query import AnswerQuery
from src.container.llm import get_llm


def build_answer_query() -> AnswerQuery:
    return AnswerQuery(get_llm())
