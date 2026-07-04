"""Document text extraction utilities."""

import logging
import warnings
from contextlib import contextmanager, redirect_stderr
from io import StringIO
from pathlib import Path

from pypdf import PdfReader

_PYPDF_LOGGER_NAME = "pypdf"


@contextmanager
def _pdf_parser_context(*, verbose: bool):
    """Control pypdf parser output based on verbose mode."""
    if verbose:
        yield
        return

    pypdf_logger = logging.getLogger(_PYPDF_LOGGER_NAME)
    previous_level = pypdf_logger.level
    pypdf_logger.setLevel(logging.ERROR)

    try:
        with redirect_stderr(StringIO()):
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                yield
    finally:
        pypdf_logger.setLevel(previous_level)


def extract_document_text(
    path: Path,
    *,
    max_pages: int = 3,
    verbose: bool = False,
) -> str:
    """Extract searchable text from a supported document."""
    suffix = path.suffix.lower()

    if suffix == ".txt":
        return path.read_text(encoding="utf-8", errors="replace")

    if suffix == ".pdf":
        return _extract_pdf_text(path, max_pages=max_pages, verbose=verbose)

    return ""


def _extract_pdf_text(path: Path, *, max_pages: int, verbose: bool) -> str:
    """Extract text from the first pages of a PDF document."""
    with _pdf_parser_context(verbose=verbose):
        reader = PdfReader(path)
        pages = reader.pages[:max_pages]

        return "\n".join(
            page_text for page in pages if (page_text := page.extract_text())
        )
