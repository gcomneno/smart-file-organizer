"""Behavioral contracts for explainable evidence decisions."""

from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import cast

import pytest

from smart_file_organizer.models import (
    ClassificationCandidate,
    ClassificationDecision,
    ClassificationEvidence,
    ClassificationOutcome,
    ClassificationSource,
    EvidenceSource,
    EvidenceStrength,
    MatchMechanism,
    SemanticRuleDefinition,
    TaxonomyProfileName,
)
from smart_file_organizer.plan_output import format_plan_json, format_plan_text
from smart_file_organizer.planning import plan_file_with_document_text
from smart_file_organizer.semantic_rules import infer_destination
from smart_file_organizer.taxonomy import PERSONAL_IT_CONTENT_TOKEN_EXCLUSIONS


def test_routed_fastweb_path_is_not_descriptive_evidence() -> None:
    decision = infer_destination(
        Path("report.txt"),
        document_text=(
            "/source/Conto-FASTWEB-M000000000-20260501.pdf\n"
            " -> /target/documents/utilities/fastweb/\n"
        ),
    )
    assert decision.outcome is ClassificationOutcome.FALLBACK
    assert decision.candidates == ()


def test_content_strength_and_filename_diversity_are_deterministic() -> None:
    weak = infer_destination(Path("report.txt"), document_text="fastweb")
    phrase = infer_destination(
        Path("report.txt"), document_text="Conto Fastweb per servizi"
    )
    combined = infer_destination(
        Path("fastweb-report.txt"), document_text="Conto Fastweb per servizi"
    )
    assert weak.outcome is ClassificationOutcome.ABSTAINED
    assert phrase.outcome is ClassificationOutcome.SELECTED
    assert combined.selected_candidate is not None
    assert {item.source for item in combined.selected_candidate.evidence} == {
        EvidenceSource.FILENAME,
        EvidenceSource.EXTRACTED_CONTENT,
    }


def test_minimal_configured_inps_token_is_weak_evidence_and_abstains() -> None:
    decision = infer_destination(
        Path("report.txt"),
        document_text="inps",
        semantic_rules=(
            SemanticRuleDefinition("documents/configured", keywords=("inps",)),
        ),
        taxonomy_profile=TaxonomyProfileName.MINIMAL,
    )

    assert decision.outcome is ClassificationOutcome.ABSTAINED
    assert decision.candidates[0].aggregate_strength is EvidenceStrength.WEAK
    assert decision.candidates[0].evidence[0].matched_value == "inps"


def test_distinct_configured_content_tokens_can_combine_to_strong() -> None:
    decision = infer_destination(
        Path("report.txt"),
        document_text="inps casefile",
        semantic_rules=(
            SemanticRuleDefinition(
                "documents/configured",
                keywords=("inps", "casefile"),
            ),
        ),
        taxonomy_profile=TaxonomyProfileName.MINIMAL,
    )

    assert decision.outcome is ClassificationOutcome.SELECTED
    assert decision.folder == Path("documents/configured")
    assert decision.selected_candidate is not None
    assert decision.selected_candidate.aggregate_strength is EvidenceStrength.STRONG
    assert [item.matched_value for item in decision.selected_candidate.evidence] == [
        "casefile",
        "inps",
    ]


def test_normalization_equivalent_rules_produce_one_weak_evidence_item() -> None:
    rules = (
        SemanticRuleDefinition("documents/configured", keywords=("token",)),
        SemanticRuleDefinition("documents/configured", keywords=(" token ",)),
    )

    decision = infer_destination(
        Path("report.txt"),
        document_text="token",
        semantic_rules=rules,
        taxonomy_profile=TaxonomyProfileName.MINIMAL,
    )

    assert decision.outcome is ClassificationOutcome.ABSTAINED
    assert len(decision.candidates) == 1
    candidate = decision.candidates[0]
    assert candidate.aggregate_strength is EvidenceStrength.WEAK
    assert [item.matched_value for item in candidate.evidence] == ["token"]


def test_normalization_equivalent_rules_are_order_independent() -> None:
    first = SemanticRuleDefinition("documents/configured", keywords=("token",))
    second = SemanticRuleDefinition("documents/configured", keywords=(" token ",))

    forward = infer_destination(
        Path("report.txt"),
        document_text="token",
        semantic_rules=(first, second),
        taxonomy_profile=TaxonomyProfileName.MINIMAL,
    )
    reverse = infer_destination(
        Path("report.txt"),
        document_text="token",
        semantic_rules=(second, first),
        taxonomy_profile=TaxonomyProfileName.MINIMAL,
    )

    assert forward == reverse


def test_duplicate_normalized_values_in_one_rule_count_once() -> None:
    decision = infer_destination(
        Path("report.txt"),
        document_text="token",
        semantic_rules=(
            SemanticRuleDefinition(
                "documents/configured", keywords=("token", " token ")
            ),
        ),
        taxonomy_profile=TaxonomyProfileName.MINIMAL,
    )

    candidate = decision.candidates[0]
    assert decision.outcome is ClassificationOutcome.ABSTAINED
    assert candidate.aggregate_strength is EvidenceStrength.WEAK
    assert len(candidate.evidence) == 1


