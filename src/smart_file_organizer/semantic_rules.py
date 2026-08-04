"""Compatibility facade joining taxonomy data to the generic evidence engine."""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from smart_file_organizer.evidence import infer_destination_with_evidence
from smart_file_organizer.models import (
    ClassificationDecision,
    ClassificationSource,
    RulePrecedence,
    SemanticFolderRule,
    SemanticRuleDefinition,
    TaxonomyProfileName,
)
from smart_file_organizer.taxonomy import (
    PERSONAL_IT_RULES,
    builtin_content_token_exclusions,
    builtin_rule_priorities,
    builtin_rules,
)


# Historical private names remain available to legacy internal imports.  The
# table itself lives in taxonomy.py; no matching mechanics live here.
_SEMANTIC_FOLDER_RULES = PERSONAL_IT_RULES


@dataclass(frozen=True)
class _CompiledSemanticRule:
    folder: str
    keywords: tuple[str, ...]
    compiled_patterns: tuple[re.Pattern[str], ...]
    rule_id: str
    source: ClassificationSource


def _coerce(rule: SemanticFolderRule) -> SemanticRuleDefinition:
    if isinstance(rule, SemanticRuleDefinition):
        return rule
    folder, keywords = rule
    return SemanticRuleDefinition(folder=folder, keywords=keywords)


def _normalize_semantic_rules(
    semantic_rules: Iterable[SemanticFolderRule] | None,
    *,
    rule_precedence: RulePrecedence = "builtins-first",
    disabled_builtin_rules: Iterable[str] = (),
    taxonomy_profile: TaxonomyProfileName = TaxonomyProfileName.PERSONAL_IT,
) -> tuple[_CompiledSemanticRule, ...]:
    """Legacy inspection helper; engine selection does not depend on its order."""
    disabled = frozenset(disabled_builtin_rules)
    builtins = [
        _compiled(_coerce(item), ClassificationSource.BUILTIN_RULE)
        for item in builtin_rules(taxonomy_profile)
    ]
    builtins = [item for item in builtins if item.rule_id not in disabled]
    configured = [
        _compiled(_coerce(item), ClassificationSource.CONFIGURED_RULE)
        for item in semantic_rules or ()
    ]
    if rule_precedence == "configured-first":
        return tuple(configured + builtins)
    return tuple(builtins + configured)


def _compiled(
    rule: SemanticRuleDefinition,
    source: ClassificationSource,
) -> _CompiledSemanticRule:
    default_id = (
        f"builtin:{rule.folder}"
        if source is ClassificationSource.BUILTIN_RULE
        else f"configured:{rule.folder}"
    )
    rule_id = rule.rule_id or default_id
    return _CompiledSemanticRule(
        folder=rule.folder,
        keywords=tuple(rule.keywords),
        compiled_patterns=tuple(re.compile(pattern) for pattern in rule.patterns),
        rule_id=rule_id,
        source=source,
    )


def infer_destination(
    path: Path,
    *,
    document_text: str = "",
    semantic_rules: Iterable[SemanticFolderRule] | None = None,
    fallback_folder: str | None = "documents/inbox",
    rule_precedence: RulePrecedence = "builtins-first",
    disabled_builtin_rules: Iterable[str] = (),
    taxonomy_profile: TaxonomyProfileName = TaxonomyProfileName.PERSONAL_IT,
) -> ClassificationDecision:
    """Infer one destination using all available evidence, not first-match order."""
    return infer_destination_with_evidence(
        path,
        document_text=document_text,
        builtin_rules=builtin_rules(taxonomy_profile),
        configured_rules=semantic_rules,
        fallback_folder=fallback_folder,
        rule_precedence=rule_precedence,
        disabled_builtin_rules=disabled_builtin_rules,
        taxonomy_profile=taxonomy_profile,
        builtin_rule_priorities=builtin_rule_priorities(taxonomy_profile),
        builtin_content_token_exclusions=builtin_content_token_exclusions(
            taxonomy_profile
        ),
    )


def infer_destination_folder(
    path: Path,
    *,
    document_text: str = "",
    semantic_rules: Iterable[SemanticFolderRule] | None = None,
    fallback_folder: str | None = "documents/inbox",
    rule_precedence: RulePrecedence = "builtins-first",
    disabled_builtin_rules: Iterable[str] = (),
    taxonomy_profile: TaxonomyProfileName = TaxonomyProfileName.PERSONAL_IT,
) -> Path:
    """Infer a destination folder while preserving the historical helper API."""
    return infer_destination(
        path,
        document_text=document_text,
        semantic_rules=semantic_rules,
        fallback_folder=fallback_folder,
        rule_precedence=rule_precedence,
        disabled_builtin_rules=disabled_builtin_rules,
        taxonomy_profile=taxonomy_profile,
    ).folder
