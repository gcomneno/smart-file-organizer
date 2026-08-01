import json
from pathlib import Path

import pytest

from smart_file_organizer.cli import main
from smart_file_organizer.config import (
    OrganizerConfig,
    SemanticRule,
    parse_config,
)
from smart_file_organizer.core import (
    ClassificationSource,
    SemanticRuleDefinition,
    infer_destination,
    plan_file,
)
from smart_file_organizer.errors import ConfigError
from smart_file_organizer.plan_output import (
    format_plan_json,
    format_plan_text,
)


def configured_tax_rule() -> SemanticRuleDefinition:
    """Return a configured rule that overlaps the tax built-in."""
    return SemanticRuleDefinition(
        folder="private/tax-archive",
        keywords=("cu2026", "certificazione unica"),
        rule_id="local:tax-archive",
    )


def test_existing_config_defaults_preserve_builtin_first_semantics() -> None:
    config = parse_config(
        {
            "semantic_rules": [
                {
                    "folder": "private/tax-archive",
                    "keywords": ["cu2026"],
                }
            ]
        }
    )

    assert config.semantic_rule_precedence == "builtins-first"
    assert config.disabled_builtin_rules == ()


def test_parse_config_reads_override_and_disabled_rules() -> None:
    config = parse_config(
        {
            "semantic_rule_precedence": "configured-first",
            "disabled_builtin_rules": [
                "builtin:documents/vehicle",
            ],
            "semantic_rules": [
                {
                    "id": "local:tax-archive",
                    "folder": "private/tax-archive",
                    "keywords": ["cu2026"],
                }
            ],
        }
    )

    assert config == OrganizerConfig(
        semantic_rules=(
            SemanticRule(
                folder="private/tax-archive",
                keywords=("cu2026",),
                rule_id="local:tax-archive",
            ),
        ),
        semantic_rule_precedence="configured-first",
        disabled_builtin_rules=("builtin:documents/vehicle",),
    )


@pytest.mark.parametrize(
    ("raw_config", "message"),
    [
        (
            {"semantic_rule_precedence": "random"},
            "semantic_rule_precedence must be",
        ),
        (
            {"disabled_builtin_rules": "wrong"},
            "disabled_builtin_rules must be a list",
        ),
        (
            {"disabled_builtin_rules": ["documents/taxes"]},
            "must start with 'builtin:'",
        ),
        (
            {
                "semantic_rules": [
                    {
                        "id": "",
                        "folder": "documents/demo",
                        "keywords": ["demo"],
                    }
                ]
            },
            "semantic rule id must be",
        ),
        (
            {
                "semantic_rules": [
                    {
                        "id": "local:same",
                        "folder": "documents/one",
                        "keywords": ["one"],
                    },
                    {
                        "id": "local:same",
                        "folder": "documents/two",
                        "keywords": ["two"],
                    },
                ]
            },
            "semantic rule ids must be unique",
        ),
    ],
)
def test_parse_config_rejects_invalid_override_policy(
    raw_config: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ConfigError, match=message):
        parse_config(raw_config)


def test_builtin_first_keeps_compatible_first_match() -> None:
    decision = infer_destination(
        Path("CU2026_PERSON_A.pdf"),
        semantic_rules=(configured_tax_rule(),),
    )

    assert decision.folder == Path("documents/taxes")
    assert decision.source == ClassificationSource.BUILTIN_RULE
    assert decision.rule_id == "builtin:documents/taxes"
    assert decision.match_target == "path"


def test_configured_first_overrides_builtin_match() -> None:
    decision = infer_destination(
        Path("CU2026_PERSON_A.pdf"),
        semantic_rules=(configured_tax_rule(),),
        rule_precedence="configured-first",
    )

    assert decision.folder == Path("private/tax-archive")
    assert decision.source == ClassificationSource.CONFIGURED_RULE
    assert decision.rule_id == "local:tax-archive"
    assert decision.match_target == "path"


def test_disabling_builtin_rule_allows_document_fallback() -> None:
    decision = infer_destination(
        Path("CU2026_PERSON_A.pdf"),
        disabled_builtin_rules=("builtin:documents/taxes",),
    )

    assert decision.folder == Path("documents/inbox")
    assert decision.source == ClassificationSource.FALLBACK
    assert decision.rule_id is None
    assert decision.match_target == "fallback"


