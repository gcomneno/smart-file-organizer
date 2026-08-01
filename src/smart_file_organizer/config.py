"""Configuration loading for smart-file-organizer."""

import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from smart_file_organizer.errors import ConfigError
from smart_file_organizer.models import RulePrecedence
from smart_file_organizer.path_validation import validate_destination_folder


DEFAULT_FALLBACK_FOLDER = "documents/inbox"


@dataclass(frozen=True)
class SemanticRule:
    """A configurable semantic destination rule."""

    folder: str
    keywords: tuple[str, ...] = ()
    patterns: tuple[str, ...] = ()
    rule_id: str | None = None


@dataclass(frozen=True)
class OrganizerConfig:
    """Application configuration loaded from a TOML file."""

    semantic_rules: tuple[SemanticRule, ...] = ()
    fallback_folder: str = DEFAULT_FALLBACK_FOLDER
    semantic_rule_precedence: RulePrecedence = "builtins-first"
    disabled_builtin_rules: tuple[str, ...] = ()


def load_config(path: Path) -> OrganizerConfig:
    """Load application configuration from a TOML file."""
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return parse_config(data)


def parse_config(data: Mapping[str, Any]) -> OrganizerConfig:
    """Parse application configuration from raw TOML data."""
    raw_rules = data.get("semantic_rules", [])

    if not isinstance(raw_rules, list):
        raise ConfigError("semantic_rules must be a list")

    semantic_rules = tuple(_parse_semantic_rule(rule) for rule in raw_rules)
    configured_ids = [
        rule.rule_id for rule in semantic_rules if rule.rule_id is not None
    ]

    if len(configured_ids) != len(set(configured_ids)):
        raise ConfigError("semantic rule ids must be unique")

    return OrganizerConfig(
        semantic_rules=semantic_rules,
        fallback_folder=_parse_fallback_folder(data),
        semantic_rule_precedence=_parse_rule_precedence(data),
        disabled_builtin_rules=_parse_disabled_builtin_rules(data),
    )


def _parse_rule_precedence(
    data: Mapping[str, Any],
) -> RulePrecedence:
    """Parse configured versus built-in rule precedence."""
    value = data.get(
        "semantic_rule_precedence",
        "builtins-first",
    )

    if not isinstance(value, str) or value not in {
        "builtins-first",
        "configured-first",
    }:
        raise ConfigError(
            "semantic_rule_precedence must be 'builtins-first' or 'configured-first'"
        )

    return value


def _parse_disabled_builtin_rules(
    data: Mapping[str, Any],
) -> tuple[str, ...]:
    """Parse stable built-in rule IDs to disable."""
    values = data.get("disabled_builtin_rules", [])

    if not isinstance(values, list):
        raise ConfigError("disabled_builtin_rules must be a list")

    parsed: list[str] = []

    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise ConfigError("disabled_builtin_rules must contain non-empty strings")

        rule_id = value.strip()

        if not rule_id.startswith("builtin:"):
            raise ConfigError("disabled built-in rule ids must start with 'builtin:'")

        parsed.append(rule_id)

    if len(parsed) != len(set(parsed)):
        raise ConfigError("disabled_builtin_rules must not contain duplicates")

    return tuple(parsed)


def _parse_fallback_folder(
    data: Mapping[str, Any],
) -> str:
    """Parse fallback folder from raw TOML data."""
    fallback_folder = data.get(
        "fallback_folder",
        DEFAULT_FALLBACK_FOLDER,
    )

    if not isinstance(fallback_folder, str) or not fallback_folder.strip():
        raise ConfigError("fallback_folder must be a non-empty string")

    parsed_folder = fallback_folder.strip()

    try:
        validate_destination_folder(parsed_folder)
    except ValueError as error:
        raise ConfigError(str(error)) from error

    return parsed_folder


def _parse_semantic_rule(data: object) -> SemanticRule:
    """Parse a semantic rule from raw TOML data."""
    if not isinstance(data, Mapping):
        raise ConfigError("semantic rule must be a table")

    folder = data.get("folder")
    keywords = data.get("keywords", [])
    patterns = data.get("patterns", [])
    rule_id = data.get("id")

    if not isinstance(folder, str) or not folder.strip():
        raise ConfigError("semantic rule folder must be a non-empty string")

    if rule_id is not None:
        if not isinstance(rule_id, str) or not rule_id.strip():
            raise ConfigError("semantic rule id must be a non-empty string")

        rule_id = rule_id.strip()

        if rule_id.startswith("builtin:"):
            raise ConfigError(
                "configured semantic rule ids must not "
                "use the reserved 'builtin:' prefix"
            )

    if keywords is None:
        keywords = []

    if patterns is None:
        patterns = []

    if not isinstance(keywords, list):
        raise ConfigError("semantic rule keywords must be a list")

    if not isinstance(patterns, list):
        raise ConfigError("semantic rule patterns must be a list")

    parsed_keywords: list[str] = []

    for keyword in keywords:
        if not isinstance(keyword, str) or not keyword.strip():
            raise ConfigError("semantic rule keywords must be non-empty strings")

        parsed_keywords.append(keyword)

    parsed_patterns: list[str] = []

    for pattern in patterns:
        if not isinstance(pattern, str) or not pattern.strip():
            raise ConfigError("semantic rule patterns must be non-empty strings")

        try:
            re.compile(pattern)
        except re.error as error:
            raise ConfigError(f"semantic rule pattern is invalid: {error}") from error

        parsed_patterns.append(pattern)

    if not parsed_keywords and not parsed_patterns:
        raise ConfigError("semantic rule must define keywords and/or patterns")

    parsed_folder = folder.strip()

    try:
        validate_destination_folder(parsed_folder)
    except ValueError as error:
        raise ConfigError(str(error)) from error

    return SemanticRule(
        folder=parsed_folder,
        keywords=tuple(parsed_keywords),
        patterns=tuple(parsed_patterns),
        rule_id=rule_id,
    )
