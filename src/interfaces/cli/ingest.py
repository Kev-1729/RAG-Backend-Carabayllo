import argparse
import asyncio
from pathlib import Path

from src.application.ingest.ingest_documents import IngestionReport, SourceFile
from src.container.ingest import ingest_documents


async def ingest(folder: Path) -> IngestionReport:
    files: list[SourceFile] = []
    unreadable: list[tuple[str, str]] = []
    for path in sorted(folder.glob("*.pdf")):
        try:
            files.append(SourceFile(name=path.name, content=path.read_bytes()))
        except OSError as error:
            unreadable.append((path.name, f"no se pudo leer el archivo: {error}"))
    async with ingest_documents() as use_case:
        report = await use_case.execute(files)
    report.failed.extend(unreadable)
    return report


def print_report(report: IngestionReport) -> None:
    print(f"Ingeridos: {len(report.ingested)}")
    for item in report.ingested:
        print(f"  + {item.name} ({item.pages} páginas, {item.chunks} fragmentos)")
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
