from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, call

import pytest
from pytest import MonkeyPatch
from voyageai import error as voyage_error

from src.domain.exceptions import EmbeddingUnavailableError
from src.domain.ports import Embedder
from src.infrastructure.embeddings import voyage_embedder


def make_embedder(monkeypatch: MonkeyPatch) -> tuple[Embedder, AsyncMock]:
    embed = AsyncMock()
    monkeypatch.setattr(
        voyage_embedder.voyageai,
        "AsyncClient",
        Mock(return_value=SimpleNamespace(embed=embed)),
    )
    return voyage_embedder.VoyageEmbedder("test", "voyage-4", 1024), embed


async def test_query_uses_query_input_with_configured_model_and_dimension(
    monkeypatch: MonkeyPatch,
) -> None:
    embedder, embed = make_embedder(monkeypatch)
    vector = [0.5] * 1024
    embed.return_value = SimpleNamespace(embeddings=[vector])

    result = await embedder.embed_query("¿Qué requisitos necesito?")

    assert result == tuple(vector)
    embed.assert_awaited_once_with(
        ["¿Qué requisitos necesito?"],
        model="voyage-4",
        input_type="query",
        output_dimension=1024,
    )


async def test_documents_keep_batching_order_and_document_input(
    monkeypatch: MonkeyPatch,
) -> None:
    embedder, embed = make_embedder(monkeypatch)
    texts = [f"párrafo {index}" for index in range(129)]
    vectors = [[float(index)] * 1024 for index in range(129)]
    embed.side_effect = [
        SimpleNamespace(embeddings=vectors[:128]),
        SimpleNamespace(embeddings=vectors[128:]),
    ]

    result = await embedder.embed_documents(texts)

    assert result == [tuple(vector) for vector in vectors]
    assert embed.await_args_list == [
        call(
            texts[:128], model="voyage-4", input_type="document", output_dimension=1024
        ),
        call(
            texts[128:], model="voyage-4", input_type="document", output_dimension=1024
        ),
    ]


async def test_empty_documents_do_not_call_provider(monkeypatch: MonkeyPatch) -> None:
    embedder, embed = make_embedder(monkeypatch)

    assert await embedder.embed_documents([]) == []
    embed.assert_not_awaited()


@pytest.mark.parametrize("query", [True, False])
@pytest.mark.parametrize(
    "error_type",
    [
        voyage_error.RateLimitError,
        voyage_error.APIConnectionError,
        voyage_error.ServerError,
        voyage_error.ServiceUnavailableError,
        voyage_error.Timeout,
    ],
)
async def test_provider_unavailability_is_translated(
    monkeypatch: MonkeyPatch, error_type: type[Exception], query: bool
) -> None:
    embedder, embed = make_embedder(monkeypatch)
    error = error_type("unavailable")
    embed.side_effect = error

    with pytest.raises(EmbeddingUnavailableError) as raised:
        if query:
            await embedder.embed_query("pregunta")
        else:
            await embedder.embed_documents(["documento"])

    assert raised.value.__cause__ is error


async def test_unexpected_errors_are_not_masked(monkeypatch: MonkeyPatch) -> None:
    embedder, embed = make_embedder(monkeypatch)
    embed.side_effect = ValueError("invalid configuration")

    with pytest.raises(ValueError, match="invalid configuration"):
        await embedder.embed_query("pregunta")
