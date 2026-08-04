"""Deterministic, privacy-safe evidence collection and decision mechanics.

Content tokens are weak.  A content phrase is strong, two distinct content
indicators combine to strong, and content regexes are supporting.  Filename
and source-path indicators are strong; path regexes are strong.  This keeps a
clear filename useful while requiring corroboration for incidental content.
"""

import hashlib
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from smart_file_organizer.classification import classify_path
from smart_file_organizer.models import (
    ClassificationCandidate,
    ClassificationDecision,
    ClassificationOutcome,
    ClassificationSource,
    EvidenceSource,
    EvidenceStrength,
    MatchMechanism,
    RulePrecedence,
    SemanticFolderRule,
    SemanticRuleDefinition,
    ClassificationEvidence,
    TaxonomyProfileName,
)


_ABSOLUTE_PATH_START_RE = re.compile(r"(?<![\w:/])/|(?<![\w:])[A-Za-z]:[\\/]")
_FILENAME_EXTENSION_RE = re.compile(r"\.[A-Za-z0-9]{1,16}$")
_PATH_REFERENCE_TRAILING_PUNCTUATION = ".,;:!?)}]"
_PATH_REFERENCE_QUOTES = "\"'`"
_ROUTING_ARROW_MARKERS = ("->", "=>", "→")
_STRENGTH_ORDER = {
    EvidenceStrength.WEAK: 1,
    EvidenceStrength.SUPPORTING: 2,
    EvidenceStrength.STRONG: 3,
}


@dataclass(frozen=True, slots=True)
class _CompiledRule:
    folder: Path
    keywords: tuple[str, ...]
    patterns: tuple[re.Pattern[str], ...]
    rule_id: str
    origin: ClassificationSource
    precedence_tier: int
    taxonomy_priority: int | None


def _normalize_search_text(text: str) -> str:
    normalized = text.lower()
    for separator in ("_", "-", ".", "/", "\\"):
        normalized = normalized.replace(separator, " ")
    return " ".join(normalized.split())


def _whole_line_absolute_filename_reference(line: str) -> bool:
    reference = line.strip().rstrip(_PATH_REFERENCE_TRAILING_PUNCTUATION)
    if (
        len(reference) >= 2
        and reference[0] in _PATH_REFERENCE_QUOTES
        and reference[-1] == reference[0]
    ):
        reference = reference[1:-1].strip()
    reference = reference.rstrip(_PATH_REFERENCE_TRAILING_PUNCTUATION)
    start = _ABSOLUTE_PATH_START_RE.search(reference)
    if start is None or start.start() != 0:
        return False
    filename = reference.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    return bool(filename) and _FILENAME_EXTENSION_RE.search(filename) is not None


def _prepare_content_search_text(document_text: str) -> str:
    """Remove routing/path-reference lines before inspecting descriptive text."""
    lines = (
        line
        for line in document_text.splitlines()
        if not (
            _ABSOLUTE_PATH_START_RE.search(line) is not None
            and any(marker in line for marker in _ROUTING_ARROW_MARKERS)
            or _whole_line_absolute_filename_reference(line)
        )
    )
    return _normalize_search_text("\n".join(lines))


def _coerce_rule(rule: SemanticFolderRule) -> SemanticRuleDefinition:
    if isinstance(rule, SemanticRuleDefinition):
        return rule
    folder, keywords = rule
    return SemanticRuleDefinition(folder=folder, keywords=keywords)


def _configured_rule_id(rule: SemanticRuleDefinition) -> str:
    """Generate an order-independent stable ID without process-random hashes."""
    if rule.rule_id is not None:
        return rule.rule_id
    keywords = sorted({_normalize_search_text(item) for item in rule.keywords})
    patterns = sorted(set(rule.patterns))
    canonical = "\x1f".join(
        (
            rule.folder,
            "keywords",
            *keywords,
            "patterns",
            *patterns,
        )
    )
    return "configured:" + hashlib.sha256(canonical.encode()).hexdigest()[:16]


