"""Document text extraction utilities."""

import logging
import warnings
from contextlib import contextmanager, redirect_stderr
from dataclasses import dataclass
from enum import StrEnum
from io import StringIO
from pathlib import Path
from typing import Protocol

from pypdf import PdfReader


_PYPDF_LOGGER_NAME = "pypdf"
_SUPPORTED_CONTENT_SUFFIXES = frozenset({".pdf", ".txt"})


class DocumentTextExtractor(Protocol):
    """Callable contract used to inject document text extraction."""

    def __call__(
        self,
        path: Path,
        *,
        verbose: bool = False,
    ) -> str:
        """Return extracted text for one document."""


class DocumentInspectionStatus(StrEnum):
    """Outcome of optional document-content inspection."""

    EXTRACTED = "extracted"
    NO_TEXT = "no_text"
    UNSUPPORTED = "unsupported"
    FAILED = "failed"


@dataclass(frozen=True)
class DocumentInspectionResult:
    """Internal transient inspection result; text must not cross planning."""

    path: Path
    status: DocumentInspectionStatus
    text: str = ""
    error_type: str | None = None


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
        return _extract_pdf_text(
            path,
            max_pages=max_pages,
            verbose=verbose,
        )

    return ""


def inspect_document_text(
    path: Path,
    *,
    max_pages: int = 3,
    verbose: bool = False,
    extract_text: DocumentTextExtractor | None = None,
) -> DocumentInspectionResult:
    """Inspect supported content and contain expected reader failures."""
    suffix = path.suffix.lower()

    # The default extractor never opens unsupported formats. An injected
    # extractor is still invoked for every source to preserve the existing
    # content-planning extension seam.
    if extract_text is None and suffix not in _SUPPORTED_CONTENT_SUFFIXES:
        return DocumentInspectionResult(
            path=path,
            status=DocumentInspectionStatus.UNSUPPORTED,
        )

    try:
        if extract_text is None:
            text = extract_document_text(
                path,
                max_pages=max_pages,
                verbose=verbose,
            )
        else:
            text = extract_text(
                path,
                verbose=verbose,
            )
    except Exception as error:
        return DocumentInspectionResult(
            path=path,
            status=DocumentInspectionStatus.FAILED,
            error_type=type(error).__name__,
        )

    if not text.strip():
        status = (
            DocumentInspectionStatus.UNSUPPORTED
            if suffix not in _SUPPORTED_CONTENT_SUFFIXES
            else DocumentInspectionStatus.NO_TEXT
        )

        return DocumentInspectionResult(
            path=path,
            status=status,
        )

    return DocumentInspectionResult(
        path=path,
        status=DocumentInspectionStatus.EXTRACTED,
        text=text,
    )


def _extract_pdf_text(
    path: Path,
    *,
    max_pages: int,
    verbose: bool,
) -> str:
    """Extract text from the first pages of a PDF document."""
    with _pdf_parser_context(verbose=verbose):
        reader = PdfReader(path)
        pages = reader.pages[:max_pages]

        return "\n".join(
            page_text for page in pages if (page_text := page.extract_text())
        )
