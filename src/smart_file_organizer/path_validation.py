"""Central path-safety invariants for planning and execution."""

from collections.abc import Iterable
from pathlib import Path

from smart_file_organizer.errors import (
    InvalidSourceError,
    SourceMissingError,
    UnsafePathError,
)
from smart_file_organizer.models import PlannedMove


def validate_source_file(source: Path) -> None:
    """Require an existing regular file, preserving file-symlink behavior."""
    if not source.exists():
        raise SourceMissingError(f"source file does not exist: {source}")
    if not source.is_file():
        raise InvalidSourceError(f"source path is not a file: {source}")


def validate_source_files(sources: Iterable[Path]) -> None:
    """Validate every source before planning or execution."""
    for source in sources:
        validate_source_file(source)


def validate_destination_folder(folder: str | Path) -> Path:
    """Return a normalized relative destination folder or raise."""
    candidate = Path(folder)
    if candidate.is_absolute():
        raise UnsafePathError(f"destination folder must be relative: {folder}")
    if ".." in candidate.parts:
        raise UnsafePathError(f"destination folder must not contain '..': {folder}")
    normalized = Path(*candidate.parts)
    if not candidate.parts or str(normalized) != str(folder):
        raise UnsafePathError(f"destination folder must be normalized: {folder}")
    return normalized


def validate_destination(destination: Path, target_root: Path) -> None:
    """Require the resolved destination to remain beneath the resolved target."""
    resolved_target = target_root.resolve()
    resolved_destination = destination.resolve()
    if (
        resolved_destination == resolved_target
        or not resolved_destination.is_relative_to(resolved_target)
    ):
        raise UnsafePathError(f"destination is outside target directory: {destination}")


def validate_plan_destinations(plan: Iterable[PlannedMove], target_root: Path) -> None:
    """Validate all final destinations against the target root."""
    for move in plan:
        validate_destination(move.destination, target_root)


def validate_scan_target(
    source_root: Path, target_root: Path, *, recursive: bool
) -> None:
    """Reject scan layouts that can ingest or overwrite their own source root."""
    resolved_source = source_root.resolve()
    resolved_target = target_root.resolve()
    if resolved_target == resolved_source:
        raise UnsafePathError("target directory must differ from source directory")
    if recursive and resolved_target.is_relative_to(resolved_source):
        raise UnsafePathError(
            "target directory must not be inside a recursively scanned source directory"
        )
