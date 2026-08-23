"""Private serialization and strict validation for supported manifest schemas."""

import json
import os
import re
from collections.abc import Iterable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from smart_file_organizer.errors import ManifestFormatError
from smart_file_organizer.manifest_models import (
    ApplyManifest,
    ManifestCounts,
    ManifestMove,
)
from smart_file_organizer.models import (
    FileCategory,
    IdentityEvidence,
    MoveExecutionRecord,
    MoveStatus,
)


_SUPPORTED_SCHEMA_VERSIONS = frozenset({1, 2})
_TOP_LEVEL_FIELDS = frozenset(
    {
        "schema_version",
        "state",
        "target_root",
        "started_at",
        "updated_at",
        "finished_at",
        "counts",
        "moves",
    }
)
_COUNT_FIELDS = frozenset(status.value for status in MoveStatus)
_MOVE_FIELDS_V1 = frozenset(
    {"original_path", "final_path", "category", "status", "timestamp", "error"}
)
_MOVE_FIELDS_V2 = _MOVE_FIELDS_V1 | {"identity"}
_ERROR_FIELDS = frozenset({"type", "message"})
_IDENTITY_FIELDS = frozenset(
    {
        "algorithm",
        "digest",
        "size_bytes",
        "source_observed_at",
        "destination_observed_at",
    }
)
_SHA256_HEX = re.compile(r"[0-9a-f]{64}\Z")


def execution_manifest_payload(
    *,
    schema_version: int,
    target_root: Path,
    started_at: datetime,
    updated_at: datetime,
    finished_at: datetime | None,
    records: Iterable[MoveExecutionRecord],
) -> dict[str, object]:
    """Serialize one supported writer payload without weakening schema boundaries."""
    if schema_version not in _SUPPORTED_SCHEMA_VERSIONS:
        raise ValueError(f"unsupported manifest schema version: {schema_version}")

    records_tuple = tuple(records)
    counts = {
        status.value: sum(record.status == status for record in records_tuple)
        for status in MoveStatus
    }
    state = (
        "running"
        if finished_at is None
        else (
            "failed"
            if any(
                record.status in {MoveStatus.FAILED, MoveStatus.IN_PROGRESS}
                for record in records_tuple
            )
            else "completed"
        )
    )
    moves: list[dict[str, object]] = []
    for record in records_tuple:
        move: dict[str, object] = {
            "original_path": str(record.original_path),
            "final_path": str(record.final_path),
            "category": record.category.value,
            "status": record.status.value,
            "timestamp": record.timestamp.isoformat(),
            "error": (
                None
                if record.error_type is None and record.error_message is None
                else {
                    "type": record.error_type or "OSError",
                    "message": record.error_message or "",
                }
            ),
        }
        if schema_version == 2:
            move["identity"] = _identity_payload(record.identity)
        moves.append(move)

    return {
        "schema_version": schema_version,
        "state": state,
        "target_root": str(Path(os.path.abspath(target_root))),
        "started_at": started_at.isoformat(),
        "updated_at": updated_at.isoformat(),
        "finished_at": finished_at.isoformat() if finished_at is not None else None,
        "counts": counts,
        "moves": moves,
    }


def _identity_payload(identity: IdentityEvidence | None) -> object:
    if identity is None:
        return None
    return {
        "algorithm": identity.algorithm,
        "digest": identity.digest,
        "size_bytes": identity.size_bytes,
        "source_observed_at": identity.source_observed_at.isoformat(),
        "destination_observed_at": identity.destination_observed_at.isoformat(),
    }


def loads_manifest(text: str, *, path: Path, expected_version: int) -> ApplyManifest:
    """Parse duplicate-key-safe JSON and dispatch to an explicit strict schema."""
    try:
        payload = json.loads(text, object_pairs_hook=_no_duplicate_object)
    except (json.JSONDecodeError, _DuplicateKeyError) as error:
        raise ManifestFormatError("manifest JSON is malformed") from error
    return validate_manifest(payload, path=path, expected_version=expected_version)


class _DuplicateKeyError(ValueError):
    pass


def _no_duplicate_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKeyError(key)
        result[key] = value
    return result