def test_duplicate_patterns_canonicalize_rule_identity_and_count_once() -> None:
    one_pattern = SemanticRuleDefinition("documents/configured", patterns=(r"token",))
    duplicate_pattern = SemanticRuleDefinition(
        "documents/configured", patterns=(r"token", r"token")
    )

    single = infer_destination(
        Path("report.txt"),
        document_text="token",
        semantic_rules=(one_pattern,),
        taxonomy_profile=TaxonomyProfileName.MINIMAL,
    )
    duplicate = infer_destination(
        Path("report.txt"),
        document_text="token",
        semantic_rules=(duplicate_pattern,),
        taxonomy_profile=TaxonomyProfileName.MINIMAL,
    )

    assert single == duplicate
    assert len(duplicate.candidates[0].evidence) == 1


def test_same_keyword_in_filename_and_content_is_distinct_evidence() -> None:
    decision = infer_destination(
        Path("token.txt"),
        document_text="token",
        semantic_rules=(
            SemanticRuleDefinition("documents/configured", keywords=("token",)),
        ),
        taxonomy_profile=TaxonomyProfileName.MINIMAL,
    )

    candidate = decision.candidates[0]
    assert decision.outcome is ClassificationOutcome.SELECTED
    assert {item.source for item in candidate.evidence} == {
        EvidenceSource.FILENAME,
        EvidenceSource.EXTRACTED_CONTENT,
    }


@pytest.mark.parametrize("token", sorted(PERSONAL_IT_CONTENT_TOKEN_EXCLUSIONS))
def test_personal_it_builtin_generic_content_tokens_remain_excluded(token: str) -> None:
    decision = infer_destination(Path("report.txt"), document_text=token)

    assert decision.outcome is ClassificationOutcome.FALLBACK
    assert decision.candidates == ()


def test_generic_evidence_module_contains_no_personal_it_vocabulary() -> None:
    source = Path(__file__).parents[1] / "src/smart_file_organizer/evidence.py"
    evidence_source = source.read_text(encoding="utf-8")

    for token in PERSONAL_IT_CONTENT_TOKEN_EXCLUSIONS:
        assert repr(token) not in evidence_source


def test_filename_plus_content_outranks_content_only() -> None:
    rules = (
        SemanticRuleDefinition("documents/filename", keywords=("file signal",)),
        SemanticRuleDefinition("documents/content", keywords=("content phrase",)),
    )
    decision = infer_destination(
        Path("file-signal.txt"),
        document_text="file signal and content phrase",
        semantic_rules=rules,
        taxonomy_profile=TaxonomyProfileName.MINIMAL,
    )
    assert decision.folder == Path("documents/filename")


def test_content_regex_is_supporting_and_overlapping_matches_do_not_combine() -> None:
    rule = SemanticRuleDefinition(
        "documents/regex",
        keywords=("signal",),
        patterns=(r"signal",),
    )
    decision = infer_destination(
        Path("report.txt"),
        document_text="signal",
        semantic_rules=(rule,),
        taxonomy_profile=TaxonomyProfileName.MINIMAL,
    )
    candidate = decision.candidates[0]
    assert decision.outcome is ClassificationOutcome.ABSTAINED
    assert candidate.aggregate_strength is EvidenceStrength.SUPPORTING
    assert [item.mechanism for item in candidate.evidence] == [MatchMechanism.REGEX]


def test_source_path_and_filename_are_strong_but_equal_destinations_are_safe() -> None:
    source_path = infer_destination(Path("archive/yocto/generic.pdf"))
    filename = infer_destination(Path("CU2026_PERSON_A.pdf"))
    assert source_path.outcome is ClassificationOutcome.SELECTED
    assert source_path.selected_candidate is not None
    assert (
        source_path.selected_candidate.evidence[0].source is EvidenceSource.SOURCE_PATH
    )
    assert filename.outcome is ClassificationOutcome.SELECTED


def test_equally_ranked_destinations_are_ambiguous_in_stable_order() -> None:
    rules = (
        SemanticRuleDefinition(
            "documents/zeta", keywords=("shared phrase",), rule_id="z"
        ),
        SemanticRuleDefinition(
            "documents/alpha", keywords=("shared phrase",), rule_id="a"
        ),
    )
    decision = infer_destination(
        Path("report.txt"), document_text="shared phrase", semantic_rules=rules
    )
    assert decision.outcome is ClassificationOutcome.AMBIGUOUS
    assert [candidate.rule_id for candidate in decision.candidates] == ["a", "z"]
    assert {candidate.aggregate_strength for candidate in decision.candidates} == {
        EvidenceStrength.STRONG
    }
    assert decision.selected_candidate is None


