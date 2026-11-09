import anthropic

from src.domain.entities import Generation
from src.domain.exceptions import LLMUnavailableError


class AnthropicLLM:
    def __init__(self, api_key: str, model: str) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model

    async def aclose(self) -> None:
        await self._client.close()

    async def generate(self, system: str, prompt: str) -> Generation:
        try:
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=16000,
                system=system,
                messages=[{"role": "user", "content": prompt}],
                output_config={"effort": "low"},
            )
        except (
            anthropic.RateLimitError,
            anthropic.APIConnectionError,
            anthropic.InternalServerError,
        ) as e:
            raise LLMUnavailableError() from e

        return Generation(
            text="".join(b.text for b in response.content if b.type == "text"),
            model=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
