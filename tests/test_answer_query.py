from src.application.answer.answer_query import AnswerQuery
from src.domain.entities import Query


class FakeLLM:
    async def generate(self, system: str, prompt: str) -> str:
        return f"respuesta a: {prompt}"


async def test_answer_query_returns_llm_text() -> None:
    answer = await AnswerQuery(FakeLLM()).execute(Query(text="hola"))

    assert answer.text == "respuesta a: hola"