def _compile_rules(
    builtins: Iterable[SemanticFolderRule],
    configured: Iterable[SemanticFolderRule] | None,
    *,
    rule_precedence: RulePrecedence,
    disabled_builtin_rules: Iterable[str],
    builtin_rule_priorities: Mapping[str, int],
) -> tuple[_CompiledRule, ...]:
    disabled = frozenset(disabled_builtin_rules)
    builtin_tier = 0 if rule_precedence == "builtins-first" else 1
    configured_tier = 1 - builtin_tier
    builtin_items: list[_CompiledRule] = []
    for raw in builtins:
        rule = _coerce_rule(raw)
        rule_id = rule.rule_id or f"builtin:{rule.folder}"
        if rule_id in disabled:
            continue
        builtin_items.append(
            _compiled(
                rule,
                rule_id,
                ClassificationSource.BUILTIN_RULE,
                builtin_tier,
                builtin_rule_priorities.get(rule_id),
            )
        )
    configured_items = [
        _compiled(
            _coerce_rule(raw),
            _configured_rule_id(_coerce_rule(raw)),
            ClassificationSource.CONFIGURED_RULE,
            configured_tier,
            None,
        )
        for raw in configured or ()
    ]
    if rule_precedence == "configured-first":
        return tuple(
            sorted(configured_items, key=lambda item: (item.rule_id, str(item.folder)))
            + sorted(builtin_items, key=lambda item: (item.rule_id, str(item.folder)))
        )
    return tuple(
        sorted(builtin_items, key=lambda item: (item.rule_id, str(item.folder)))
        + sorted(configured_items, key=lambda item: (item.rule_id, str(item.folder)))
    )


def _compiled(
    rule: SemanticRuleDefinition,
    rule_id: str,
    origin: ClassificationSource,
    precedence_tier: int,
    taxonomy_priority: int | None,
) -> _CompiledRule:
    return _CompiledRule(
        folder=Path(rule.folder),
        keywords=tuple(rule.keywords),
        patterns=tuple(re.compile(pattern) for pattern in rule.patterns),
        rule_id=rule_id,
        origin=origin,
        precedence_tier=precedence_tier,
        taxonomy_priority=taxonomy_priority,
    )


def _contains_term(term: str, text: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text) is not None


def _evidence_for_rule(
    rule: _CompiledRule,
    text: str,
    *,
    source: EvidenceSource,
    builtin_content_token_exclusions: frozenset[str],
) -> list[ClassificationEvidence]:
    evidence: list[ClassificationEvidence] = []
    normalized_keywords = tuple(
        (raw_keyword, _normalize_search_text(raw_keyword))
        for raw_keyword in rule.keywords
    )
    if source is EvidenceSource.EXTRACTED_CONTENT:
        # A reviewed phrase is more specific than any token it contains.  The
        # token is not a second independent content indicator in that case.
        matching_phrases = {
            keyword
            for _, keyword in normalized_keywords
            if " " in keyword and keyword in text
        }
        keyword_items = tuple(
            (raw_keyword, keyword)
            for raw_keyword, keyword in normalized_keywords
            if " " in keyword
            or not any(_contains_term(keyword, phrase) for phrase in matching_phrases)
        )
        keyword_items = tuple(item for item in keyword_items if " " in item[1]) + tuple(
            item for item in keyword_items if " " not in item[1]
        )
    else:
        keyword_items = normalized_keywords

    occupied_spans: list[tuple[int, int]] = []

    def overlaps_existing(span: tuple[int, int]) -> bool:
        return any(span[0] < end and start < span[1] for start, end in occupied_spans)

    def add_keywords(items: Iterable[tuple[str, str]]) -> None:
        for _, keyword in items:
            if not keyword:
                continue
            phrase = " " in keyword
            if source is EvidenceSource.EXTRACTED_CONTENT:
                if (
                    not phrase
                    and rule.origin is ClassificationSource.BUILTIN_RULE
                    and keyword in builtin_content_token_exclusions
                ):
                    continue
                strength = EvidenceStrength.STRONG if phrase else EvidenceStrength.WEAK
            else:
                strength = EvidenceStrength.STRONG
            match = (
                re.search(re.escape(keyword), text)
                if phrase
                else re.search(rf"(?<!\w){re.escape(keyword)}(?!\w)", text)
            )
            if match is not None and not overlaps_existing(match.span()):
                mechanism = (
                    MatchMechanism.EXACT_PHRASE if phrase else MatchMechanism.TOKEN
                )
                target = (
                    "content" if source is EvidenceSource.EXTRACTED_CONTENT else "path"
                )
                evidence.append(
                    ClassificationEvidence(
                        rule_id=rule.rule_id,
                        source=source,
                        mechanism=mechanism,
                        strength=strength,
                        matched_value=keyword,
                        reason=(
                            f"{rule.rule_id} matched keyword {keyword!r} in {target}"
                        ),
                    )
                )
                occupied_spans.append(match.span())

    def add_patterns() -> None:
        for pattern in rule.patterns:
            match = pattern.search(text)
            if match is not None and not overlaps_existing(match.span()):
                strength = (
                    EvidenceStrength.SUPPORTING
                    if source is EvidenceSource.EXTRACTED_CONTENT
                    else EvidenceStrength.STRONG
                )
                target = (
                    "content" if source is EvidenceSource.EXTRACTED_CONTENT else "path"
                )
                evidence.append(
                    ClassificationEvidence(
                        rule_id=rule.rule_id,
                        source=source,
                        mechanism=MatchMechanism.REGEX,
                        strength=strength,
                        matched_value=pattern.pattern,
                        reason=f"{rule.rule_id} matched regex {pattern.pattern!r} in {target}",
                    )
                )
                occupied_spans.append(match.span())

    if source is EvidenceSource.EXTRACTED_CONTENT:
        # A content regex is supporting, so it takes precedence over an
        # overlapping weak token while a reviewed phrase remains strong.
        add_keywords(item for item in keyword_items if " " in item[1])
        add_patterns()
        add_keywords(item for item in keyword_items if " " not in item[1])
    else:
        add_keywords(keyword_items)
        add_patterns()
    return evidence


