from itertools import pairwise

import pytest

from src.application.ingest.chunking import split_text


def test_short_text_is_a_single_clean_chunk() -> None:
    assert split_text("  Requisitos   para\n pagar. ", size=100, overlap=20) == [
        "Requisitos para pagar."
    ]


def test_empty_text_has_no_chunks() -> None:
    assert split_text(" \n ", size=100, overlap=20) == []


def test_long_text_overlaps_without_cutting_words() -> None:
    words = [f"palabra{i}" for i in range(50)]

    chunks = split_text(" ".join(words), size=100, overlap=30)

    assert len(chunks) > 1
    assert all(len(chunk) <= 100 for chunk in chunks)
    assert all(word in words for chunk in chunks for word in chunk.split())
    for previous, current in pairwise(chunks):
        assert current.split()[0] in previous.split()


def test_text_without_spaces_is_cut_at_size() -> None:
    chunks = split_text("a" * 250, size=100, overlap=10)

    assert [len(chunk) for chunk in chunks] == [100, 100, 70]


def test_overlap_must_be_smaller_than_size() -> None:
    with pytest.raises(ValueError):
        split_text("texto", size=100, overlap=100)
