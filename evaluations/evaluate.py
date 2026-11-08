import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select

from src.config import get_settings
from src.domain.entities import RetrievedChunk
from src.infrastructure.db.chunk_retriever import SqlAlchemyChunkRetriever
from src.infrastructure.db.database import create_engine, create_session_factory
from src.infrastructure.db.models import EMBEDDING_DIMENSION, DocumentModel
from src.infrastructure.embeddings.voyage_embedder import VoyageEmbedder


def load_questions(path: Path) -> list[dict[str, Any]]:
    questions = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(questions, list) or not questions:
        raise ValueError("Expected a non-empty question list")
    ids: set[str] = set()
    for item in questions:
        if not isinstance(item, dict):
            raise ValueError("Each question must be an object")
        identifier, question, expected = (
            item.get("id"),
            item.get("question"),
            item.get("expected_documents"),
        )
        if (
            not isinstance(identifier, str)
            or not identifier.strip()
            or identifier in ids
        ):
            raise ValueError("Question IDs must be non-empty and unique")
        if not isinstance(question, str) or not 1 <= len(question.strip()) <= 2000:
            raise ValueError("Question must contain 1 to 2000 characters")
        if not isinstance(expected, list) or any(
            not isinstance(name, str) or not name.endswith(".pdf") for name in expected
        ):
            raise ValueError("Expected documents must be PDF names, or []")
        ids.add(identifier)
    return questions


def score(
    item: dict[str, Any], matches: list[RetrievedChunk], threshold: float
) -> dict[str, Any]:
    accepted = [m for m in matches if 0 <= m.distance <= threshold]
    expected = item["expected_documents"]
    rank = next((i for i, m in enumerate(matches, 1) if m.file_name in expected), None)
    filtered_rank = next(
        (i for i, m in enumerate(accepted, 1) if m.file_name in expected), None
    )
    return {
        "id": item["id"],
        "question": item["question"],
        "expected_documents": expected,
        "raw_rank": rank,
        "filtered_rank": filtered_rank,
        "abstained": not accepted,
        "matches": [
            {
                "file_name": m.file_name,
                "page": m.page,
                "distance": m.distance,
                "accepted": 0 <= m.distance <= threshold,
                "content": m.content,
            }
            for m in matches
        ],
    }


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    positive = [r for r in results if r["expected_documents"]]
    negative = [r for r in results if not r["expected_documents"]]
    summary: dict[str, Any] = {
        "total": len(results),
        "positive_count": len(positive),
        "negative_count": len(negative),
    }
    for field, prefix in [("raw_rank", ""), ("filtered_rank", "filtered_")]:
        summary[prefix + "hit_at_5"] = (
            sum(r[field] is not None for r in positive) / len(positive)
            if positive
            else None
        )
        summary[prefix + "mrr_at_5"] = (
            sum(1 / r[field] if r[field] else 0 for r in positive) / len(positive)
            if positive
            else None
        )
    summary["correct_rejection_rate"] = (
        sum(r["abstained"] for r in negative) / len(negative) if negative else None
    )
    return summary


async def run(dataset: Path, output: Path, corpus_label: str) -> Path:
    questions = load_questions(dataset)
    settings = get_settings()
    directory = output / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    directory.mkdir(parents=True, exist_ok=False)
    results: list[dict[str, Any]] = []
    report: dict[str, Any] = {
        "status": "running",
        "corpus_label": corpus_label,
        "embedding_model": settings.embedding_model,
        "embedding_dimension": EMBEDDING_DIMENSION,
        "max_distance": settings.retrieval_max_distance,
        "k": 5,
        "dataset": questions,
        "results": results,
    }
    path = directory / "report.json"
    engine = create_engine(settings.database_url.get_secret_value())
    try:
        factory = create_session_factory(engine)
        async with factory() as session:
            documents = set(
                (
                    await session.scalars(
                        select(DocumentModel.file_name).where(
                            DocumentModel.superseded_by_id.is_(None)
                        )
                    )
                ).all()
            )
        missing = {
            name for q in questions for name in q["expected_documents"]
        } - documents
        if missing:
            raise ValueError(
                "Documents missing from database: " + ", ".join(sorted(missing))
            )
        embedder = VoyageEmbedder(
            settings.voyage_api_key.get_secret_value(),
            settings.embedding_model,
            EMBEDDING_DIMENSION,
        )
        retriever = SqlAlchemyChunkRetriever(factory)
        for item in questions:
            report["current_item"] = item["id"]
            vector = await embedder.embed_query(item["question"])
            matches = await retriever.search_similar(vector, k=5)
            results.append(score(item, matches, settings.retrieval_max_distance))
            path.write_text(
                json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False),
                encoding="utf-8",
            )
        report["status"] = "complete"
        report["summary"] = summarize(results)
    except Exception as error:
        report["status"] = "failed"
        report["error_type"] = type(error).__name__
        raise
    finally:
        try:
            path.write_text(
                json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False),
                encoding="utf-8",
            )
            print(f"Resultados: {path}")
        finally:
            await engine.dispose()
    print(json.dumps(report["summary"], indent=2))
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("evaluations/datasets/retrieval_reference_v2.json"),
    )
    parser.add_argument("--output", type=Path, default=Path("evaluations/results"))
    parser.add_argument(
        "--corpus-label",
        required=True,
        help="Ingested chunking configuration, e.g. fixed-1000-overlap-200",
    )
    args = parser.parse_args()
    asyncio.run(run(args.dataset, args.output, args.corpus_label))


if __name__ == "__main__":
    main()
