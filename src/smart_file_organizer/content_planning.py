"""Content-aware planning helpers."""

from collections.abc import Callable, Iterable
from pathlib import Path

from smart_file_organizer.document_text import extract_document_text
from smart_file_organizer.core import (
    PlannedMove,
    SemanticFolderRule,
    build_organization_plan_with_document_texts,
)

DocumentTextExtractor = Callable[[Path], str]


def build_organization_plan_with_extracted_text(
    sources: Iterable[Path],
    target_root: Path,
    *,
    extract_text: DocumentTextExtractor,
    semantic_rules: Iterable[SemanticFolderRule] | None = None,
) -> list[PlannedMove]:
    """Build move plans using document text returned by an injected extractor."""
    source_list = list(sources)
    document_texts = {source: extract_text(source) for source in source_list}

    return build_organization_plan_with_document_texts(
        source_list,
        target_root,
        document_texts,
        semantic_rules=semantic_rules,
    )


def build_organization_plan_inspecting_content(
    sources: Iterable[Path],
    target_root: Path,
    *,
    semantic_rules: Iterable[SemanticFolderRule] | None = None,
) -> list[PlannedMove]:
    """Build move plans using the default document text extractor."""
    return build_organization_plan_with_extracted_text(
        sources,
        target_root,
        extract_text=extract_document_text,
        semantic_rules=semantic_rules,
    )
