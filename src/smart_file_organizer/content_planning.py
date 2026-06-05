"""Content-aware planning helpers."""

from collections.abc import Callable, Iterable
from pathlib import Path

from smart_file_organizer.core import (
    PlannedMove,
    build_organization_plan_with_document_texts,
)

DocumentTextExtractor = Callable[[Path], str]


def build_organization_plan_with_extracted_text(
    sources: Iterable[Path],
    target_root: Path,
    *,
    extract_text: DocumentTextExtractor,
) -> list[PlannedMove]:
    """Build move plans using document text returned by an injected extractor."""
    source_list = list(sources)
    document_texts = {source: extract_text(source) for source in source_list}

    return build_organization_plan_with_document_texts(
        source_list,
        target_root,
        document_texts,
    )
