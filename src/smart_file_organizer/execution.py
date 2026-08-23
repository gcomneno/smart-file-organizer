"""Failure-aware move execution and durable apply manifests."""

import hashlib
import json
import os
import shutil
import stat
from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from smart_file_organizer.errors import (
    DestinationConflictError,
    DestinationExistsError,
    DestinationParentError,
    ManifestWriteError,
)
from smart_file_organizer.manifest_schema import execution_manifest_payload
from smart_file_organizer.models import (
    ExecutionResult,
    IdentityEvidence,
    MoveExecutionRecord,
    MoveStatus,
    PlannedMove,
)
from smart_file_organizer.path_validation import (
    validate_plan_destinations,
    validate_source_files,
)


MANIFEST_SCHEMA_VERSION = 2
_MANIFEST_DIRECTORY = Path(".smart-file-organizer") / "manifests"
_FINGERPRINT_CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True, slots=True)
class _Fingerprint:
    digest: str
    size_bytes: int
    observed_at: datetime


def _utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


def _absolute_path(path: Path) -> Path:
    """Return an absolute path without dereferencing symlinks."""
    return Path(os.path.abspath(path))


def _validate_destination_conflicts(moves: Iterable[PlannedMove]) -> None:
    """Reject duplicate final destinations before any filesystem mutation."""
    destinations: set[Path] = set()

    for move in moves:
        if move.destination in destinations:
            raise DestinationConflictError("plan contains destination conflicts")
        destinations.add(move.destination)


def _prepare_directory(path: Path, *, description: str) -> None:
    """Create and validate one directory used during apply."""
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise DestinationParentError(
            f"{description} is unusable: {path}: {error}"
        ) from error

    if not path.is_dir():
        raise DestinationParentError(f"{description} is not a directory: {path}")

    if not os.access(path, os.W_OK | os.X_OK):
        raise DestinationParentError(f"{description} is not writable: {path}")


def _prepare_destination_parents(moves: Iterable[PlannedMove]) -> None:
    """Create every destination parent before the first file is moved."""
    parents = sorted(
        {move.destination.parent for move in moves},
        key=lambda path: (len(path.parts), str(path)),
    )

    for parent in parents:
        _prepare_directory(parent, description="destination parent")


def _manifest_directory(target_root: Path) -> Path:
    """Return the absolute directory used for apply manifests."""
    return _absolute_path(target_root) / _MANIFEST_DIRECTORY


def _new_manifest_path(manifest_directory: Path, started_at: datetime) -> Path:
    """Return a collision-resistant manifest path."""
    timestamp = started_at.strftime("%Y%m%dT%H%M%S%fZ")
    identifier = uuid4().hex[:12]
    return manifest_directory / f"apply-{timestamp}-{identifier}.json"


def _initial_records(
    moves: Iterable[PlannedMove],
    timestamp: datetime,
) -> list[MoveExecutionRecord]:
    """Build initial unattempted records for the whole plan."""
    return [
        MoveExecutionRecord(
            original_path=_absolute_path(move.source),
            final_path=_absolute_path(move.destination),
            category=move.category,
            status=MoveStatus.UNATTEMPTED,
            timestamp=timestamp,
        )
        for move in moves
    ]


def _manifest_payload(
    *,
    target_root: Path,
    started_at: datetime,
    finished_at: datetime | None,
    records: Iterable[MoveExecutionRecord],
) -> dict[str, object]:
    """Build the complete JSON manifest payload."""
    return execution_manifest_payload(
        schema_version=MANIFEST_SCHEMA_VERSION,
        target_root=target_root,
        started_at=started_at,
        updated_at=_utc_now(),
        finished_at=finished_at,
        records=records,
    )


def _fsync_directory(path: Path) -> None:
    """Best-effort directory sync after atomically replacing a manifest."""
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)

    try:
        descriptor = os.open(path, flags)
    except OSError:
        return

    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def _write_manifest(
    manifest_path: Path,
    *,
    target_root: Path,
    started_at: datetime,
    finished_at: datetime | None,
    records: Iterable[MoveExecutionRecord],
) -> None:
    """Atomically persist and synchronize the current execution state."""
    temporary_path = manifest_path.with_name(
        f".{manifest_path.name}.{uuid4().hex}.tmp"
    )

    payload = _manifest_payload(
        target_root=target_root,
        started_at=started_at,
        finished_at=finished_at,
        records=records,
    )

    try:
        with temporary_path.open("x", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())

        os.replace(temporary_path, manifest_path)
        _fsync_directory(manifest_path.parent)
    except OSError as error:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass

        raise ManifestWriteError(
            f"could not persist apply manifest {manifest_path}: {error}"
        ) from error


