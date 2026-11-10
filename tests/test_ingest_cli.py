from pathlib import Path
from unittest.mock import AsyncMock, Mock
from uuid import UUID

import pytest

from src.application.ingest.ingest_documents import IngestionReport, SourceFile
from src.interfaces.cli import ingest as cli


@pytest.mark.parametrize("count", [0, 2])
async def test_replace_requires_exactly_one_pdf_before_opening_services(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, count: int
) -> None:
    for index in range(count):
        (tmp_path / f"{index}.pdf").write_bytes(b"pdf")
    factory = Mock()
    monkeypatch.setattr(cli, "ingest_documents", factory)
    report = await cli.ingest(tmp_path, UUID(int=1))
    assert len(report.failed) == 1
    factory.assert_not_called()


async def test_cli_passes_replacement_target_with_file_contents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "new.pdf").write_bytes(b"pdf")
    use_case = AsyncMock()
    use_case.execute.return_value = IngestionReport()
    context = AsyncMock()
    context.__aenter__.return_value = use_case
    monkeypatch.setattr(cli, "ingest_documents", Mock(return_value=context))
    await cli.ingest(tmp_path, UUID(int=1))
    use_case.execute.assert_awaited_once_with(
        [SourceFile("new.pdf", b"pdf", supersedes=UUID(int=1))]
    )