def _aggregate_strength(
    evidence: tuple[ClassificationEvidence, ...],
) -> EvidenceStrength:
    if any(item.strength is EvidenceStrength.STRONG for item in evidence):
        return EvidenceStrength.STRONG
    if len(evidence) >= 2:
        return EvidenceStrength.STRONG
    if any(item.strength is EvidenceStrength.SUPPORTING for item in evidence):
        return EvidenceStrength.SUPPORTING
    return EvidenceStrength.WEAK


def _evidence_order(item: ClassificationEvidence) -> tuple[str, int, str]:
    """Return a stable order that keeps legacy keyword explanations familiar."""
    mechanism_order = {
        MatchMechanism.TOKEN: 0,
        MatchMechanism.EXACT_PHRASE: 1,
        MatchMechanism.REGEX: 2,
    }
    return (
        item.source.value,
        mechanism_order[item.mechanism],
        item.matched_value or "",
    )


def _indicator_identity(
    item: ClassificationEvidence,
) -> tuple[EvidenceSource, MatchMechanism, str]:
    """Return the canonical identity of one independently countable indicator.

    Keyword values are normalized exactly as they are for searching.  Regex
    values are reviewed patterns, where textual equality is the intended
    identity.  Source and mechanism intentionally remain part of the key so a
    filename indication is independent from the same content indication.
    """
    value = item.matched_value or ""
    if item.mechanism in {MatchMechanism.TOKEN, MatchMechanism.EXACT_PHRASE}:
        value = _normalize_search_text(value)
    return (item.source, item.mechanism, value)


def _legacy_primary_reason(
    candidate: ClassificationCandidate,
    rules: tuple[_CompiledRule, ...],
    text: str,
    *,
    source: EvidenceSource,
    builtin_content_token_exclusions: frozenset[str],
) -> str:
    """Keep historical selected-rule reasons truthful after evidence aggregation.

    A more-specific phrase can suppress an overlapping token from the evidence
    graph, but the token remains a genuine reviewed match.  Legacy callers saw
    the first reviewed rule indicator in the decision reason, so retain that
    wording without treating it as additional evidence.
    """
    if candidate.rule_origin is ClassificationSource.CONFIGURED_RULE:
        return candidate.evidence[0].reason
    rule = next(
        rule
        for rule in rules
        if rule.rule_id == candidate.rule_id
        and rule.origin is candidate.rule_origin
        and rule.taxonomy_priority == candidate.taxonomy_priority
        and rule.folder == candidate.folder
    )
    for raw_keyword in rule.keywords:
        keyword = _normalize_search_text(raw_keyword)
        if not keyword:
            continue
        if (
            source is EvidenceSource.EXTRACTED_CONTENT
            and " " not in keyword
            and rule.origin is ClassificationSource.BUILTIN_RULE
            and keyword in builtin_content_token_exclusions
        ):
            continue
        if keyword in text if " " in keyword else _contains_term(keyword, text):
            target = "content" if source is EvidenceSource.EXTRACTED_CONTENT else "path"
            return f"{rule.rule_id} matched keyword {raw_keyword!r} in {target}"
    for pattern in rule.patterns:
        if pattern.search(text) is not None:
            target = "content" if source is EvidenceSource.EXTRACTED_CONTENT else "path"
            return f"{rule.rule_id} matched regex {pattern.pattern!r} in {target}"
    return candidate.evidence[0].reason


