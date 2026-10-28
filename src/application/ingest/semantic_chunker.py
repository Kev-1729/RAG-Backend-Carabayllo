import json
import re

from src.domain.entities import Page
from src.domain.exceptions import InvalidChunkingError
from src.domain.ports import LLM

SYSTEM_PROMPT = (
    "Agrupas párrafos numerados de un documento administrativo en fragmentos "
    "semánticos. Responde solo con JSON: una lista de pares [inicio, fin] "
    "inclusivos, numerados desde 1. Los rangos deben ser contiguos, sin huecos "
    "ni solapes, y cubrir todos los párrafos. No devuelvas el texto."
)

_JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


class SemanticChunker:
    def __init__(self, llm: LLM, max_chars: int) -> None:
        if max_chars <= 0:
            raise ValueError("max_chars must be positive")
        self._llm = llm
        self._max_chars = max_chars

    async def split(self, pages: tuple[Page, ...]) -> list[tuple[int, str]]:
        numbered = [
            (page.number, paragraph) for page in pages for paragraph in page.paragraphs
        ]
        if not numbered:
            return []

        ranges = await self._groups(len(numbered), numbered)
        pieces: list[tuple[int, str]] = []
        for start, end in ranges:
            group = numbered[start - 1 : end]
            pieces.extend(self._pack(group))
        return pieces

    async def _groups(
        self, count: int, numbered: list[tuple[int, str]]
    ) -> list[tuple[int, int]]:
        prompt = _user_prompt(numbered)
        for _ in range(2):
            raw = await self._llm.generate(system=SYSTEM_PROMPT, prompt=prompt)
            parsed = _parse_ranges(raw, count)
            if parsed is not None:
                return parsed
        raise InvalidChunkingError("el modelo no devolvió grupos de párrafos válidos")

    def _pack(self, group: list[tuple[int, str]]) -> list[tuple[int, str]]:
        packed: list[list[tuple[int, str]]] = []
        current: list[tuple[int, str]] = []
        current_len = 0
        for item in group:
            text_len = len(item[1])
            extra = text_len if not current else text_len + 2
            if current and current_len + extra > self._max_chars:
                packed.append(current)
                current = [item]
                current_len = text_len
            else:
                current.append(item)
                current_len += extra
        if current:
            packed.append(current)
        return [
            (items[0][0], "\n\n".join(text for _, text in items)) for items in packed
        ]


def _user_prompt(numbered: list[tuple[int, str]]) -> str:
    lines = [f"{index}. {text}" for index, (_, text) in enumerate(numbered, start=1)]
    example = "[[1, 2], [3, 3]]" if len(numbered) >= 3 else f"[[1, {len(numbered)}]]"
    return (
        "Párrafos:\n"
        + "\n".join(lines)
        + f"\n\nResponde solo con JSON, por ejemplo: {example}"
    )


def _parse_ranges(raw: str, count: int) -> list[tuple[int, int]] | None:
    payload = raw.strip()
    fenced = _JSON_FENCE.search(payload)
    if fenced:
        payload = fenced.group(1).strip()
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, list):
        return None
    ranges: list[tuple[int, int]] = []
    for item in data:
        parsed = _as_range(item, count)
        if parsed is None:
            return None
        ranges.append(parsed)
    return _contiguous(ranges, count)


def _as_range(item: object, count: int) -> tuple[int, int] | None:
    if not isinstance(item, list) or len(item) != 2:
        return None
    start, end = item
    if not _is_int(start) or not _is_int(end):
        return None
    if start < 1 or end > count or start > end:
        return None
    return (start, end)


def _contiguous(
    ranges: list[tuple[int, int]], count: int
) -> list[tuple[int, int]] | None:
    expected = 1
    for start, end in ranges:
        if start != expected:
            return None
        expected = end + 1
    if expected != count + 1:
        return None
    return ranges


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)
