"""Document text extraction utilities."""

from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path

from pypdf import PdfReader


def extract_document_text(path: Path, *, max_pages: int = 3) -> str:
    """Extract searchable text from a supported document."""
    suffix = path.suffix.lower()

    if suffix == ".txt":
        return path.read_text(encoding="utf-8", errors="replace")

    if suffix == ".pdf":
        return _extract_pdf_text(path, max_pages=max_pages)

    return ""


def _extract_pdf_text(path: Path, *, max_pages: int) -> str:
    """Extract text from the first pages of a PDF document."""
    with redirect_stderr(StringIO()):
        reader = PdfReader(path)
        pages = reader.pages[:max_pages]

        return "\n".join(
            page_text for page in pages if (page_text := page.extract_text())
        )
