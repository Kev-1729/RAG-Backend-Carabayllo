from src.domain.entities import Answer, Query
from src.domain.ports import LLM

SYSTEM_PROMPT = (
    "Eres el asistente de trámites de la Municipalidad de Carabayllo. "
    "Responde en español, de forma clara, breve y sin emojis."
)


class AnswerQuery:
    def __init__(self, llm: LLM) -> None:
        self._llm = llm

    async def execute(self, query: Query) -> Answer:
        text = await self._llm.generate(system=SYSTEM_PROMPT, prompt=query.text)
        return Answer(text=text)