def _semantic_candidates(
    path: Path,
    document_text: str,
    rules: tuple[_CompiledRule, ...],
    *,
    builtin_content_token_exclusions: frozenset[str],
) -> tuple[tuple[ClassificationCandidate, int], ...]:
    filename = _normalize_search_text(path.name)
    parent = (
        _normalize_search_text(" ".join(path.parent.parts)) if path.parent.parts else ""
    )
    content = _prepare_content_search_text(document_text) if document_text else ""
    grouped: dict[
        tuple[Path, str, ClassificationSource, int], list[ClassificationEvidence]
    ] = {}
    for rule in rules:
        items = _evidence_for_rule(
            rule,
            filename,
            source=EvidenceSource.FILENAME,
            builtin_content_token_exclusions=builtin_content_token_exclusions,
        )
        if parent:
            items.extend(
                _evidence_for_rule(
                    rule,
                    parent,
                    source=EvidenceSource.SOURCE_PATH,
                    builtin_content_token_exclusions=builtin_content_token_exclusions,
                )
            )
        if content:
            items.extend(
                _evidence_for_rule(
                    rule,
                    content,
                    source=EvidenceSource.EXTRACTED_CONTENT,
                    builtin_content_token_exclusions=builtin_content_token_exclusions,
                )
            )
        unique: dict[
            tuple[EvidenceSource, MatchMechanism, str], ClassificationEvidence
        ] = {}
        for item in items:
            unique[_indicator_identity(item)] = item
        ordered = tuple(sorted(unique.values(), key=_evidence_order))
        if ordered:
            grouped.setdefault(
                (rule.folder, rule.rule_id, rule.origin, rule.precedence_tier), []
            ).extend(ordered)
    candidates: list[tuple[ClassificationCandidate, int]] = []
    for (folder, rule_id, origin, tier), items in grouped.items():
        unique = {_indicator_identity(item): item for item in items}
        ordered = tuple(sorted(unique.values(), key=_evidence_order))
        candidates.append(
            (
                ClassificationCandidate(
                    folder,
                    rule_id,
                    origin,
                    _aggregate_strength(ordered),
                    ordered,
                    next(
                        rule.taxonomy_priority
                        for rule in rules
                        if rule.rule_id == rule_id
                        and rule.origin is origin
                        and rule.precedence_tier == tier
                    ),
                ),
                tier,
            )
        )
    return tuple(candidates)


def _candidate_score(
    item: tuple[ClassificationCandidate, int],
) -> tuple[int, int, int, int, int, int]:
    candidate, tier = item
    diversity = len({evidence.source for evidence in candidate.evidence})
    has_descriptive_path = any(
        evidence.source in {EvidenceSource.FILENAME, EvidenceSource.SOURCE_PATH}
        for evidence in candidate.evidence
    )
    return (
        -_STRENGTH_ORDER[candidate.aggregate_strength],
        tier,
        -int(has_descriptive_path),
        (
            candidate.taxonomy_priority
            if candidate.taxonomy_priority is not None
            else 1_000_000
        ),
        -diversity,
        -len(candidate.evidence),
    )


def _candidate_key(
    item: tuple[ClassificationCandidate, int],
) -> tuple[int, int, int, int, int, int, str, str]:
    candidate, _ = item
    return (
        *_candidate_score(item),
        candidate.rule_id,
        str(candidate.folder),
    )


def _fallback_decision(
    *,
    folder: Path,
    profile: TaxonomyProfileName,
    outcome: ClassificationOutcome,
    candidates: tuple[ClassificationCandidate, ...],
    reason: str,
) -> ClassificationDecision:
    return ClassificationDecision(
        folder=folder,
        source=ClassificationSource.FALLBACK,
        reason=reason,
        rule_id=None,
        match_target="fallback",
        outcome=outcome,
        taxonomy_profile=profile,
        candidates=candidates,
    )


