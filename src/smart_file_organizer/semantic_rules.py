"""Semantic destination rule helpers."""

from collections.abc import Iterable
from pathlib import Path

from smart_file_organizer.classification import classify_path
from smart_file_organizer.models import FileCategory, SemanticFolderRule


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
    """Return built-in rules merged with caller-provided rules.

    Built-in rules are evaluated first, then user rules, so default
    classifications stay stable and custom rules extend coverage.
    """
    if semantic_rules is None:
        return _SEMANTIC_FOLDER_RULES

    return _SEMANTIC_FOLDER_RULES + tuple(semantic_rules)


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