def _fingerprint_regular_file(path: Path) -> _Fingerprint:
    """Observe one regular-file payload through one complete bounded stream."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except (OSError, ValueError) as error:
        raise OSError(
            f"could not fingerprint regular file: {path}: {error}"
        ) from error

    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise OSError(f"fingerprint path is not a regular file: {path}")

        digest = hashlib.sha256()
        size_bytes = 0
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = -1
            while chunk := stream.read(_FINGERPRINT_CHUNK_SIZE):
                digest.update(chunk)
                size_bytes += len(chunk)
    finally:
        if descriptor != -1:
            os.close(descriptor)

    return _Fingerprint(
        digest=digest.hexdigest(),
        size_bytes=size_bytes,
        observed_at=_utc_now(),
    )


def _identity_evidence(
    source: _Fingerprint,
    destination: _Fingerprint,
) -> IdentityEvidence:
    """Require two-sided equality before constructing complete identity evidence."""
    if source.digest != destination.digest or source.size_bytes != destination.size_bytes:
        raise OSError("destination fingerprint does not match source fingerprint")
    return IdentityEvidence(
        algorithm="sha256",
        digest=source.digest,
        size_bytes=source.size_bytes,
        source_observed_at=source.observed_at,
        destination_observed_at=destination.observed_at,
    )


def _move_completed(move: PlannedMove) -> None:
    """Verify the minimum observable postcondition of a successful move."""
    if not os.path.lexists(move.destination):
        raise OSError(f"move did not produce destination: {move.destination}")

    if os.path.lexists(move.source):
        raise OSError(f"source still exists after move: {move.source}")


def execute_plan(
    plan: Iterable[PlannedMove],
    target_root: Path,
) -> ExecutionResult:
    """Execute a plan, stopping at the first failure with durable evidence."""
    moves = list(plan)

    _validate_destination_conflicts(moves)
    validate_source_files(move.source for move in moves)
    validate_plan_destinations(moves, target_root)

    for move in moves:
        if os.path.lexists(move.destination):
            raise DestinationExistsError(
                f"destination already exists: {move.destination}"
            )

    _prepare_destination_parents(moves)

    manifest_directory = _manifest_directory(target_root)
    _prepare_directory(
        manifest_directory,
        description="apply manifest directory",
    )

    started_at = _utc_now()
    manifest_path = _new_manifest_path(manifest_directory, started_at)
    records = _initial_records(moves, started_at)

    _write_manifest(
        manifest_path,
        target_root=target_root,
        started_at=started_at,
        finished_at=None,
        records=records,
    )

    if not moves:
        finished_at = _utc_now()
        _write_manifest(
            manifest_path,
            target_root=target_root,
            started_at=started_at,
            finished_at=finished_at,
            records=records,
        )
        return ExecutionResult(
            manifest_path=manifest_path,
            started_at=started_at,
            finished_at=finished_at,
            moves=tuple(records),
        )

    for index, move in enumerate(moves):
        attempt_started_at = _utc_now()
        records[index] = replace(
            records[index],
            status=MoveStatus.IN_PROGRESS,
            timestamp=attempt_started_at,
            error_type=None,
            error_message=None,
            identity=None,
        )

        _write_manifest(
            manifest_path,
            target_root=target_root,
            started_at=started_at,
            finished_at=None,
            records=records,
        )

        try:
            move.destination.parent.mkdir(parents=True, exist_ok=True)
            source_fingerprint = _fingerprint_regular_file(move.source)
            shutil.move(move.source, move.destination)
            _move_completed(move)
            destination_fingerprint = _fingerprint_regular_file(move.destination)
            identity = _identity_evidence(source_fingerprint, destination_fingerprint)
        except OSError as error:
            failed_at = _utc_now()
            records[index] = replace(
                records[index],
                status=MoveStatus.FAILED,
                timestamp=failed_at,
                error_type=type(error).__name__,
                error_message=str(error),
                identity=None,
            )

            _write_manifest(
                manifest_path,
                target_root=target_root,
                started_at=started_at,
                finished_at=failed_at,
                records=records,
            )

            return ExecutionResult(
                manifest_path=manifest_path,
                started_at=started_at,
                finished_at=failed_at,
                moves=tuple(records),
            )

        completed_at = _utc_now()
        records[index] = replace(
            records[index],
            status=MoveStatus.COMPLETED,
            timestamp=completed_at,
            error_type=None,
            error_message=None,
            identity=identity,
        )

        finished_at = completed_at if index == len(moves) - 1 else None

        _write_manifest(
            manifest_path,
            target_root=target_root,
            started_at=started_at,
            finished_at=finished_at,
            records=records,
        )

    final_timestamp = records[-1].timestamp

    return ExecutionResult(
        manifest_path=manifest_path,
        started_at=started_at,
        finished_at=final_timestamp,
        moves=tuple(records),
    )


def format_execution_summary(result: ExecutionResult) -> str:
    """Return concise human-readable apply output."""
    lines = [
        (
            "Apply result: "
            f"completed={result.completed_count} "
            f"failed={result.failed_count} "
            f"unattempted={result.unattempted_count}"
        ),
        f"Manifest: {result.manifest_path}",
    ]

    failed_record = next(
        (record for record in result.moves if record.status == MoveStatus.FAILED),
        None,
    )

    if failed_record is not None:
        error = failed_record.error_message or "filesystem operation failed"
        lines.append(
            "Failed move: "
            f"{failed_record.original_path} -> {failed_record.final_path}: "
            f"{error}"
        )

    return "\n".join(lines) + "\n"
