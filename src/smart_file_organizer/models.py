"""Domain models for file organization."""

from dataclasses import dataclass, field
from datetime import datetime
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


class MoveStatus(StrEnum):
    """Durable execution states for one planned move."""

    UNATTEMPTED = "unattempted"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class ClassificationSource(StrEnum):
    """Origin of a destination classification decision."""

    BUILTIN_RULE = "built_in_rule"
    CONFIGURED_RULE = "configured_rule"
    SPECIAL_CASE = "special_case"
    EXTENSION = "extension"
    FALLBACK = "fallback"


ClassificationMatchTarget = Literal[
    "path",
    "content",
    "extension",
    "fallback",
]
RulePrecedence = Literal[
    "builtins-first",
    "configured-first",
]


@dataclass(frozen=True)
class ClassificationDecision:
    """Explain why one destination folder was selected."""

    folder: Path
    source: ClassificationSource
    reason: str
    rule_id: str | None = None
    match_target: ClassificationMatchTarget | None = None


@dataclass(frozen=True)
class PlannedMove:
    """A planned file move that has not been executed yet."""

    source: Path
    destination: Path
    category: FileCategory
    classification: ClassificationDecision | None = field(
        default=None,
        compare=False,
    )


@dataclass(frozen=True)
class MoveExecutionRecord:
    """Truthful outcome and recovery evidence for one planned move."""

    original_path: Path
    final_path: Path
    category: FileCategory
    status: MoveStatus
    timestamp: datetime
    error_type: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class ExecutionResult:
    """First-class result of applying a complete move plan."""

    manifest_path: Path
    started_at: datetime
    finished_at: datetime
    moves: tuple[MoveExecutionRecord, ...]

    def count(self, status: MoveStatus) -> int:
        """Return the number of moves with the selected status."""
        return sum(record.status == status for record in self.moves)

    @property
    def completed_count(self) -> int:
        """Return the number of completed moves."""
        return self.count(MoveStatus.COMPLETED)

    @property
    def failed_count(self) -> int:
        """Return the number of failed moves."""
        return self.count(MoveStatus.FAILED)

    @property
    def unattempted_count(self) -> int:
        """Return the number of moves that were not attempted."""
        return self.count(MoveStatus.UNATTEMPTED)

    @property
    def in_progress_count(self) -> int:
        """Return the number of moves left in an indeterminate state."""
        return self.count(MoveStatus.IN_PROGRESS)

    @property
    def successful(self) -> bool:
        """Return whether every planned move completed."""
        return (
            self.failed_count == 0
            and self.unattempted_count == 0
            and self.in_progress_count == 0
        )


@dataclass(frozen=True)
class SemanticRuleDefinition:
    """A semantic destination rule with keyword and optional regex patterns."""

    folder: str
    keywords: tuple[str, ...] = ()
    patterns: tuple[str, ...] = ()
    rule_id: str | None = None


# Backward-compatible alias for keyword-only rules passed as tuples in tests.
SemanticFolderRule = SemanticRuleDefinition | tuple[str, tuple[str, ...]]
ConflictStrategy = Literal["fail", "rename"]