@pytest.mark.parametrize(
    ("rules", "document_text", "strength"),
    [
        (
            (
                SemanticRuleDefinition(
                    "documents/zeta", keywords=("second",), rule_id="z"
                ),
                SemanticRuleDefinition(
                    "documents/alpha", keywords=("first",), rule_id="a"
                ),
            ),
            "first second",
            EvidenceStrength.WEAK,
        ),
        (
            (
                SemanticRuleDefinition(
                    "documents/zeta", patterns=(r"second",), rule_id="z"
                ),
                SemanticRuleDefinition(
                    "documents/alpha", patterns=(r"first",), rule_id="a"
                ),
            ),
            "first second",
            EvidenceStrength.SUPPORTING,
        ),
    ],
)
def test_tied_non_strong_candidates_abstain_in_deterministic_order(
    rules: tuple[SemanticRuleDefinition, ...],
    document_text: str,
    strength: EvidenceStrength,
) -> None:
    decision = infer_destination(
        Path("report.txt"),
        document_text=document_text,
        semantic_rules=rules,
        fallback_folder="documents/fallback",
        taxonomy_profile=TaxonomyProfileName.MINIMAL,
    )

    assert decision.outcome is ClassificationOutcome.ABSTAINED
    assert decision.folder == Path("documents/fallback")
    assert decision.source is ClassificationSource.FALLBACK
    assert [candidate.rule_id for candidate in decision.candidates] == ["a", "z"]
    assert {candidate.aggregate_strength for candidate in decision.candidates} == {
        strength
    }


def test_equivalent_configured_rules_are_order_independent() -> None:
    first = SemanticRuleDefinition("documents/demo", keywords=("demo phrase",))
    second = SemanticRuleDefinition("documents/demo", keywords=("demo phrase",))
    forward = infer_destination(
        Path("report.txt"), document_text="demo phrase", semantic_rules=(first, second)
    )
    reverse = infer_destination(
        Path("report.txt"), document_text="demo phrase", semantic_rules=(second, first)
    )
    assert forward == reverse


def test_evidence_graph_is_frozen_and_collection_safe() -> None:
    evidence = [
        ClassificationEvidence(
            "local:demo",
            EvidenceSource.FILENAME,
            MatchMechanism.TOKEN,
            EvidenceStrength.STRONG,
            "safe reason",
            "demo",
        )
    ]
    candidate = ClassificationCandidate(
        Path("documents/demo"),
        "local:demo",
        ClassificationSource.CONFIGURED_RULE,
        EvidenceStrength.STRONG,
        cast(tuple[ClassificationEvidence, ...], evidence),
    )
    evidence.clear()
    assert len(candidate.evidence) == 1
    with pytest.raises(FrozenInstanceError):
        setattr(candidate, "rule_id", "other")

    candidates = [candidate]
    decision = ClassificationDecision(
        Path("documents/demo"),
        ClassificationSource.CONFIGURED_RULE,
        "safe reason",
        candidates=cast(tuple[ClassificationCandidate, ...], candidates),
    )
    candidates.clear()
    assert decision.candidates == (candidate,)


@pytest.mark.parametrize(
    ("source", "outcome"),
    [
        (ClassificationSource.BUILTIN_RULE, ClassificationOutcome.SELECTED),
        (ClassificationSource.CONFIGURED_RULE, ClassificationOutcome.SELECTED),
        (ClassificationSource.EXTENSION, ClassificationOutcome.EXTENSION),
        (ClassificationSource.SPECIAL_CASE, ClassificationOutcome.SPECIAL_CASE),
        (ClassificationSource.FALLBACK, ClassificationOutcome.FALLBACK),
    ],
)
def test_legacy_decision_defaults_remain_coherent(
    source: ClassificationSource,
    outcome: ClassificationOutcome,
) -> None:
    decision = ClassificationDecision(Path("documents/demo"), source, "safe reason")
    assert decision.outcome is outcome
    assert decision.selected_candidate is None


def test_explain_output_reports_abstention_without_document_text() -> None:
    secret = "TOP SECRET EXTRACTED DOCUMENT CONTENT"
    move = plan_file_with_document_text(
        Path("report.txt"), Path("organized"), secret + " fastweb"
    )
    text = format_plan_text([move], explain=True)
    payload = format_plan_json([move], explain=True)
    assert "outcome=abstained" in text
    assert '"outcome": "abstained"' in payload
    assert secret not in text
    assert secret not in payload


def test_explain_output_reports_ambiguity() -> None:
    rules = (
        SemanticRuleDefinition("documents/one", keywords=("shared phrase",)),
        SemanticRuleDefinition("documents/two", keywords=("shared phrase",)),
    )
    move = plan_file_with_document_text(
        Path("report.txt"),
        Path("organized"),
        "shared phrase",
        semantic_rules=rules,
        taxonomy_profile=TaxonomyProfileName.MINIMAL,
    )
    assert "outcome=ambiguous" in format_plan_text([move], explain=True)
    assert '"outcome": "ambiguous"' in format_plan_json([move], explain=True)


def test_text_explain_output_includes_each_evidence_detail() -> None:
    move = plan_file_with_document_text(
        Path("fastweb-report.txt"),
        Path("organized"),
        "Conto Fastweb per servizi",
    )
    output = format_plan_text([move], explain=True)
    assert "selected=" in output
    assert "filename/token/strong/'fastweb'" in output
    assert "extracted_content/exact_phrase/strong/'conto fastweb'" in output
