"""Profile selection and configured-rule layering contracts."""

from pathlib import Path

from smart_file_organizer.models import (
    ClassificationOutcome,
    SemanticRuleDefinition,
    TaxonomyProfileName,
)
from smart_file_organizer.semantic_rules import infer_destination
from smart_file_organizer.taxonomy import builtin_content_token_exclusions


def test_personal_it_is_default_and_minimal_removes_personal_candidates() -> None:
    default = infer_destination(Path("Conto-FASTWEB-M000000000-20260501.pdf"))
    minimal = infer_destination(
        Path("Conto-FASTWEB-M000000000-20260501.pdf"),
        taxonomy_profile=TaxonomyProfileName.MINIMAL,
    )
    assert default.taxonomy_profile is TaxonomyProfileName.PERSONAL_IT
    assert default.outcome is ClassificationOutcome.SELECTED
    assert minimal.taxonomy_profile is TaxonomyProfileName.MINIMAL
    assert minimal.outcome is ClassificationOutcome.FALLBACK


def test_minimal_has_no_builtin_content_token_exclusions() -> None:
    assert builtin_content_token_exclusions(TaxonomyProfileName.MINIMAL) == frozenset()


def test_configured_rules_layer_over_both_profiles_and_precedence() -> None:
    configured = SemanticRuleDefinition(
        "documents/local-fastweb", keywords=("fastweb",), rule_id="local:fastweb"
    )
    minimal = infer_destination(
        Path("fastweb.pdf"),
        taxonomy_profile=TaxonomyProfileName.MINIMAL,
        semantic_rules=(configured,),
    )
    configured_first = infer_destination(
        Path("fastweb.pdf"),
        semantic_rules=(configured,),
        rule_precedence="configured-first",
    )
    builtin_first = infer_destination(Path("fastweb.pdf"), semantic_rules=(configured,))
    assert minimal.folder == Path("documents/local-fastweb")
    assert configured_first.folder == Path("documents/local-fastweb")
    assert builtin_first.folder == Path("documents/utilities/fastweb")


def test_disabled_builtin_remains_disabled_under_personal_it() -> None:
    decision = infer_destination(
        Path("CU2026_PERSON_A.pdf"),
        disabled_builtin_rules=("builtin:documents/taxes",),
    )
    assert decision.outcome is ClassificationOutcome.FALLBACK
