"""Move planning and execution helpers."""

import shutil
from collections.abc import Iterable, Mapping
from pathlib import Path

from smart_file_organizer.classification import classify_path
from smart_file_organizer.errors import (
    DestinationConflictError,
    DestinationExistsError,
    SourceMissingError,
)
from smart_file_organizer.models import PlannedMove
from smart_file_organizer.semantic_rules import (
    _normalize_semantic_rules,
    infer_destination_folder,
)


def plan_file(
    source: Path,
    target_root: Path,
    *,
    semantic_rules: Iterable[tuple[str, tuple[str, ...]]] | None = None,
) -> PlannedMove:
    """Build a move plan for a single file without touching the filesystem."""
    return plan_file_with_document_text(
        source,
        target_root,
        "",
        semantic_rules=semantic_rules,
    )


def plan_file_with_document_text(
    source: Path,
    target_root: Path,
    document_text: str,
    *,
    semantic_rules: Iterable[tuple[str, tuple[str, ...]]] | None = None,
) -> PlannedMove:
    """Build a move plan using caller-provided document text."""
    category = classify_path(source)
    destination = (
        target_root
        / infer_destination_folder(
            source,
            document_text=document_text,
            semantic_rules=semantic_rules,
        )
        / source.name
    )

    return PlannedMove(
        source=source,
        destination=destination,
        category=category,
    )


def build_organization_plan(
    sources: Iterable[Path],
    target_root: Path,
    *,
    semantic_rules: Iterable[tuple[str, tuple[str, ...]]] | None = None,
) -> list[PlannedMove]:
    """Build move plans for multiple files without touching the filesystem."""
    rules = _normalize_semantic_rules(semantic_rules)

    return [plan_file(source, target_root, semantic_rules=rules) for source in sources]


def build_organization_plan_with_document_texts(
    sources: Iterable[Path],
    target_root: Path,
    document_texts: Mapping[Path, str],
    *,
    semantic_rules: Iterable[tuple[str, tuple[str, ...]]] | None = None,
) -> list[PlannedMove]:
    """Build move plans using caller-provided document text."""
    rules = _normalize_semantic_rules(semantic_rules)

    return [
        plan_file_with_document_text(
            source,
            target_root,
            document_texts.get(source, ""),
            semantic_rules=rules,
        )
        for source in sources
    ]


def list_source_files(source_root: Path) -> list[Path]:
    """Return direct files contained in a source directory."""
    return sorted(path for path in source_root.iterdir() if path.is_file())


def find_destination_conflicts(
    plan: Iterable[PlannedMove],
) -> dict[Path, list[PlannedMove]]:
    """Return planned moves grouped by duplicated destination."""
    moves_by_destination: dict[Path, list[PlannedMove]] = {}

    for move in plan:
        moves_by_destination.setdefault(move.destination, []).append(move)

    return {
        destination: moves
        for destination, moves in moves_by_destination.items()
        if len(moves) > 1
    }


def execute_plan(plan: Iterable[PlannedMove]) -> None:
    """Execute a move plan safely."""
    moves = list(plan)

    if find_destination_conflicts(moves):
        raise DestinationConflictError("plan contains destination conflicts")

    for planned_move in moves:
        if not planned_move.source.exists():
            raise SourceMissingError(
                f"source file does not exist: {planned_move.source}"
            )

        if planned_move.destination.exists():
            raise DestinationExistsError(
                f"destination already exists: {planned_move.destination}"
            )

    for planned_move in moves:
        planned_move.destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(planned_move.source, planned_move.destination)
