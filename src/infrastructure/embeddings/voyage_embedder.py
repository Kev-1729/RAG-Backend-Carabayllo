from typing import Literal

import voyageai
from voyageai import error as voyage_error

from src.domain.exceptions import EmbeddingUnavailableError

BATCH_SIZE = 128


class VoyageEmbedder:
    def __init__(self, api_key: str, model: str, dimension: int) -> None:
        self._client = voyageai.AsyncClient(api_key=api_key, max_retries=3)
        self._model = model
        self._dimension = dimension

    async def embed_documents(self, texts: list[str]) -> list[tuple[float, ...]]:
        embeddings: list[tuple[float, ...]] = []
        for start in range(0, len(texts), BATCH_SIZE):
            embeddings.extend(
                await self._embed(texts[start : start + BATCH_SIZE], "document")
            )
        return embeddings

    async def embed_query(self, text: str) -> tuple[float, ...]:
        embeddings = await self._embed([text], "query")
        return embeddings[0]

    async def _embed(
        self, texts: list[str], input_type: Literal["document", "query"]
    ) -> list[tuple[float, ...]]:
        try:
            result = await self._client.embed(
                texts,
                model=self._model,
                input_type=input_type,
                output_dimension=self._dimension,
            )
        except (
            voyage_error.RateLimitError,
            voyage_error.APIConnectionError,
            voyage_error.ServerError,
            voyage_error.ServiceUnavailableError,
            voyage_error.Timeout,
        ) as e:
            raise EmbeddingUnavailableError() from e
        return [tuple(vector) for vector in result.embeddings]
