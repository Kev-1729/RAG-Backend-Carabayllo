from collections.abc import AsyncGenerator

import anthropic
import httpx2

from src.domain.entities import Generation
from src.domain.exceptions import LLMUnavailableError


class AnthropicLLM:
    def __init__(self, api_key: str, model: str) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model

    async def aclose(self) -> None:
        await self._client.close()

    async def stream(
        self, system: str, prompt: str
    ) -> AsyncGenerator[str | Generation, None]:
        try:
            async with self._client.messages.stream(
                model=self._model,
                max_tokens=16000,
                system=system,
                messages=[{"role": "user", "content": prompt}],
                output_config={"effort": "low"},
            ) as response:
                completed = False
                async for event in response:
                    if event.type == "text" and event.text:
                        yield event.text
                    elif (
                        event.type == "content_block_start"
                        and event.content_block.type == "text"
                        and event.content_block.text
                    ):
                        yield event.content_block.text
                    elif event.type == "message_stop":
                        completed = True
                if not completed:
                    raise LLMUnavailableError()
                message = await response.get_final_message()
                if message.stop_reason not in {"end_turn", "stop_sequence"}:
                    raise LLMUnavailableError()
                generation = Generation(
                    text="".join(b.text for b in message.content if b.type == "text"),
                    model=message.model,
                    input_tokens=message.usage.input_tokens,
                    output_tokens=message.usage.output_tokens,
                )
            yield generation
        except (anthropic.APIError, httpx2.TransportError) as error:
            raise LLMUnavailableError() from error

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
