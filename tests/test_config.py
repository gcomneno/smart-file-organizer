from pathlib import Path

import pytest

from smart_file_organizer.errors import ConfigError
from smart_file_organizer.config import (
    DEFAULT_FALLBACK_FOLDER,
    OrganizerConfig,
    SemanticRule,
    load_config,
    parse_config,
)


def test_parse_config_returns_empty_config_for_empty_data() -> None:
    assert parse_config({}) == OrganizerConfig(fallback_folder="documents/inbox")


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


def test_parse_config_reads_regex_patterns() -> None:
    config = parse_config(
        {
            "semantic_rules": [
                {
                    "folder": "documents/analisi-mediche",
                    "patterns": [r"\d{8} analisi ade \d+"],
                },
                {
                    "folder": "books/fiction/demo-author",
                    "keywords": ["demo author"],
                    "patterns": [r"^demo author \d{4} "],
                },
            ],
        }
    )

    assert config == OrganizerConfig(
        semantic_rules=(
            SemanticRule(
                folder="documents/analisi-mediche",
                patterns=(r"\d{8} analisi ade \d+",),
            ),
            SemanticRule(
                folder="books/fiction/demo-author",
                keywords=("demo author",),
                patterns=(r"^demo author \d{4} ",),
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


def test_parse_config_reads_fallback_folder() -> None:
    config = parse_config(
        {
            "fallback_folder": "documents/inbox",
            "semantic_rules": [
                {
                    "folder": "documents/demo-utility",
                    "keywords": ["demo utility"],
                },
            ],
        }
    )

    assert config == OrganizerConfig(
        fallback_folder="documents/inbox",
        semantic_rules=(
            SemanticRule(
                folder="documents/demo-utility",
                keywords=("demo utility",),
            ),
        ),
    )


def test_parse_config_uses_default_fallback_folder_without_explicit_value() -> None:
    config = parse_config(
        {
            "semantic_rules": [
                {
                    "folder": "documents/demo-utility",
                    "keywords": ["demo utility"],
                },
            ],
        }
    )

    assert config.fallback_folder == DEFAULT_FALLBACK_FOLDER


def test_load_config_reads_fallback_folder_from_toml(tmp_path: Path) -> None:
    config_file = tmp_path / "smart-file-organizer.toml"
    config_file.write_text(
        """
fallback_folder = "documents/inbox"

[[semantic_rules]]
folder = "documents/demo-utility"
keywords = ["demo utility"]
""",
        encoding="utf-8",
    )

    assert load_config(config_file).fallback_folder == "documents/inbox"


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
            "semantic rule must define keywords and/or patterns",
        ),
        (
            {"semantic_rules": [{"folder": "documents/demo", "keywords": [""]}]},
            "semantic rule keywords must be non-empty strings",
        ),
        (
            {"semantic_rules": [{"folder": "documents/demo", "patterns": [""]}]},
            "semantic rule patterns must be non-empty strings",
        ),
        (
            {"semantic_rules": [{"folder": "documents/demo", "patterns": ["("]}]},
            "semantic rule pattern is invalid",
        ),
        ({"fallback_folder": ""}, "fallback_folder must be a non-empty string"),
        ({"fallback_folder": 123}, "fallback_folder must be a non-empty string"),
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


@pytest.mark.parametrize(
    "folder",
    ["/absolute/folder", "documents/../escaped", "documents//inbox"],
)
@pytest.mark.parametrize("field", ["fallback", "rule"])
def test_parse_config_rejects_unsafe_destination_folders(
    folder: str, field: str
) -> None:
    raw_config: dict[str, object]
    if field == "fallback":
        raw_config = {"fallback_folder": folder}
    else:
        raw_config = {"semantic_rules": [{"folder": folder, "keywords": ["demo"]}]}

    with pytest.raises(ConfigError, match="destination folder"):
        parse_config(raw_config)
