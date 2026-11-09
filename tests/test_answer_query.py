import json
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from src.application.answer.answer_query import ABSTENTION_MESSAGE, AnswerQuery
from src.domain.entities import Answer, AnswerSource, Generation, Query, RetrievedChunk
from src.domain.exceptions import (
    EmbeddingUnavailableError,
    LLMUnavailableError,
    RetrievalUnavailableError,
)
from src.domain.ports import LLM, ChunkRetriever, Embedder

DOCUMENT_ID = UUID(int=1)
VECTOR = (1.0, 0.0)


def chunk(
    content: str = "Requisitos",
    distance: float = 0.2,
    page: int = 1,
    document_id: UUID = DOCUMENT_ID,
    title: str = "Licencias",
) -> RetrievedChunk:
    return RetrievedChunk(document_id, title, "licencias.pdf", page, content, distance)


def make_query(
    matches: list[RetrievedChunk],
    max_distance: float = 0.5,
) -> tuple[AnswerQuery, AsyncMock, AsyncMock, AsyncMock]:
    llm = AsyncMock(spec=LLM)
    llm.generate.return_value = Generation("Presenta los requisitos [1].")
    embedder = AsyncMock(spec=Embedder)
    embedder.embed_query.return_value = VECTOR
    retriever = AsyncMock(spec=ChunkRetriever)
    retriever.search_similar.return_value = matches
    return AnswerQuery(llm, embedder, retriever, max_distance), llm, embedder, retriever


async def test_retrieves_top_five_and_passes_only_relevant_context() -> None:
    use_case, llm, embedder, retriever = make_query(
        [chunk("Texto relevante", 0.2), chunk("Texto descartado", 0.6)]
    )
    answer = await use_case.execute(Query("¿Qué necesito?"))
    embedder.embed_query.assert_awaited_once_with("¿Qué necesito?")
    embedder.embed_documents.assert_not_awaited()
    retriever.search_similar.assert_awaited_once_with(VECTOR, k=5)
    payload = json.loads(llm.generate.await_args.kwargs["prompt"])
    assert payload == {
        "question": "¿Qué necesito?",
        "context": [
            {
                "source": 1,
                "document": "Licencias",
                "page": 1,
                "content": "Texto relevante",
            }
        ],
    }
    assert answer == Answer(
        "Presenta los requisitos [1].", (AnswerSource(DOCUMENT_ID, "Licencias", 1),)
    )


async def test_sources_are_deduplicated_by_document_id_and_initial_page() -> None:
    use_case, llm, _, _ = make_query(
        [
            chunk("Uno"),
            chunk("Dos"),
            chunk("Tres", page=2),
            chunk("Cuatro", document_id=UUID(int=2)),
        ]
    )
    answer = await use_case.execute(Query("pregunta"))
    assert [(s.document_id, s.page) for s in answer.sources] == [
        (DOCUMENT_ID, 1),
        (DOCUMENT_ID, 2),
        (UUID(int=2), 1),
    ]
    context = json.loads(llm.generate.await_args.kwargs["prompt"])["context"]
    assert [item["source"] for item in context] == [1, 1, 2, 3]
    assert [item["content"] for item in context] == ["Uno", "Dos", "Tres", "Cuatro"]


@pytest.mark.parametrize(
    "matches", [[], [chunk(distance=0.51)], [chunk(distance=float("nan"))]]
)
async def test_abstains_without_llm_when_no_relevant_context(
    matches: list[RetrievedChunk],
) -> None:
    use_case, llm, _, _ = make_query(matches)
    assert await use_case.execute(Query("pregunta")) == Answer(
        ABSTENTION_MESSAGE, input_tokens=0, output_tokens=0
    )
    llm.generate.assert_not_awaited()


async def test_threshold_is_configurable_and_inclusive() -> None:
    use_case, llm, _, _ = make_query([chunk(distance=0.7)], max_distance=0.7)
    answer = await use_case.execute(Query("pregunta"))
    assert len(answer.sources) == 1
    llm.generate.assert_awaited_once()


async def test_source_falls_back_to_file_name() -> None:
    use_case, _, _, _ = make_query([chunk(title="")])
    answer = await use_case.execute(Query("pregunta"))
    assert answer.sources[0].document == "licencias.pdf"


async def test_llm_abstention_has_no_sources() -> None:
    use_case, llm, _, _ = make_query([chunk()])
    llm.generate.return_value = Generation(f" {ABSTENTION_MESSAGE}\n")
    assert await use_case.execute(Query("pregunta ajena")) == Answer(ABSTENTION_MESSAGE)


@pytest.mark.parametrize("abstains", [False, True])
async def test_generation_usage_is_kept_even_when_model_abstains(
    abstains: bool,
) -> None:
    use_case, llm, _, _ = make_query([chunk()])
    text = ABSTENTION_MESSAGE if abstains else "Requisitos [1]."
    llm.generate.return_value = Generation(text, "actual-model", 180, 24)
    answer = await use_case.execute(Query("pregunta"))
    assert (answer.model, answer.input_tokens, answer.output_tokens) == (
        "actual-model",
        180,
        24,
    )
    assert bool(answer.sources) is not abstains


@pytest.mark.parametrize("value", [-0.1, 2.1, float("nan"), float("inf")])
def test_invalid_threshold_is_rejected(value: float) -> None:
    with pytest.raises(ValueError, match="max_distance"):
        make_query([], max_distance=value)


@pytest.mark.parametrize("stage", ["embedding", "retrieval", "llm"])
async def test_service_errors_propagate_without_becoming_abstention(stage: str) -> None:
    use_case, llm, embedder, retriever = make_query([chunk()])
    errors = {
        "embedding": EmbeddingUnavailableError,
        "retrieval": RetrievalUnavailableError,
        "llm": LLMUnavailableError,
    }
    methods = {
        "embedding": embedder.embed_query,
        "retrieval": retriever.search_similar,
        "llm": llm.generate,
    }
    methods[stage].side_effect = errors[stage]()
    with pytest.raises(errors[stage]):
        await use_case.execute(Query("pregunta"))
    if stage == "embedding":
        retriever.search_similar.assert_not_awaited()
    if stage != "llm":
        llm.generate.assert_not_awaited()
