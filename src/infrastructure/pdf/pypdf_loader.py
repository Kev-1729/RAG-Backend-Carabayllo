import hashlib
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader

from src.domain.entities import Document, Page
from src.domain.exceptions import InvalidDocumentError


class PypdfLoader:
    def load(self, path: Path) -> Document:
        try:
            data = path.read_bytes()
            reader = PdfReader(BytesIO(data))
            pages = tuple(
                Page(number=number, text=page.extract_text() or "")
                for number, page in enumerate(reader.pages, start=1)
            )
        except Exception as e:
            # pypdf lanza errores de varios tipos con archivos dañados o protegidos.
            raise InvalidDocumentError(f"no se pudo leer el PDF: {e}") from e

        return Document(
            title=path.stem.replace("_", " "),
            file_name=path.name,
            sha256=hashlib.sha256(data).hexdigest(),
            pages=pages,
        )
