import argparse
import asyncio
from pathlib import Path

from src.application.ingest.ingest_documents import IngestionReport
from src.container.ingest import ingest_documents


async def ingest(folder: Path) -> IngestionReport:
    async with ingest_documents() as use_case:
        return await use_case.execute(sorted(folder.glob("*.pdf")))


def print_report(report: IngestionReport) -> None:
    print(f"Ingeridos: {len(report.ingested)}")
    for name in report.ingested:
        print(f"  + {name}")
    print(f"Omitidos (ya existían): {len(report.skipped)}")
    for name in report.skipped:
        print(f"  = {name}")
    print(f"Fallidos: {len(report.failed)}")
    for name, reason in report.failed:
        print(f"  ! {name}: {reason}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Ingiere los PDF de una carpeta en la base de datos."
    )
    parser.add_argument("folder", type=Path, help="carpeta con los PDF a ingerir")
    args = parser.parse_args()
    if not args.folder.is_dir():
        parser.error(f"no existe la carpeta: {args.folder}")

    report = asyncio.run(ingest(args.folder))
    print_report(report)
    return 1 if report.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
