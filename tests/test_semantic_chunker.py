import pytest

from src.application.ingest.semantic_chunker import SemanticChunker
from src.domain.entities import Page
from src.domain.exceptions import InvalidChunkingError, LLMUnavailableError


class FakeLLM:
    def __init__(self, *responses: str | BaseException) -> None:
        self._responses = list(responses)
        self.calls = 0

    async def generate(self, system: str, prompt: str) -> str:
        self.calls += 1
        response = self._responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def pages(*groups: tuple[str, ...]) -> tuple[Page, ...]:
    return tuple(
        Page(number=number, paragraphs=paragraphs)
        for number, paragraphs in enumerate(groups, start=1)
    )


def chunker(*responses: str | BaseException, max_chars: int = 1000) -> SemanticChunker:
    return SemanticChunker(FakeLLM(*responses), max_chars=max_chars)


async def test_valid_groups_join_original_paragraphs() -> None:
    document = pages(("Uno.", "Dos."), ("Tres.",))
    pieces = await chunker("[[1, 2], [3, 3]]").split(document)

    assert pieces == [(1, "Uno.\n\nDos."), (2, "Tres.")]


async def test_retries_once_after_invalid_json_then_succeeds() -> None:
    llm = FakeLLM("no es json", "[[1, 1]]")
    pieces = await SemanticChunker(llm, max_chars=1000).split(pages(("Solo.",)))

    assert pieces == [(1, "Solo.")]
    assert llm.calls == 2


async def test_raises_after_two_invalid_responses() -> None:
    llm = FakeLLM("basura", "[[1, 1], [3, 3]]")
    with pytest.raises(InvalidChunkingError):
        await SemanticChunker(llm, max_chars=1000).split(pages(("A.", "B.", "C.")))
    assert llm.calls == 2


async def test_rejects_overlapping_ranges() -> None:
    with pytest.raises(InvalidChunkingError):
        await chunker("[[1, 2], [2, 3]]", "[[1, 2], [2, 3]]").split(
            pages(("A.", "B.", "C."))
        )


async def test_rejects_ranges_with_gaps() -> None:
    with pytest.raises(InvalidChunkingError):
        await chunker("[[1, 1], [3, 3]]", "[[1, 1], [3, 3]]").split(
            pages(("A.", "B.", "C."))
        )


async def test_rejects_non_list_json() -> None:
    with pytest.raises(InvalidChunkingError):
        await chunker("{}", "{}").split(pages(("A.",)))


async def test_rejects_malformed_range_items() -> None:
    with pytest.raises(InvalidChunkingError):
        await chunker("[[1]]", "[1, 2]").split(pages(("A.", "B.")))


async def test_rejects_non_integer_bounds() -> None:
    with pytest.raises(InvalidChunkingError):
        await chunker("[[1.5, 2]]", "[[true, 1]]").split(pages(("A.", "B.")))


async def test_rejects_out_of_bounds_and_incomplete_cover() -> None:
    with pytest.raises(InvalidChunkingError):
        await chunker("[[1, 5]]", "[[1, 2]]").split(pages(("A.", "B.", "C.")))


async def test_group_over_the_cap_is_split_by_paragraphs() -> None:
    document = pages(("aaaa", "bbbb", "cccc"))
    pieces = await chunker("[[1, 3]]", max_chars=10).split(document)

    assert pieces == [(1, "aaaa\n\nbbbb"), (1, "cccc")]


async def test_single_paragraph_over_the_cap_is_not_cut() -> None:
    long_text = "x" * 50
    pieces = await chunker("[[1, 1]]", max_chars=10).split(pages((long_text,)))

    assert pieces == [(1, long_text)]


async def test_single_paragraph_document() -> None:
    pieces = await chunker("```json\n[[1, 1]]\n```").split(pages(("Único.",)))

    assert pieces == [(1, "Único.")]


def test_max_chars_must_be_positive() -> None:
    with pytest.raises(ValueError):
        SemanticChunker(FakeLLM(), max_chars=0)


async def test_empty_pages_do_not_call_the_llm() -> None:
    llm = FakeLLM()
    pieces = await SemanticChunker(llm, max_chars=1000).split(
        (Page(number=1, paragraphs=()),)
    )

    assert pieces == []
    assert llm.calls == 0


async def test_llm_outage_is_not_swallowed() -> None:
    with pytest.raises(LLMUnavailableError):
        await chunker(LLMUnavailableError()).split(pages(("A.",)))
