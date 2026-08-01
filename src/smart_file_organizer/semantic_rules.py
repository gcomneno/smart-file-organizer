"""Semantic destination rule helpers."""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from smart_file_organizer.classification import classify_path
from smart_file_organizer.config import DEFAULT_FALLBACK_FOLDER
from smart_file_organizer.models import (
    ClassificationDecision,
    ClassificationSource,
    FileCategory,
    RulePrecedence,
    SemanticFolderRule,
    SemanticRuleDefinition,
)

MatchTarget = Literal["path", "content"]

_CONTENT_MIN_SINGLE_KEYWORD_LENGTH = 5

_ABSOLUTE_PATH_START_RE = re.compile(r"(?<![\w:/])/|(?<![\w:])[A-Za-z]:[\\/]")
_FILENAME_EXTENSION_RE = re.compile(r"\.[A-Za-z0-9]{1,16}$")
_PATH_REFERENCE_TRAILING_PUNCTUATION = ".,;:!?)]}"
_PATH_REFERENCE_QUOTES = "\"'`"
_ROUTING_ARROW_MARKERS = ("->", "=>", "→")

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
    """A semantic rule with identity and compiled patterns."""

    folder: str
    keywords: tuple[str, ...]
    compiled_patterns: tuple[re.Pattern[str], ...]
    rule_id: str
    source: ClassificationSource


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


def _absolute_path_start(line: str) -> re.Match[str] | None:
    """Return the start of an absolute filesystem path, if present."""
    return _ABSOLUTE_PATH_START_RE.search(line)


def _whole_line_absolute_filename_reference(line: str) -> bool:
    """Return whether a line consists only of an absolute filename reference."""
    path_reference = line.strip().rstrip(_PATH_REFERENCE_TRAILING_PUNCTUATION)

    if (
        len(path_reference) >= 2
        and path_reference[0] in _PATH_REFERENCE_QUOTES
        and path_reference[-1] == path_reference[0]
    ):
        path_reference = path_reference[1:-1].strip()

    path_reference = path_reference.rstrip(_PATH_REFERENCE_TRAILING_PUNCTUATION)
    path_start = _absolute_path_start(path_reference)
    if path_start is None or path_start.start() != 0:
        return False

    filename = path_reference.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    return bool(filename) and _FILENAME_EXTENSION_RE.search(filename) is not None


def _should_exclude_content_line(line: str) -> bool:
    """Return whether a line is an absolute-path reference unsuitable as content."""
    path_start = _absolute_path_start(line)
    if path_start is not None and any(
        marker in line for marker in _ROUTING_ARROW_MARKERS
    ):
        return True

    return _whole_line_absolute_filename_reference(line)


def _prepare_content_search_text(document_text: str) -> str:
    """Normalize descriptive content after omitting explicit path-reference lines."""
    retained_lines = (
        line
        for line in document_text.splitlines()
        if not _should_exclude_content_line(line)
    )
    return _normalize_search_text("\n".join(retained_lines))


def _coerce_semantic_rule(rule: SemanticFolderRule) -> SemanticRuleDefinition:
    """Return a semantic rule definition from supported rule shapes."""
    if isinstance(rule, SemanticRuleDefinition):
        return rule

    folder, keywords = rule
    return SemanticRuleDefinition(folder=folder, keywords=keywords)


def _builtin_rule_id(folder: str) -> str:
    """Return the stable identifier for a built-in rule."""
    return f"builtin:{folder}"


def _compile_semantic_rule(
    rule: SemanticRuleDefinition,
    *,
    source: ClassificationSource,
    default_rule_id: str,
) -> _CompiledSemanticRule:
    """Compile one identified semantic rule."""
    return _CompiledSemanticRule(
        folder=rule.folder,
        keywords=rule.keywords,
        compiled_patterns=tuple(re.compile(pattern) for pattern in rule.patterns),
        rule_id=rule.rule_id or default_rule_id,
        source=source,
    )


def _normalize_semantic_rules(
    semantic_rules: Iterable[SemanticFolderRule] | None,
    *,
    rule_precedence: RulePrecedence = "builtins-first",
    disabled_builtin_rules: Iterable[str] = (),
) -> tuple[_CompiledSemanticRule, ...]:
    """Return enabled built-ins and configured rules in policy order."""
    disabled_ids = set(disabled_builtin_rules)
    builtin_rules: list[_CompiledSemanticRule] = []

    for raw_rule in _SEMANTIC_FOLDER_RULES:
        definition = _coerce_semantic_rule(raw_rule)
        compiled = _compile_semantic_rule(
            definition,
            source=ClassificationSource.BUILTIN_RULE,
            default_rule_id=_builtin_rule_id(definition.folder),
        )

        if compiled.rule_id not in disabled_ids:
            builtin_rules.append(compiled)

    configured_rules = tuple(
        _compile_semantic_rule(
            _coerce_semantic_rule(rule),
            source=ClassificationSource.CONFIGURED_RULE,
            default_rule_id=f"configured:{index}",
        )
        for index, rule in enumerate(
            semantic_rules or (),
            start=1,
        )
    )
    builtins = tuple(builtin_rules)

    if rule_precedence == "configured-first":
        return configured_rules + builtins

    return builtins + configured_rules


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
) -> tuple[str, str] | None:
    """Return the first matching mechanism and value."""
    for keyword in rule.keywords:
        if _keyword_matches_search_text(
            keyword,
            search_text,
            match_target=match_target,
        ):
            return ("keyword", keyword)

    if match_target == "path":
        for pattern in rule.compiled_patterns:
            if _pattern_matches_search_text(
                pattern,
                search_text,
            ):
                return ("pattern", pattern.pattern)

    return None


