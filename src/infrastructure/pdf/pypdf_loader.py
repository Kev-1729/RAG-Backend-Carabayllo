import re
from io import BytesIO

from pypdf import PdfReader

from src.domain.entities import Page
from src.domain.exceptions import InvalidDocumentError


def _paragraphs_from_layout(text: str) -> tuple[str, ...]:
    return tuple(
        " ".join(block.split()) for block in re.split(r"\n\s*\n", text) if block.split()
    )


class PypdfLoader:
    def load(self, content: bytes) -> tuple[Page, ...]:
        try:
            reader = PdfReader(BytesIO(content))
            return tuple(
                Page(
                    number=number,
                    paragraphs=_paragraphs_from_layout(
                        page.extract_text(extraction_mode="layout") or ""
                    ),
                )
                for number, page in enumerate(reader.pages, start=1)
            )
        except Exception as e:
            # pypdf lanza errores de varios tipos con archivos dañados o protegidos.
            raise InvalidDocumentError(f"no se pudo leer el PDF: {e}") from e
