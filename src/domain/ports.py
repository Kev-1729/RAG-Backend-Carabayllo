from typing import Protocol


class LLM(Protocol):
    async def generate(self, system: str, prompt: str) -> str: ...
