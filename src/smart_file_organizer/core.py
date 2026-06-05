"""Core file organization logic."""

import re
import shutil
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


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


def plan_file(source: Path, target_root: Path) -> PlannedMove:
    """Build a move plan for a single file without touching the filesystem."""
    return plan_file_with_document_text(source, target_root, "")


def plan_file_with_document_text(
    source: Path,
    target_root: Path,
    document_text: str,
) -> PlannedMove:
    """Build a move plan using caller-provided document text."""
    category = classify_path(source)
    destination = (
        target_root
        / infer_destination_folder(source, document_text=document_text)
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
) -> list[PlannedMove]:
    """Build move plans for multiple files without touching the filesystem."""
    return [plan_file(source, target_root) for source in sources]


def build_organization_plan_with_document_texts(
    sources: Iterable[Path],
    target_root: Path,
    document_texts: Mapping[Path, str],
) -> list[PlannedMove]:
    """Build move plans using caller-provided document text."""
    return [
        plan_file_with_document_text(
            source,
            target_root,
            document_texts.get(source, ""),
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
        raise ValueError("plan contains destination conflicts")

    for planned_move in moves:
        if not planned_move.source.exists():
            raise FileNotFoundError(
                f"source file does not exist: {planned_move.source}"
            )

        if planned_move.destination.exists():
            raise FileExistsError(
                f"destination already exists: {planned_move.destination}"
            )

    for planned_move in moves:
        planned_move.destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(planned_move.source, planned_move.destination)


_SEMANTIC_FOLDER_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
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


def _match_semantic_folder(search_text: str) -> Path | None:
    """Return the first semantic folder matching searchable text."""
    for folder, keywords in _SEMANTIC_FOLDER_RULES:
        if any(keyword in search_text for keyword in keywords):
            return Path(folder)

    return None


def infer_destination_folder(path: Path, *, document_text: str = "") -> Path:
    """Infer a semantic destination folder for a path."""
    path_search_text = _path_search_text(path)
    suffixes = tuple(suffix.lower() for suffix in path.suffixes)

    if re.search(r"\b[a-z]{2}\d{3}[a-z]{2}\b", path_search_text):
        return Path("documents/vehicle")

    if path_semantic_folder := _match_semantic_folder(path_search_text):
        return path_semantic_folder

    if any(suffix in {".epub", ".azw3"} for suffix in suffixes):
        return Path("books/fiction")

    if document_text:
        content_search_text = _normalize_search_text(
            f"{path_search_text} {document_text}"
        )

        if content_semantic_folder := _match_semantic_folder(content_search_text):
            return content_semantic_folder

    return Path(classify_path(path).value)
