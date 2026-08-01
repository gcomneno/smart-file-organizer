"""Move planning and execution helpers."""

from collections.abc import Iterable, Mapping
from pathlib import Path

from smart_file_organizer.classification import classify_path
from smart_file_organizer.errors import DestinationConflictError
from smart_file_organizer.config import DEFAULT_FALLBACK_FOLDER
from smart_file_organizer.models import PlannedMove, SemanticFolderRule
from smart_file_organizer.path_validation import (
    is_supported_source_file,
    validate_destination,
    validate_destination_folder,
)
from smart_file_organizer.semantic_rules import infer_destination_folder


def plan_file(
    source: Path,
    target_root: Path,
    *,
    semantic_rules: Iterable[SemanticFolderRule] | None = None,
    fallback_folder: str | None = DEFAULT_FALLBACK_FOLDER,
) -> PlannedMove:
    """Build a move plan for a single file without touching the filesystem."""
    return plan_file_with_document_text(
        source,
        target_root,
        "",
        semantic_rules=semantic_rules,
        fallback_folder=fallback_folder,
    )


def plan_file_with_document_text(
    source: Path,
    target_root: Path,
    document_text: str,
    *,
    semantic_rules: Iterable[SemanticFolderRule] | None = None,
    fallback_folder: str | None = DEFAULT_FALLBACK_FOLDER,
) -> PlannedMove:
    """Build a move plan using caller-provided document text."""
    category = classify_path(source)
    destination_folder = validate_destination_folder(
        infer_destination_folder(
            source,
            document_text=document_text,
            semantic_rules=semantic_rules,
            fallback_folder=fallback_folder,
        )
    )
    destination = target_root / destination_folder / source.name
    validate_destination(destination, target_root)

    return PlannedMove(
        source=source,
        destination=destination,
        category=category,
    )


def build_organization_plan(
    sources: Iterable[Path],
    target_root: Path,
    *,
    semantic_rules: Iterable[SemanticFolderRule] | None = None,
    fallback_folder: str | None = DEFAULT_FALLBACK_FOLDER,
) -> list[PlannedMove]:
    """Build move plans for multiple files without touching the filesystem."""
    return [
        plan_file(
            source,
            target_root,
            semantic_rules=semantic_rules,
            fallback_folder=fallback_folder,
        )
        for source in sources
    ]


def build_organization_plan_with_document_texts(
    sources: Iterable[Path],
    target_root: Path,
    document_texts: Mapping[Path, str],
    *,
    semantic_rules: Iterable[SemanticFolderRule] | None = None,
    fallback_folder: str | None = DEFAULT_FALLBACK_FOLDER,
) -> list[PlannedMove]:
    """Build move plans using caller-provided document text."""
    return [
        plan_file_with_document_text(
            source,
            target_root,
            document_texts.get(source, ""),
            semantic_rules=semantic_rules,
            fallback_folder=fallback_folder,
        )
        for source in sources
    ]


def list_source_files(source_root: Path, *, recursive: bool = False) -> list[Path]:
    """Return supported files without following directory symlinks."""
    files: list[Path] = []

    def visit(directory: Path) -> None:
        for path in sorted(directory.iterdir(), key=str):
            if path.is_symlink():
                if is_supported_source_file(path):
                    files.append(path)
                continue

            if is_supported_source_file(path):
                files.append(path)
                continue

            if recursive and path.is_dir():
                visit(path)

    visit(source_root)
    return sorted(files, key=str)


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


def _sanitize_disambiguation_label(text: str) -> str:
    """Normalize text for deterministic destination suffixes."""
    normalized = text.lower()

    for separator in ("_", "-", ".", "/", "\\", " "):
        normalized = normalized.replace(separator, "-")

    return "-".join(part for part in normalized.split("-") if part)


def _disambiguation_label(source: Path) -> str:
    """Return a deterministic label derived from a source path."""
    parent_name = source.parent.name
    if parent_name:
        return _sanitize_disambiguation_label(parent_name)

    return _sanitize_disambiguation_label(source.stem)


def _renamed_destination(source: Path, destination: Path) -> Path:
    """Return a renamed destination for a conflicting move."""
    suffix = "".join(destination.suffixes)
    if not suffix:
        suffix = destination.suffix

    label = _disambiguation_label(source)
    return destination.parent / f"{destination.stem}__{label}{suffix}"


def resolve_destination_conflicts(plan: Iterable[PlannedMove]) -> list[PlannedMove]:
    """Return a plan with deterministic renamed destinations for conflicts."""
    moves = list(plan)
    conflicts = find_destination_conflicts(moves)
    if not conflicts:
        return moves

    renamed_destinations: dict[tuple[Path, Path], Path] = {}

    for destination, conflict_moves in conflicts.items():
        for index, move in enumerate(
            sorted(conflict_moves, key=lambda item: str(item.source))
        ):
            if index == 0:
                renamed_destinations[(move.source, move.destination)] = destination
                continue

            renamed_destinations[(move.source, move.destination)] = (
                _renamed_destination(
                    move.source,
                    destination,
                )
            )

    resolved_plan = [
        PlannedMove(
            source=move.source,
            destination=renamed_destinations.get(
                (move.source, move.destination),
                move.destination,
            ),
            category=move.category,
        )
        for move in moves
    ]

    if find_destination_conflicts(resolved_plan):
        raise DestinationConflictError(
            "rename strategy failed to resolve destination conflicts"
        )

    return resolved_plan
