"""Semantic destination rule helpers."""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from smart_file_organizer.classification import classify_path
from smart_file_organizer.config import DEFAULT_FALLBACK_FOLDER
from smart_file_organizer.models import (
    FileCategory,
    SemanticFolderRule,
    SemanticRuleDefinition,
)

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


@dataclass(frozen=True)
class _CompiledSemanticRule:
    """A semantic rule with compiled regex patterns."""

    folder: str
    keywords: tuple[str, ...]
    compiled_patterns: tuple[re.Pattern[str], ...]


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


def _coerce_semantic_rule(rule: SemanticFolderRule) -> SemanticRuleDefinition:
    """Return a semantic rule definition from supported rule shapes."""
    if isinstance(rule, SemanticRuleDefinition):
        return rule

    folder, keywords = rule
    return SemanticRuleDefinition(folder=folder, keywords=keywords)


def _compile_semantic_rule(rule: SemanticRuleDefinition) -> _CompiledSemanticRule:
    """Compile regex patterns for a semantic rule."""
    return _CompiledSemanticRule(
        folder=rule.folder,
        keywords=rule.keywords,
        compiled_patterns=tuple(re.compile(pattern) for pattern in rule.patterns),
    )


def _normalize_semantic_rules(
    semantic_rules: Iterable[SemanticFolderRule] | None,
) -> tuple[_CompiledSemanticRule, ...]:
    """Return built-in rules merged with caller-provided rules.

    Built-in rules are evaluated first, then user rules, so default
    classifications stay stable and custom rules extend coverage.
    """
    if semantic_rules is None:
        return tuple(
            _compile_semantic_rule(_coerce_semantic_rule(rule))
            for rule in _SEMANTIC_FOLDER_RULES
        )

    user_rules = tuple(
        _compile_semantic_rule(_coerce_semantic_rule(rule)) for rule in semantic_rules
    )
    return (
        tuple(
            _compile_semantic_rule(_coerce_semantic_rule(rule))
            for rule in _SEMANTIC_FOLDER_RULES
        )
        + user_rules
    )


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
    normalized_keyword = keyword.strip()
    if not normalized_keyword:
        return False

    if " " in normalized_keyword:
        return normalized_keyword in search_text

    if match_target == "content":
        if normalized_keyword in _GENERIC_CONTENT_KEYWORDS:
            return False

        if len(normalized_keyword) < _CONTENT_MIN_SINGLE_KEYWORD_LENGTH:
            return False

    return _contains_whole_term(normalized_keyword, search_text)


def _pattern_matches_search_text(
    pattern: re.Pattern[str],
    search_text: str,
) -> bool:
    """Return True when a regex pattern matches searchable text."""
    return pattern.search(search_text) is not None


def _rule_matches_search_text(
    rule: _CompiledSemanticRule,
    search_text: str,
    *,
    match_target: MatchTarget,
) -> bool:
    """Return True when a semantic rule matches searchable text."""
    if any(
        _keyword_matches_search_text(keyword, search_text, match_target=match_target)
        for keyword in rule.keywords
    ):
        return True

    if match_target == "path":
        return any(
            _pattern_matches_search_text(pattern, search_text)
            for pattern in rule.compiled_patterns
        )

    return False


def _match_semantic_folder(
    search_text: str,
    rules: tuple[_CompiledSemanticRule, ...],
    *,
    match_target: MatchTarget = "path",
) -> Path | None:
    """Return the first semantic folder matching searchable text."""
    for rule in rules:
        if _rule_matches_search_text(rule, search_text, match_target=match_target):
            return Path(rule.folder)

    return None


def _default_category_folder(
    category: FileCategory,
    *,
    fallback_folder: str | None = DEFAULT_FALLBACK_FOLDER,
) -> Path:
    """Return the default folder when no semantic rule matches."""
    if category == FileCategory.DOCUMENTS and fallback_folder is not None:
        return Path(fallback_folder)

    return Path(category.value)


def infer_destination_folder(
    path: Path,
    *,
    document_text: str = "",
    semantic_rules: Iterable[SemanticFolderRule] | None = None,
    fallback_folder: str | None = DEFAULT_FALLBACK_FOLDER,
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

    return _default_category_folder(category, fallback_folder=fallback_folder)
