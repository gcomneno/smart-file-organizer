"""Configuration loading for smart-file-organizer."""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import tomllib

from smart_file_organizer.errors import ConfigError


@dataclass(frozen=True)
class SemanticRule:
    """A configurable semantic destination rule."""

    folder: str
    keywords: tuple[str, ...] = ()
    patterns: tuple[str, ...] = ()


@dataclass(frozen=True)
class OrganizerConfig:
    """Application configuration loaded from a TOML file."""

    semantic_rules: tuple[SemanticRule, ...] = ()


def load_config(path: Path) -> OrganizerConfig:
    """Load application configuration from a TOML file."""
    data = tomllib.loads(path.read_text(encoding="utf-8"))

    return parse_config(data)


def parse_config(data: Mapping[str, Any]) -> OrganizerConfig:
    """Parse application configuration from raw TOML data."""
    raw_rules = data.get("semantic_rules", [])

    if not isinstance(raw_rules, list):
        raise ConfigError("semantic_rules must be a list")

    return OrganizerConfig(
        semantic_rules=tuple(_parse_semantic_rule(rule) for rule in raw_rules),
    )


def _parse_semantic_rule(data: object) -> SemanticRule:
    """Parse a semantic rule from raw TOML data."""
    if not isinstance(data, Mapping):
        raise ConfigError("semantic rule must be a table")

    folder = data.get("folder")
    keywords = data.get("keywords", [])
    patterns = data.get("patterns", [])

    if not isinstance(folder, str) or not folder.strip():
        raise ConfigError("semantic rule folder must be a non-empty string")

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

    return SemanticRule(
        folder=folder,
        keywords=tuple(parsed_keywords),
        patterns=tuple(parsed_patterns),
    )