def _match_semantic_rule(
    search_text: str,
    rules: tuple[_CompiledSemanticRule, ...],
    *,
    match_target: MatchTarget = "path",
) -> ClassificationDecision | None:
    """Return the first matching semantic decision."""
    for rule in rules:
        match = _rule_matches_search_text(
            rule,
            search_text,
            match_target=match_target,
        )

        if match is None:
            continue

        match_kind, match_value = match

        return ClassificationDecision(
            folder=Path(rule.folder),
            source=rule.source,
            rule_id=rule.rule_id,
            match_target=match_target,
            reason=(
                f"{rule.rule_id} matched {match_kind} {match_value!r} in {match_target}"
            ),
        )

    return None


def _match_semantic_folder(
    search_text: str,
    rules: tuple[_CompiledSemanticRule, ...],
    *,
    match_target: MatchTarget = "path",
) -> Path | None:
    """Return the first semantic folder matching searchable text."""
    decision = _match_semantic_rule(
        search_text,
        rules,
        match_target=match_target,
    )

    return decision.folder if decision is not None else None


def _default_category_folder(
    category: FileCategory,
    *,
    fallback_folder: str | None = DEFAULT_FALLBACK_FOLDER,
) -> Path:
    """Return the default folder when no semantic rule matches."""
    if category == FileCategory.DOCUMENTS and fallback_folder is not None:
        return Path(fallback_folder)

    return Path(category.value)


def infer_destination(
    path: Path,
    *,
    document_text: str = "",
    semantic_rules: Iterable[SemanticFolderRule] | None = None,
    fallback_folder: str | None = DEFAULT_FALLBACK_FOLDER,
    rule_precedence: RulePrecedence = "builtins-first",
    disabled_builtin_rules: Iterable[str] = (),
) -> ClassificationDecision:
    """Infer a destination and retain its classification reason."""
    rules = _normalize_semantic_rules(
        semantic_rules,
        rule_precedence=rule_precedence,
        disabled_builtin_rules=disabled_builtin_rules,
    )
    path_search_text = _path_search_text(path)

    if path_decision := _match_semantic_rule(
        path_search_text,
        rules,
        match_target="path",
    ):
        return path_decision

    suffixes = tuple(suffix.lower() for suffix in path.suffixes)

    if any(suffix in {".epub", ".azw3"} for suffix in suffixes):
        return ClassificationDecision(
            folder=Path("books/fiction"),
            source=ClassificationSource.SPECIAL_CASE,
            match_target="extension",
            reason=("ebook extension selected the built-in books/fiction special case"),
        )

    category = classify_path(path)

    if category != FileCategory.DOCUMENTS:
        return ClassificationDecision(
            folder=Path(category.value),
            source=ClassificationSource.EXTENSION,
            match_target="extension",
            reason=(f"extension classification selected category {category.value!r}"),
        )

    if document_text:
        content_search_text = _prepare_content_search_text(document_text)

        if content_decision := _match_semantic_rule(
            content_search_text,
            rules,
            match_target="content",
        ):
            return content_decision

    folder = _default_category_folder(
        category,
        fallback_folder=fallback_folder,
    )

    return ClassificationDecision(
        folder=folder,
        source=ClassificationSource.FALLBACK,
        match_target="fallback",
        reason=(f"no semantic rule matched; selected fallback folder {str(folder)!r}"),
    )


def infer_destination_folder(
    path: Path,
    *,
    document_text: str = "",
    semantic_rules: Iterable[SemanticFolderRule] | None = None,
    fallback_folder: str | None = DEFAULT_FALLBACK_FOLDER,
    rule_precedence: RulePrecedence = "builtins-first",
    disabled_builtin_rules: Iterable[str] = (),
) -> Path:
    """Infer a semantic folder while preserving the legacy API."""
    return infer_destination(
        path,
        document_text=document_text,
        semantic_rules=semantic_rules,
        fallback_folder=fallback_folder,
        rule_precedence=rule_precedence,
        disabled_builtin_rules=disabled_builtin_rules,
    ).folder
