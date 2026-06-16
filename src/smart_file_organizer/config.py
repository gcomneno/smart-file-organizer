"""Configuration loading for smart-file-organizer."""

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
    keywords: tuple[str, ...]


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
    keywords = data.get("keywords")

    if not isinstance(folder, str) or not folder.strip():
        raise ConfigError("semantic rule folder must be a non-empty string")

    if not isinstance(keywords, list) or not keywords:
        raise ConfigError("semantic rule keywords must be a non-empty list")

    parsed_keywords: list[str] = []
    for keyword in keywords:
        if not isinstance(keyword, str) or not keyword.strip():
            raise ConfigError("semantic rule keywords must be non-empty strings")

        parsed_keywords.append(keyword)

    return SemanticRule(
        folder=folder,
        keywords=tuple(parsed_keywords),
    )
