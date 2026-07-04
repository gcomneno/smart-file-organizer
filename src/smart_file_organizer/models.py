"""Domain models for file organization."""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Literal


class FileCategory(StrEnum):
    """Supported file categories."""

    ARCHIVES = "archives"
    AUDIO = "audio"
    CODE = "code"
    DOCUMENTS = "documents"
    IMAGES = "images"
    OTHER = "other"
    VIDEOS = "videos"


@dataclass(frozen=True)
class PlannedMove:
    """A planned file move that has not been executed yet."""

    source: Path
    destination: Path
    category: FileCategory


@dataclass(frozen=True)
class SemanticRuleDefinition:
    """A semantic destination rule with keyword and optional regex patterns."""

    folder: str
    keywords: tuple[str, ...] = ()
    patterns: tuple[str, ...] = ()


# Backward-compatible alias for keyword-only rules passed as tuples in tests.
SemanticFolderRule = SemanticRuleDefinition | tuple[str, tuple[str, ...]]
ConflictStrategy = Literal["fail", "rename"]
