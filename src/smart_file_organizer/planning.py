"""Move planning and execution helpers."""

from collections.abc import Iterable, Mapping
from pathlib import Path

from smart_file_organizer.classification import classify_path
from smart_file_organizer.config import DEFAULT_FALLBACK_FOLDER
from smart_file_organizer.errors import DestinationConflictError
from smart_file_organizer.models import (
    PlannedMove,
    RulePrecedence,
    SemanticFolderRule,
    TaxonomyProfileName,
)
from smart_file_organizer.path_validation import (
    is_supported_source_file,
    validate_destination,
    validate_destination_folder,
)
from smart_file_organizer.semantic_rules import infer_destination


def plan_file(
    source: Path,
    target_root: Path,
    *,
    semantic_rules: Iterable[SemanticFolderRule] | None = None,
    fallback_folder: str | None = DEFAULT_FALLBACK_FOLDER,
    rule_precedence: RulePrecedence = "builtins-first",
    disabled_builtin_rules: Iterable[str] = (),
    taxonomy_profile: TaxonomyProfileName = TaxonomyProfileName.PERSONAL_IT,
) -> PlannedMove:
    """Build a move plan for one file without filesystem mutation."""
    return plan_file_with_document_text(
        source,
        target_root,
        "",
        semantic_rules=semantic_rules,
        fallback_folder=fallback_folder,
        rule_precedence=rule_precedence,
        disabled_builtin_rules=disabled_builtin_rules,
        taxonomy_profile=taxonomy_profile,
    )


def plan_file_with_document_text(
    source: Path,
    target_root: Path,
    document_text: str,
    *,
    semantic_rules: Iterable[SemanticFolderRule] | None = None,
    fallback_folder: str | None = DEFAULT_FALLBACK_FOLDER,
    rule_precedence: RulePrecedence = "builtins-first",
    disabled_builtin_rules: Iterable[str] = (),
    taxonomy_profile: TaxonomyProfileName = TaxonomyProfileName.PERSONAL_IT,
) -> PlannedMove:
    """Build a move plan and retain the classification decision."""
    category = classify_path(source)
    decision = infer_destination(
        source,
        document_text=document_text,
        semantic_rules=semantic_rules,
        fallback_folder=fallback_folder,
        rule_precedence=rule_precedence,
        disabled_builtin_rules=disabled_builtin_rules,
        taxonomy_profile=taxonomy_profile,
    )
    destination_folder = validate_destination_folder(decision.folder)
    destination = target_root / destination_folder / source.name
    validate_destination(destination, target_root)

    return PlannedMove(
        source=source,
        destination=destination,
        category=category,
        classification=decision,
    )


def build_organization_plan(
    sources: Iterable[Path],
    target_root: Path,
    *,
    semantic_rules: Iterable[SemanticFolderRule] | None = None,
    fallback_folder: str | None = DEFAULT_FALLBACK_FOLDER,
    rule_precedence: RulePrecedence = "builtins-first",
    disabled_builtin_rules: Iterable[str] = (),
    taxonomy_profile: TaxonomyProfileName = TaxonomyProfileName.PERSONAL_IT,
) -> list[PlannedMove]:
    """Build move plans for multiple files."""
    rule_list = tuple(semantic_rules) if semantic_rules is not None else None
    disabled_ids = tuple(disabled_builtin_rules)

    return [
        plan_file(
            source,
            target_root,
            semantic_rules=rule_list,
            fallback_folder=fallback_folder,
            rule_precedence=rule_precedence,
            disabled_builtin_rules=disabled_ids,
            taxonomy_profile=taxonomy_profile,
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
    rule_precedence: RulePrecedence = "builtins-first",
    disabled_builtin_rules: Iterable[str] = (),
    taxonomy_profile: TaxonomyProfileName = TaxonomyProfileName.PERSONAL_IT,
) -> list[PlannedMove]:
    """Build move plans using caller-provided document text."""
    rule_list = tuple(semantic_rules) if semantic_rules is not None else None
    disabled_ids = tuple(disabled_builtin_rules)

    return [
        plan_file_with_document_text(
            source,
            target_root,
            document_texts.get(source, ""),
            semantic_rules=rule_list,
            fallback_folder=fallback_folder,
            rule_precedence=rule_precedence,
            disabled_builtin_rules=disabled_ids,
            taxonomy_profile=taxonomy_profile,
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


def _renamed_destination(
    source: Path,
    destination: Path,
    *,
    ordinal: int | None = None,
) -> Path:
    """Return one deterministic renamed destination for a conflicting move."""
    suffix = "".join(destination.suffixes)
    stem = destination.name[: -len(suffix)] if suffix else destination.name
    label = _disambiguation_label(source)

    if ordinal is not None:
        label = f"{label}-{ordinal}"

    return destination.parent / f"{stem}__{label}{suffix}"


def _next_available_renamed_destination(
    source: Path,
    destination: Path,
    reserved_destinations: set[Path],
) -> Path:
    """Return the first deterministic renamed destination not already reserved."""
    ordinal: int | None = None

    while True:
        candidate = _renamed_destination(
            source,
            destination,
            ordinal=ordinal,
        )

        if candidate not in reserved_destinations:
            return candidate

        ordinal = 2 if ordinal is None else ordinal + 1


def resolve_destination_conflicts(plan: Iterable[PlannedMove]) -> list[PlannedMove]:
    """Return a plan with deterministic unique destinations for conflicts."""
    moves = list(plan)
    conflicts = find_destination_conflicts(moves)

    if not conflicts:
        return moves

    resolved_destinations = [move.destination for move in moves]
    reserved_destinations = set(resolved_destinations)
    indices_by_destination: dict[Path, list[int]] = {}

    for index, move in enumerate(moves):
        indices_by_destination.setdefault(move.destination, []).append(index)

    for destination in sorted(conflicts, key=str):
        conflict_indices = sorted(
            indices_by_destination[destination],
            key=lambda index: str(moves[index].source),
        )

        for index in conflict_indices[1:]:
            candidate = _next_available_renamed_destination(
                moves[index].source,
                destination,
                reserved_destinations,
            )
            resolved_destinations[index] = candidate
            reserved_destinations.add(candidate)

    resolved_plan = [
        PlannedMove(
            source=move.source,
            destination=resolved_destinations[index],
            category=move.category,
            classification=move.classification,
        )
        for index, move in enumerate(moves)
    ]

    if find_destination_conflicts(resolved_plan):
        raise DestinationConflictError(
            "rename strategy failed to resolve destination conflicts"
        )

    return resolved_plan
