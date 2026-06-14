from pathlib import Path

import pytest

from smart_file_organizer.errors import ConfigError
from smart_file_organizer.config import (
    OrganizerConfig,
    SemanticRule,
    load_config,
    parse_config,
)


def test_parse_config_returns_empty_config_for_empty_data() -> None:
    assert parse_config({}) == OrganizerConfig()


def test_parse_config_reads_semantic_rules() -> None:
    config = parse_config(
        {
            "semantic_rules": [
                {
                    "folder": "documents/demo-utility",
                    "keywords": ["demo utility", "invoice"],
                },
                {
                    "folder": "learning/demo-course",
                    "keywords": ["demo course"],
                },
            ],
        }
    )

    assert config == OrganizerConfig(
        semantic_rules=(
            SemanticRule(
                folder="documents/demo-utility",
                keywords=("demo utility", "invoice"),
            ),
            SemanticRule(
                folder="learning/demo-course",
                keywords=("demo course",),
            ),
        )
    )


def test_load_config_reads_toml_file(tmp_path: Path) -> None:
    config_file = tmp_path / "smart-file-organizer.toml"
    config_file.write_text(
        """
[[semantic_rules]]
folder = "documents/demo-utility"
keywords = ["demo utility", "invoice"]
""",
        encoding="utf-8",
    )

    assert load_config(config_file) == OrganizerConfig(
        semantic_rules=(
            SemanticRule(
                folder="documents/demo-utility",
                keywords=("demo utility", "invoice"),
            ),
        )
    )


@pytest.mark.parametrize(
    ("raw_config", "message"),
    [
        ({"semantic_rules": "wrong"}, "semantic_rules must be a list"),
        ({"semantic_rules": ["wrong"]}, "semantic rule must be a table"),
        (
            {"semantic_rules": [{"folder": "", "keywords": ["demo"]}]},
            "semantic rule folder must be a non-empty string",
        ),
        (
            {"semantic_rules": [{"folder": "documents/demo", "keywords": []}]},
            "semantic rule keywords must be a non-empty list",
        ),
        (
            {"semantic_rules": [{"folder": "documents/demo", "keywords": [""]}]},
            "semantic rule keywords must be non-empty strings",
        ),
    ],
)
def test_parse_config_rejects_invalid_semantic_rules(
    raw_config: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        parse_config(raw_config)


def test_parse_config_raises_config_error_for_invalid_data() -> None:
    with pytest.raises(ConfigError, match="semantic_rules must be a list"):
        parse_config({"semantic_rules": "wrong"})
