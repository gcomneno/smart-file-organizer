"""Domain models for file organization."""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


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


SemanticFolderRule = tuple[str, tuple[str, ...]]
