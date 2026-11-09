from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from src.domain.entities import Generation
from src.infrastructure.llm import anthropic_llm


async def test_adapter_returns_actual_model_and_provider_usage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = SimpleNamespace(
        model="actual-model-version",
        usage=SimpleNamespace(input_tokens=321, output_tokens=45),
        content=[
            SimpleNamespace(type="thinking"),
            SimpleNamespace(type="text", text="Uno"),
            SimpleNamespace(type="text", text=" dos"),
        ],
    )
    create = AsyncMock(return_value=response)
    client = SimpleNamespace(messages=SimpleNamespace(create=create))
    monkeypatch.setattr(
        anthropic_llm.anthropic, "AsyncAnthropic", Mock(return_value=client)
    )
    llm = anthropic_llm.AnthropicLLM("test-key", "configured-alias")
    result = await llm.generate("system", "question")
    assert result == Generation("Uno dos", "actual-model-version", 321, 45)
    assert create.await_args is not None
    assert create.await_args.kwargs["model"] == "configured-alias"