def test_parent_directory_influences_path_classification() -> None:
    decision = infer_destination(
        Path("archive/yocto/generic.pdf"),
    )

    assert decision.folder == Path("learning/yocto")
    assert decision.rule_id == "builtin:learning/yocto"
    assert decision.match_target == "path"
    assert "yocto" in decision.reason


def test_configured_content_match_reports_content_target() -> None:
    decision = infer_destination(
        Path("generic.pdf"),
        document_text=("Demo Fiscal Agency\nAnnual private archive statement\n"),
        semantic_rules=(
            SemanticRuleDefinition(
                folder="private/annual-statements",
                keywords=("demo fiscal agency",),
                rule_id="local:annual-statements",
            ),
        ),
    )

    assert decision.folder == Path("private/annual-statements")
    assert decision.source == (ClassificationSource.CONFIGURED_RULE)
    assert decision.rule_id == "local:annual-statements"
    assert decision.match_target == "content"


def test_planned_move_retains_classification_evidence() -> None:
    move = plan_file(
        Path("CU2026_PERSON_A.pdf"),
        Path("organized"),
        semantic_rules=(configured_tax_rule(),),
        rule_precedence="configured-first",
    )

    assert move.destination == Path("organized/private/tax-archive/CU2026_PERSON_A.pdf")
    assert move.classification is not None
    assert move.classification.rule_id == "local:tax-archive"


def test_default_text_preview_remains_compatible() -> None:
    move = plan_file(
        Path("photo.jpg"),
        Path("organized"),
    )

    assert format_plan_text([move]) == ("photo.jpg -> organized/images/photo.jpg\n")


def test_explained_text_preview_identifies_rule_and_reason() -> None:
    move = plan_file(
        Path("CU2026_PERSON_A.pdf"),
        Path("organized"),
        semantic_rules=(configured_tax_rule(),),
        rule_precedence="configured-first",
    )

    output = format_plan_text(
        [move],
        explain=True,
    )

    assert "source=configured_rule" in output
    assert "rule=local:tax-archive" in output
    assert "target=path" in output
    assert "matched keyword" in output


def test_explained_json_preview_contains_classification_object() -> None:
    move = plan_file(
        Path("CU2026_PERSON_A.pdf"),
        Path("organized"),
    )

    payload = json.loads(
        format_plan_json(
            [move],
            explain=True,
        )
    )

    assert payload[0]["classification"] == {
        "folder": "documents/taxes",
        "source": "built_in_rule",
        "rule_id": "builtin:documents/taxes",
        "match_target": "path",
        "reason": ("builtin:documents/taxes matched keyword 'cu2026' in path"),
    }


def test_cli_configured_first_override_is_explainable(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "CU2026_PERSON_A.pdf"
    target = tmp_path / "organized"
    config = tmp_path / "organizer.toml"

    source.write_bytes(b"synthetic")
    config.write_text(
        """
semantic_rule_precedence = "configured-first"

[[semantic_rules]]
id = "local:tax-archive"
folder = "private/tax-archive"
keywords = ["cu2026"]
""",
        encoding="utf-8",
    )

    main(
        [
            "--config",
            str(config),
            "--target",
            str(target),
            "--format",
            "json",
            "--explain",
            str(source),
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert captured.err == ""
    assert payload[0]["destination"] == str(
        target / "private" / "tax-archive" / source.name
    )
    assert payload[0]["classification"]["rule_id"] == ("local:tax-archive")
    assert payload[0]["classification"]["source"] == ("configured_rule")


def test_cli_can_disable_applicable_builtin_rule(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "CU2026_PERSON_A.pdf"
    target = tmp_path / "organized"
    config = tmp_path / "organizer.toml"

    source.write_bytes(b"synthetic")
    config.write_text(
        """
disabled_builtin_rules = [
  "builtin:documents/taxes",
]
""",
        encoding="utf-8",
    )

    main(
        [
            "--config",
            str(config),
            "--target",
            str(target),
            str(source),
        ]
    )

    captured = capsys.readouterr()

    assert captured.err == ""
    assert captured.out == (
        f"{source} -> {target / 'documents' / 'inbox' / source.name}\n"
    )


def test_cli_help_documents_explanation_mode(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["plan", "--help"])

    captured = capsys.readouterr()
    normalized = " ".join(captured.out.split())

    assert exc_info.value.code == 0
    assert "--explain" in normalized
    assert "classification source, rule, match target" in normalized
