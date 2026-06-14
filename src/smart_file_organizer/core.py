"""Core file organization logic."""

import shutil
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from smart_file_organizer.errors import (
    DestinationConflictError,
    DestinationExistsError,
    SourceMissingError,
)


class FileCategory(StrEnum):
    """Supported file categories."""

    ARCHIVES = "archives"
    AUDIO = "audio"
    CODE = "code"
    DOCUMENTS = "documents"
    IMAGES = "images"
    OTHER = "other"
    VIDEOS = "videos"


@dataclass(frozen=True)
class PlannedMove:
    """A planned file move that has not been executed yet."""

    source: Path
    destination: Path
    category: FileCategory


_EXTENSION_CATEGORIES: dict[str, FileCategory] = {
    ".7z": FileCategory.ARCHIVES,
    ".gz": FileCategory.ARCHIVES,
    ".rar": FileCategory.ARCHIVES,
    ".tar": FileCategory.ARCHIVES,
    ".zip": FileCategory.ARCHIVES,
    ".flac": FileCategory.AUDIO,
    ".mp3": FileCategory.AUDIO,
    ".wav": FileCategory.AUDIO,
    ".css": FileCategory.CODE,
    ".html": FileCategory.CODE,
    ".js": FileCategory.CODE,
    ".json": FileCategory.CODE,
    ".py": FileCategory.CODE,
    ".md": FileCategory.DOCUMENTS,
    ".pdf": FileCategory.DOCUMENTS,
    ".txt": FileCategory.DOCUMENTS,
    ".doc": FileCategory.DOCUMENTS,
    ".docx": FileCategory.DOCUMENTS,
    ".gif": FileCategory.IMAGES,
    ".jpeg": FileCategory.IMAGES,
    ".jpg": FileCategory.IMAGES,
    ".png": FileCategory.IMAGES,
    ".svg": FileCategory.IMAGES,
    ".mkv": FileCategory.VIDEOS,
    ".mov": FileCategory.VIDEOS,
    ".mp4": FileCategory.VIDEOS,
    ".webm": FileCategory.VIDEOS,
}


def classify_path(path: Path) -> FileCategory:
    """Return the category for a path based on its file extension."""
    extension = path.suffix.lower()

    return _EXTENSION_CATEGORIES.get(extension, FileCategory.OTHER)


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


SemanticFolderRule = tuple[str, tuple[str, ...]]


_SEMANTIC_FOLDER_RULES: tuple[SemanticFolderRule, ...] = (
    (
        "documents/utilities/fastweb",
        (
            "fastweb",
            "conto fastweb",
        ),
    ),
    (
        "documents/utilities/water",
        (
            "acque spa",
            "acque",
        ),
    ),
    (
        "documents/inps-sfl",
        (
            "inps",
            "sfl",
            "adi",
            "isee",
            "dsu",
            "prestazioni a sostegno",
            "modelloattestazionedsu",
        ),
    ),
    (
        "documents/taxes",
        (
            "730",
            "cu2026",
            "cu 2026",
            "ade 2024",
            "agenzia entrate",
            "certificazione unica",
        ),
    ),
    (
        "documents/identity",
        (
            "ci fronte",
            "ci retro",
            "carta identita",
            "carta d identita",
            "identity",
        ),
    ),
    (
        "documents/health",
        (
            "urologia",
            "urinocoltura",
            "ecoaddome",
            "deambulazione",
        ),
    ),
    (
        "documents/legal-notifications",
        (
            "pn aar",
            "pn legal facts",
            "pn notification attachments",
        ),
    ),
    (
        "documents/bank-poste",
        (
            "documentopostawebrapporto",
            "documento postaweb rapporto",
            "prospettopagamento",
            "poste",
        ),
    ),
    (
        "documents/vehicle",
        (
            "mazda",
            "rinnovo parcheggio",
            "contrassegno",
            "bollo",
            "ricevuta",
        ),
    ),
    (
        "documents/insurance",
        (
            "zurich",
            "ass ne",
            "pol ",
            "polizza",
        ),
    ),
    (
        "documents/work-admin",
        (
            "pre assunzione",
            "coop zefiro",
        ),
    ),
    (
        "learning/kleis",
        (
            "kleis corso",
            "kleis references",
            "vademecum stage",
        ),
    ),
    (
        "learning/yocto",
        ("yocto",),
    ),
    (
        "books/programming",
        (
            "algoritmi",
            "strutture dati",
            "csharp",
            "c sharp",
            "python",
            "modern cpp",
            "c++",
            "lean architectures",
            "hacking secret ciphers",
            "makinggames",
        ),
    ),
    (
        "photos/2026",
        ("foto2026",),
    ),
)


def _normalize_search_text(text: str) -> str:
    """Normalize text for semantic rule matching."""
    normalized = text.lower()

    for separator in ("_", "-", ".", "/", "\\"):
        normalized = normalized.replace(separator, " ")

    return " ".join(normalized.split())


def _path_search_text(path: Path) -> str:
    """Return normalized searchable text for a path."""
    return _normalize_search_text(" ".join(path.parts))


def _normalize_semantic_rules(
    semantic_rules: Iterable[tuple[str, tuple[str, ...]]] | None,
) -> tuple[SemanticFolderRule, ...]:
    """Return caller-provided semantic rules or the built-in defaults."""
    if semantic_rules is None:
        return _SEMANTIC_FOLDER_RULES

    return tuple(semantic_rules)


def _match_semantic_folder(
    search_text: str,
    semantic_rules: Iterable[tuple[str, tuple[str, ...]]] | None = None,
) -> Path | None:
    """Return the first semantic folder matching searchable text."""
    rules = _normalize_semantic_rules(semantic_rules)

    for folder, keywords in rules:
        if any(keyword in search_text for keyword in keywords):
            return Path(folder)

    return None


def infer_destination_folder(
    path: Path,
    *,
    document_text: str = "",
    semantic_rules: Iterable[tuple[str, tuple[str, ...]]] | None = None,
) -> Path:
    """Infer a semantic destination folder for a path."""
    rules = _normalize_semantic_rules(semantic_rules)
    path_search_text = _path_search_text(path)

    if path_semantic_folder := _match_semantic_folder(path_search_text, rules):
        return path_semantic_folder

    suffixes = tuple(suffix.lower() for suffix in path.suffixes)
    if any(suffix in {".epub", ".azw3"} for suffix in suffixes):
        return Path("books/fiction")

    category = classify_path(path)
    if category != FileCategory.DOCUMENTS:
        return Path(category.value)

    if document_text:
        content_search_text = _normalize_search_text(document_text)
        if content_semantic_folder := _match_semantic_folder(
            content_search_text,
            rules,
        ):
            return content_semantic_folder

    return Path(category.value)