def infer_destination_with_evidence(
    path: Path,
    *,
    document_text: str,
    builtin_rules: Iterable[SemanticFolderRule],
    configured_rules: Iterable[SemanticFolderRule] | None,
    fallback_folder: str | None,
    rule_precedence: RulePrecedence,
    disabled_builtin_rules: Iterable[str],
    taxonomy_profile: TaxonomyProfileName,
    builtin_rule_priorities: Mapping[str, int],
    builtin_content_token_exclusions: frozenset[str],
) -> ClassificationDecision:
    """Gather candidates and make a deterministic, non-speculative decision."""
    rules = _compile_rules(
        builtin_rules,
        configured_rules,
        rule_precedence=rule_precedence,
        disabled_builtin_rules=disabled_builtin_rules,
        builtin_rule_priorities=builtin_rule_priorities,
    )
    ranked = tuple(
        sorted(
            _semantic_candidates(
                path,
                document_text,
                rules,
                builtin_content_token_exclusions=builtin_content_token_exclusions,
            ),
            key=_candidate_key,
        )
    )
    candidates = tuple(item[0] for item in ranked)
    if ranked:
        top, _ = ranked[0]
        top_score = _candidate_score(ranked[0])
        tied_folders = {
            candidate.folder
            for candidate, candidate_tier in ranked
            if _candidate_score((candidate, candidate_tier)) == top_score
        }
        fallback = (
            Path(fallback_folder)
            if fallback_folder is not None
            else Path(classify_path(path).value)
        )
        if top.aggregate_strength is not EvidenceStrength.STRONG:
            return _fallback_decision(
                folder=fallback,
                profile=taxonomy_profile,
                outcome=ClassificationOutcome.ABSTAINED,
                candidates=candidates,
                reason=(
                    "semantic evidence was insufficiently strong; selected "
                    "fallback folder " + repr(str(fallback))
                ),
            )
        if len(tied_folders) > 1:
            return _fallback_decision(
                folder=fallback,
                profile=taxonomy_profile,
                outcome=ClassificationOutcome.AMBIGUOUS,
                candidates=candidates,
                reason="equally ranked semantic candidates require fallback",
            )
        target = (
            "content"
            if all(
                evidence.source is EvidenceSource.EXTRACTED_CONTENT
                for evidence in top.evidence
            )
            else "path"
        )
        primary_source = (
            EvidenceSource.EXTRACTED_CONTENT
            if target == "content"
            else EvidenceSource.SOURCE_PATH
        )
        primary_text = (
            _prepare_content_search_text(document_text)
            if target == "content"
            else _normalize_search_text(" ".join(path.parts))
        )
        return ClassificationDecision(
            folder=top.folder,
            source=top.rule_origin,
            reason=_legacy_primary_reason(
                top,
                rules,
                primary_text,
                source=primary_source,
                builtin_content_token_exclusions=builtin_content_token_exclusions,
            ),
            rule_id=top.rule_id,
            match_target=target,
            outcome=ClassificationOutcome.SELECTED,
            taxonomy_profile=taxonomy_profile,
            selected_candidate=top,
            candidates=candidates,
        )
    suffixes = tuple(suffix.lower() for suffix in path.suffixes)
    if any(suffix in {".epub", ".azw3"} for suffix in suffixes):
        candidate = _mechanical_candidate(
            Path("books/fiction"),
            "builtin:special-case:ebook",
            ClassificationSource.SPECIAL_CASE,
            EvidenceSource.EXTENSION,
            MatchMechanism.SPECIAL_CASE,
            "ebook extension selected the built-in books/fiction special case",
            path.suffix.lower(),
        )
        return ClassificationDecision(
            candidate.folder,
            ClassificationSource.SPECIAL_CASE,
            candidate.evidence[0].reason,
            candidate.rule_id,
            "extension",
            ClassificationOutcome.SPECIAL_CASE,
            taxonomy_profile,
            candidate,
            (candidate,),
        )
    category = classify_path(path)
    if category.value != "documents":
        candidate = _mechanical_candidate(
            Path(category.value),
            f"extension:{category.value}",
            ClassificationSource.EXTENSION,
            EvidenceSource.EXTENSION,
            MatchMechanism.EXTENSION,
            f"extension classification selected category {category.value!r}",
            path.suffix.lower(),
        )
        return ClassificationDecision(
            candidate.folder,
            ClassificationSource.EXTENSION,
            candidate.evidence[0].reason,
            candidate.rule_id,
            "extension",
            ClassificationOutcome.EXTENSION,
            taxonomy_profile,
            candidate,
            (candidate,),
        )
    folder = (
        Path(fallback_folder) if fallback_folder is not None else Path(category.value)
    )
    return _fallback_decision(
        folder=folder,
        profile=taxonomy_profile,
        outcome=ClassificationOutcome.FALLBACK,
        candidates=(),
        reason=f"no semantic rule matched; selected fallback folder {str(folder)!r}",
    )


def _mechanical_candidate(
    folder: Path,
    rule_id: str,
    origin: ClassificationSource,
    source: EvidenceSource,
    mechanism: MatchMechanism,
    reason: str,
    value: str,
) -> ClassificationCandidate:
    evidence = ClassificationEvidence(
        rule_id,
        source,
        mechanism,
        EvidenceStrength.STRONG,
        reason,
        value,
    )
    return ClassificationCandidate(
        folder,
        rule_id,
        origin,
        EvidenceStrength.STRONG,
        (evidence,),
    )
