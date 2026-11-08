import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import UUID

import pytest
from pydantic import SecretStr

from evaluations import evaluate
from src.domain.entities import RetrievedChunk


def test_document_ranking_and_threshold_are_separate() -> None:
    item = {"id": "a", "question": "q", "expected_documents": ["expected.pdf"]}
    matches = [
        RetrievedChunk(UUID(int=1), "Other", "other.pdf", 1, "x", 0.1),
        RetrievedChunk(UUID(int=2), "Expected", "expected.pdf", 2, "y", 0.6),
    ]
    row = evaluate.score(item, matches, 0.5)
    assert row["raw_rank"] == 2
    assert row["filtered_rank"] is None
    assert row["abstained"] is False
    summary = evaluate.summarize([row])
    assert summary["mrr_at_5"] == 0.5
    assert summary["filtered_hit_at_5"] == 0


def test_negatives_do_not_enter_hit_or_mrr() -> None:
    row = evaluate.score(
        {"id": "a", "question": "q", "expected_documents": []}, [], 0.5
    )
    summary = evaluate.summarize([row])
    assert summary["hit_at_5"] is None
    assert summary["correct_rejection_rate"] == 1


def test_reference_questions_load() -> None:
    root = Path(__file__).resolve().parents[1]
    questions = evaluate.load_questions(
        root / "evaluations/datasets/retrieval_reference_v2.json"
    )
    assert len(questions) == 71
    assert sum(not q["expected_documents"] for q in questions) == 7


@pytest.mark.parametrize("fails", [False, True])
async def test_run_saves_report_and_closes_engine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fails: bool
) -> None:
    dataset = tmp_path / "questions.json"
    dataset.write_text(
        json.dumps(
            [
                {"id": "a", "question": "q1", "expected_documents": ["a.pdf"]},
                {"id": "b", "question": "q2", "expected_documents": []},
            ]
        ),
        encoding="utf-8",
    )
    engine = SimpleNamespace(dispose=AsyncMock())
    session = AsyncMock()
    session.__aenter__.return_value = session
    session.scalars.return_value = Mock(all=Mock(return_value=["a.pdf"]))
    embedder = SimpleNamespace(embed_query=AsyncMock(return_value=(1.0,)))
    retriever = SimpleNamespace(search_similar=AsyncMock())
    match = RetrievedChunk(UUID(int=1), "A", "a.pdf", 1, "text", 0.2)
    retriever.search_similar.side_effect = (
        [[match], RuntimeError("offline")] if fails else [[match], []]
    )
    monkeypatch.setattr(
        evaluate,
        "get_settings",
        lambda: SimpleNamespace(
            database_url=SecretStr("test"),
            voyage_api_key=SecretStr("test"),
            embedding_model="test",
            retrieval_max_distance=0.5,
        ),
    )
    monkeypatch.setattr(evaluate, "create_engine", lambda *_: engine)
    monkeypatch.setattr(evaluate, "create_session_factory", lambda *_: lambda: session)
    monkeypatch.setattr(evaluate, "VoyageEmbedder", lambda *_: embedder)
    monkeypatch.setattr(evaluate, "SqlAlchemyChunkRetriever", lambda *_: retriever)
    output = tmp_path / "results"
    if fails:
        with pytest.raises(RuntimeError):
            await evaluate.run(dataset, output, "fixed")
    else:
        await evaluate.run(dataset, output, "fixed")
    report = json.loads(next(output.glob("*/report.json")).read_text(encoding="utf-8"))
    assert report["status"] == ("failed" if fails else "complete")
    assert len(report["results"]) == (1 if fails else 2)
    assert ("summary" in report) is not fails
    engine.dispose.assert_awaited_once()
