"""Semantic destination rule helpers."""

import re
from collections.abc import Iterable
from pathlib import Path
from typing import Literal

from smart_file_organizer.classification import classify_path
from smart_file_organizer.models import FileCategory, SemanticFolderRule

MatchTarget = Literal["path", "content"]

_CONTENT_MIN_SINGLE_KEYWORD_LENGTH = 5

_GENERIC_CONTENT_KEYWORDS = frozenset(
    {
        "adi",
        "bollo",
        "dsu",
        "inps",
        "isee",
        "pol",
        "poste",
        "ricevuta",
        "sfl",
    }
)


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
            "acqua",
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
            "naspi",
            "domanda inps",
            "prestazioni a sostegno",
            "modelloattestazionedsu",
            "modelloattestazionedso",
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
            "verbale invalidita",
            "verbale invalidità",
            "verbale handicap",
            "commissione medica",
            "legge 104",
            "l104",
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
            "costimutuo",
            "costi mutuo",
            "mutuo",
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
            "algorithms",
            "strutture dati",
            "csharp",
            "c sharp",
            "python",
            "modern cpp",
            "c++",
            "cpp",
            "lean architectures",
            "hacking secret ciphers",
            "makinggames",
            "esp idf",
            "esp-idf",
            "software architecture",
            "oreilly",
            "o reilly",
            "wiley",
            "programming",
            "regular expressions",
            "object oriented programming",
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


def _contains_whole_term(term: str, search_text: str) -> bool:
    """Return True when a normalized term appears as a whole token."""
    return re.search(rf"(?<!\w){re.escape(term)}(?!\w)", search_text) is not None


def _keyword_matches_search_text(
    keyword: str,
    search_text: str,
    *,
    match_target: MatchTarget,
) -> bool:
    """Return True when a keyword matches searchable text."""
    if match_target == "path":
        return keyword in search_text

    normalized_keyword = keyword.strip()
    if not normalized_keyword:
        return False

    if " " in normalized_keyword:
        return normalized_keyword in search_text

    if normalized_keyword in _GENERIC_CONTENT_KEYWORDS:
        return False

    if len(normalized_keyword) < _CONTENT_MIN_SINGLE_KEYWORD_LENGTH:
        return False

    return _contains_whole_term(normalized_keyword, search_text)


def _match_semantic_folder(
    search_text: str,
    semantic_rules: Iterable[tuple[str, tuple[str, ...]]] | None = None,
    *,
    match_target: MatchTarget = "path",
) -> Path | None:
    """Return the first semantic folder matching searchable text."""
    rules = _normalize_semantic_rules(semantic_rules)

    for folder, keywords in rules:
        if any(
            _keyword_matches_search_text(
                keyword,
                search_text,
                match_target=match_target,
            )
            for keyword in keywords
        ):
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
            match_target="content",
        ):
            return content_semantic_folder

    return Path(category.value)