def _mapping(
    value: object, *, fields: frozenset[str], label: str
) -> Mapping[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise ManifestFormatError(f"manifest {label} fields are invalid")
    return cast(Mapping[str, Any], value)


def _integer(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ManifestFormatError(f"manifest {label} is invalid")
    return value


def _timestamp(value: object, *, label: str) -> datetime:
    if not isinstance(value, str):
        raise ManifestFormatError(f"manifest {label} is invalid")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ManifestFormatError(f"manifest {label} is invalid") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ManifestFormatError(f"manifest {label} is invalid")
    return parsed


def _absolute_canonical_path(value: object, *, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ManifestFormatError(f"manifest {label} is invalid")
    if "\x00" in value:
        raise ManifestFormatError(f"manifest {label} is invalid")
    if not os.path.isabs(value) or value.startswith("//"):
        raise ManifestFormatError(f"manifest {label} is unsafe")
    normalized = os.path.normpath(value)
    if value != normalized or ".." in Path(value).parts:
        raise ManifestFormatError(f"manifest {label} is unsafe")
    return Path(value)


def validate_manifest(
    payload: object, *, path: Path, expected_version: int
) -> ApplyManifest:
    """Validate one explicitly supported schema into immutable historical facts."""
    top = _mapping(payload, fields=_TOP_LEVEL_FIELDS, label="top-level")
    version = _integer(top["schema_version"], label="schema version")
    if (
        version not in _SUPPORTED_SCHEMA_VERSIONS
        or expected_version not in _SUPPORTED_SCHEMA_VERSIONS
    ):
        raise ManifestFormatError("manifest schema version is unsupported")

    state = top["state"]
    if not isinstance(state, str) or state not in {"running", "completed", "failed"}:
        raise ManifestFormatError("manifest execution state is invalid")
    target_root = _absolute_canonical_path(top["target_root"], label="target root")
    started_at = _timestamp(top["started_at"], label="started timestamp")
    updated_at = _timestamp(top["updated_at"], label="updated timestamp")
    finished_value = top["finished_at"]
    finished_at = (
        None
        if finished_value is None
        else _timestamp(finished_value, label="finished timestamp")
    )
    if updated_at < started_at or (
        finished_at is not None
        and (finished_at < started_at or finished_at > updated_at)
    ):
        raise ManifestFormatError("manifest timestamp ordering is invalid")

    raw_counts = _mapping(top["counts"], fields=_COUNT_FIELDS, label="counts")
    counts = ManifestCounts(
        **{
            key: _integer(raw_counts[key], label=f"count {key}")
            for key in _COUNT_FIELDS
        }
    )
    raw_moves = top["moves"]
    if not isinstance(raw_moves, list):
        raise ManifestFormatError("manifest moves are invalid")
    moves = tuple(
        _move(
            item,
            target_root,
            started_at,
            updated_at,
            schema_version=version,
        )
        for item in raw_moves
    )
    if finished_at is not None and any(move.timestamp > finished_at for move in moves):
        raise ManifestFormatError("manifest move timestamp ordering is invalid")
    if counts.total != len(moves) or any(
        counts.count(status) != sum(move.status is status for move in moves)
        for status in MoveStatus
    ):
        raise ManifestFormatError("manifest counts do not match move records")
    _validate_state(state, finished_at, moves)
    return ApplyManifest(
        path=path,
        schema_version=version,
        state=state,
        target_root=target_root,
        started_at=started_at,
        updated_at=updated_at,
        finished_at=finished_at,
        counts=counts,
        moves=moves,
    )


def _move(
    value: object,
    target_root: Path,
    started_at: datetime,
    updated_at: datetime,
    *,
    schema_version: int,
) -> ManifestMove:
    fields = _MOVE_FIELDS_V1 if schema_version == 1 else _MOVE_FIELDS_V2
    raw = _mapping(value, fields=fields, label="move")
    original = _absolute_canonical_path(raw["original_path"], label="original path")
    final = _absolute_canonical_path(raw["final_path"], label="final path")
    if (
        original == final
        or final == target_root
        or not final.is_relative_to(target_root)
    ):
        raise ManifestFormatError("manifest move paths are contradictory")
    try:
        category = FileCategory(raw["category"])
        status = MoveStatus(raw["status"])
    except (TypeError, ValueError) as error:
        raise ManifestFormatError(
            "manifest move category or status is invalid"
        ) from error
    timestamp = _timestamp(raw["timestamp"], label="move timestamp")
    if timestamp < started_at or timestamp > updated_at:
        raise ManifestFormatError("manifest move timestamp ordering is invalid")

    error_value = raw["error"]
    if status is MoveStatus.FAILED:
        error = _mapping(error_value, fields=_ERROR_FIELDS, label="move error")
        error_type, error_message = error["type"], error["message"]
        if (
            not isinstance(error_type, str)
            or not error_type
            or not isinstance(error_message, str)
        ):
            raise ManifestFormatError("manifest move error is invalid")
    else:
        if error_value is not None:
            raise ManifestFormatError("manifest move error is contradictory")
        error_type = error_message = None

    identity = None
    if schema_version == 2:
        identity_value = raw["identity"]
        if status is MoveStatus.COMPLETED:
            if identity_value is None:
                raise ManifestFormatError("manifest move identity is contradictory")
            identity = _identity(
                identity_value,
                started_at=started_at,
                updated_at=updated_at,
                move_timestamp=timestamp,
            )
        elif identity_value is not None:
            raise ManifestFormatError("manifest move identity is contradictory")

    return ManifestMove(
        original,
        final,
        category,
        status,
        timestamp,
        error_type,
        error_message,
        identity,
    )


def _identity(
    value: object,
    *,
    started_at: datetime,
    updated_at: datetime,
    move_timestamp: datetime,
) -> IdentityEvidence:
    raw = _mapping(value, fields=_IDENTITY_FIELDS, label="move identity")
    algorithm = raw["algorithm"]
    digest = raw["digest"]
    if algorithm != "sha256":
        raise ManifestFormatError("manifest move identity algorithm is invalid")
    if not isinstance(digest, str) or _SHA256_HEX.fullmatch(digest) is None:
        raise ManifestFormatError("manifest move identity digest is invalid")
    size_bytes = _integer(raw["size_bytes"], label="move identity size")
    source_observed_at = _timestamp(
        raw["source_observed_at"], label="source observation timestamp"
    )
    destination_observed_at = _timestamp(
        raw["destination_observed_at"], label="destination observation timestamp"
    )
    if (
        source_observed_at < started_at
        or source_observed_at > updated_at
        or destination_observed_at < source_observed_at
        or destination_observed_at > updated_at
        or move_timestamp < destination_observed_at
    ):
        raise ManifestFormatError("manifest move identity timestamp ordering is invalid")
    return IdentityEvidence(
        algorithm=algorithm,
        digest=digest,
        size_bytes=size_bytes,
        source_observed_at=source_observed_at,
        destination_observed_at=destination_observed_at,
    )


def _validate_state(
    state: object, finished_at: datetime | None, moves: tuple[ManifestMove, ...]
) -> None:
    statuses = tuple(move.status for move in moves)
    if state == "running":
        if (
            finished_at is not None
            or MoveStatus.FAILED in statuses
            or (
                bool(statuses)
                and all(status is MoveStatus.COMPLETED for status in statuses)
            )
            or not _writer_order(statuses, running=True)
        ):
            raise ManifestFormatError("manifest state is contradictory")
        return
    if finished_at is None:
        raise ManifestFormatError("manifest state is contradictory")
    if state == "completed" and all(
        status is MoveStatus.COMPLETED for status in statuses
    ):
        return
    if (
        state == "failed"
        and MoveStatus.FAILED in statuses
        and MoveStatus.IN_PROGRESS not in statuses
        and _writer_order(statuses, running=False)
    ):
        return
    raise ManifestFormatError("manifest state is contradictory")


def _writer_order(statuses: tuple[MoveStatus, ...], *, running: bool) -> bool:
    """Require the prefix-and-remainder ordering emitted by the writer."""
    if running:
        if not statuses:
            return True
        if all(status is MoveStatus.COMPLETED for status in statuses):
            return False
        first_unfinished = next(
            index
            for index, status in enumerate(statuses)
            if status is not MoveStatus.COMPLETED
        )
        remainder = statuses[first_unfinished:]
        if remainder[0] is MoveStatus.IN_PROGRESS:
            remainder = remainder[1:]
        return all(status is MoveStatus.UNATTEMPTED for status in remainder)

    terminal = MoveStatus.FAILED
    if statuses.count(terminal) != 1:
        return False
    index = statuses.index(terminal)
    return all(status is MoveStatus.COMPLETED for status in statuses[:index]) and all(
        status is MoveStatus.UNATTEMPTED for status in statuses[index + 1 :]
    )
