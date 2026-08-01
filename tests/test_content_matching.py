import json
from pathlib import Path

import pytest

from smart_file_organizer.cli import main
from smart_file_organizer.core import (
    ClassificationSource,
    SemanticRuleDefinition,
    infer_destination,
)


_FASTWEB_PATH_REPORT = (
    "/some/source/Conto-FASTWEB-M000000000-20260501.pdf\n"
    "  -> /some/target/documents/utilities/fastweb/\n"
)
_FALLBACK_REASON = (
    "no semantic rule matched; selected fallback folder 'documents/inbox'"
)


def test_incidental_absolute_path_report_falls_back() -> None:
    decision = infer_destination(
        Path("diagnostic-report.txt"),
        document_text=_FASTWEB_PATH_REPORT,
    )

    assert decision.folder == Path("documents/inbox")
    assert decision.source == ClassificationSource.FALLBACK
    assert decision.rule_id is None
    assert decision.match_target == "fallback"
    assert decision.reason == _FALLBACK_REASON
    assert "Conto-FASTWEB" not in decision.reason


def test_genuine_fastweb_content_matches_builtin_rule() -> None:
    decision = infer_destination(
        Path("statement.txt"),
        document_text=(
            "FASTWEB S.p.A.\n"
            "Conto Fastweb per servizi di telecomunicazione\n"
            "Periodo di fatturazione: maggio 2026\n"
        ),
    )

    assert decision.folder == Path("documents/utilities/fastweb")
    assert decision.source == ClassificationSource.BUILTIN_RULE
    assert decision.rule_id == "builtin:documents/utilities/fastweb"
    assert decision.match_target == "content"
    assert decision.reason == (
        "builtin:documents/utilities/fastweb matched keyword 'fastweb' in content"
    )


def test_fastweb_filename_still_matches_through_path() -> None:
    decision = infer_destination(Path("Conto-FASTWEB-M000000000-20260501.pdf"))

    assert decision.folder == Path("documents/utilities/fastweb")
    assert decision.match_target == "path"
    assert decision.reason == (
        "builtin:documents/utilities/fastweb matched keyword 'fastweb' in path"
    )


@pytest.mark.parametrize(
    "document_text",
    [
        "/some/source/Conto FASTWEB maggio 2026.pdf\n",
        '"/some/source/Conto FASTWEB maggio 2026.pdf"\n',
        "C:\\some source\\Conto FASTWEB maggio 2026.pdf\n",
        '"C:\\some source\\Conto FASTWEB maggio 2026.pdf"\n',
    ],
)
def test_whole_line_absolute_filename_references_with_spaces_fall_back(
    document_text: str,
) -> None:
    decision = infer_destination(Path("diagnostic.txt"), document_text=document_text)

    assert decision.folder == Path("documents/inbox")
    assert decision.source == ClassificationSource.FALLBACK
    assert decision.match_target == "fallback"


@pytest.mark.parametrize("arrow", ("->", "=>", "→"))
def test_routing_directory_paths_with_spaces_without_extensions_fall_back(
    arrow: str,
) -> None:
    decision = infer_destination(
        Path("diagnostic.txt"),
        document_text=(
            f"/some source/input folder {arrow} /some target/fastweb archive\n"
        ),
    )

    assert decision.folder == Path("documents/inbox")
    assert decision.source == ClassificationSource.FALLBACK
    assert decision.match_target == "fallback"


def test_retained_descriptive_fastweb_content_still_matches() -> None:
    decision = infer_destination(
        Path("diagnostic.txt"),
        document_text=(
            _FASTWEB_PATH_REPORT
            + "FASTWEB S.p.A.\n"
            + "Conto Fastweb per servizi di telecomunicazione\n"
        ),
    )

    assert decision.folder == Path("documents/utilities/fastweb")
    assert decision.source == ClassificationSource.BUILTIN_RULE
    assert decision.match_target == "content"


def test_prose_with_embedded_absolute_filename_path_is_retained() -> None:
    decision = infer_destination(
        Path("diagnostic.txt"),
        document_text=(
            "See /some/archive/compatibility-signal.txt for descriptive details.\n"
        ),
        semantic_rules=(
            SemanticRuleDefinition(
                folder="private/compatibility",
                keywords=("compatibility signal",),
                rule_id="local:compatibility",
            ),
        ),
    )

    assert decision.folder == Path("private/compatibility")
    assert decision.source == ClassificationSource.CONFIGURED_RULE
    assert decision.match_target == "content"


@pytest.mark.parametrize(
    "document_text",
    [
        "Visit https://example.test/compatibility-signal for details.\n",
        "See relative/reports/compatibility-signal.txt for details.\n",
        "This ordinary descriptive compatibility signal is retained.\n",
    ],
)
def test_non_absolute_path_like_content_is_retained(document_text: str) -> None:
    decision = infer_destination(
        Path("diagnostic.txt"),
        document_text=document_text,
        semantic_rules=(
            SemanticRuleDefinition(
                folder="private/compatibility",
                keywords=("compatibility signal",),
                rule_id="local:compatibility",
            ),
        ),
    )

    assert decision.folder == Path("private/compatibility")
    assert decision.source == ClassificationSource.CONFIGURED_RULE
    assert decision.rule_id == "local:compatibility"
    assert decision.match_target == "content"


def test_configured_rule_preserves_precedence_and_ignores_path_only_phrase() -> None:
    rule = SemanticRuleDefinition(
        folder="private/fastweb-diagnostics",
        keywords=("fastweb diagnostic record",),
        rule_id="local:fastweb-diagnostics",
    )

    descriptive_decision = infer_destination(
        Path("diagnostic.txt"),
        document_text="Fastweb diagnostic record for review.\n",
        semantic_rules=(rule,),
        rule_precedence="configured-first",
    )
    path_only_decision = infer_destination(
        Path("diagnostic.txt"),
        document_text=(
            "/some/source/fastweb-diagnostic-record.pdf -> /some/target/archive/\n"
        ),
        semantic_rules=(rule,),
        rule_precedence="configured-first",
    )

    assert descriptive_decision.folder == Path("private/fastweb-diagnostics")
    assert descriptive_decision.source == ClassificationSource.CONFIGURED_RULE
    assert descriptive_decision.rule_id == "local:fastweb-diagnostics"
    assert descriptive_decision.match_target == "content"
    assert path_only_decision.folder == Path("documents/inbox")
    assert path_only_decision.source == ClassificationSource.FALLBACK
    assert path_only_decision.match_target == "fallback"


def test_cli_content_inspection_falls_back_without_leaking_report(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = tmp_path / "diagnostic.txt"
    target = tmp_path / "organized"
    report.write_text(_FASTWEB_PATH_REPORT)

    main(
        [
            "--inspect-content",
            "--format",
            "json",
            "--explain",
            "--target",
            str(target),
            str(report),
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert payload[0]["destination"] == str(target / "documents/inbox/diagnostic.txt")
    assert payload[0]["classification"] == {
        "folder": "documents/inbox",
        "source": "fallback",
        "rule_id": None,
        "match_target": "fallback",
        "reason": _FALLBACK_REASON,
    }
    assert not target.exists()
    assert _FASTWEB_PATH_REPORT not in captured.out
    assert _FASTWEB_PATH_REPORT not in captured.err
