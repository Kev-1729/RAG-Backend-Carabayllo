from io import BytesIO

from pypdf import PdfReader

from src.domain.entities import Page
from src.domain.exceptions import InvalidDocumentError


class PypdfLoader:
    def load(self, content: bytes) -> tuple[Page, ...]:
        try:
            reader = PdfReader(BytesIO(content))
            return tuple(
                Page(number=number, text=page.extract_text() or "")
                for number, page in enumerate(reader.pages, start=1)
            )
        except Exception as e:
            # pypdf lanza errores de varios tipos con archivos dañados o protegidos.
            raise InvalidDocumentError(f"no se pudo leer el PDF: {e}") from e
