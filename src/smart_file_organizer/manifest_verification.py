"""Read-only current filesystem reconciliation for historical manifests."""

import stat
from dataclasses import dataclass
from pathlib import Path

from smart_file_organizer.manifest_models import (
    ApplyManifest,
    ManifestVerification,
    MoveReconciliation,
    ReconciliationState,
)
from smart_file_organizer.models import MoveStatus


@dataclass(frozen=True, slots=True)
class _Observation:
    exists: bool | None
    unsafe: bool = False
    is_directory: bool = False
    is_symlink: bool = False


def verify_manifest(manifest: ApplyManifest) -> ManifestVerification:
    """Compare historical records to lstat-style current observations."""
    results: list[MoveReconciliation] = []
    summary = {state: 0 for state in ReconciliationState}
    for move in manifest.moves:
        source = _observe(move.original_path)
        destination = _observe(move.final_path)
        state = _state(move.status, source, destination)
        summary[state] += 1
        results.append(
            MoveReconciliation(move, state, source.exists, destination.exists)
        )
    return ManifestVerification(manifest, tuple(results), summary)


def _observe(path: Path) -> _Observation:
    """Observe only regular files without treating broken links as absent."""
    if _has_symlink_parent(path):
        return _Observation(None, unsafe=True)
    try:
        info = path.lstat()
    except FileNotFoundError:
        return _Observation(False)
    except OSError:
        return _Observation(None)
    except ValueError:
        return _Observation(None, unsafe=True)
    is_regular = stat.S_ISREG(info.st_mode)
    return _Observation(
        True,
        unsafe=not is_regular,
        is_directory=stat.S_ISDIR(info.st_mode),
        is_symlink=stat.S_ISLNK(info.st_mode),
    )


def _has_symlink_parent(path: Path) -> bool:
    current = path.parent
    while current != current.parent:
        try:
            info = current.lstat()
        except FileNotFoundError:
            current = current.parent
            continue
        except OSError:
            return False
        except ValueError:
            return True
        if stat.S_ISLNK(info.st_mode):
            return True
        current = current.parent
    return False


def _state(
    status: MoveStatus,
    source: _Observation,
    destination: _Observation,
) -> ReconciliationState:
    if source.unsafe or destination.unsafe:
        return ReconciliationState.UNSAFE_PATH
    if source.exists is None or destination.exists is None:
        return ReconciliationState.INDETERMINATE
    if status is MoveStatus.IN_PROGRESS:
        return ReconciliationState.INDETERMINATE
    if status is MoveStatus.COMPLETED:
        if not source.exists and destination.exists:
            return ReconciliationState.CONSISTENT
        if source.exists and not destination.exists:
            return ReconciliationState.SOURCE_RESTORED
        if source.exists:
            return ReconciliationState.BOTH_PRESENT
        return ReconciliationState.BOTH_MISSING
    if status is MoveStatus.FAILED:
        if source.exists and not destination.exists:
            return ReconciliationState.CONSISTENT
        if not source.exists and destination.exists:
            return ReconciliationState.UNEXPECTED_DESTINATION
        if source.exists:
            return ReconciliationState.BOTH_PRESENT
        return ReconciliationState.DESTINATION_MISSING
    if source.exists and not destination.exists:
        return ReconciliationState.CONSISTENT
    if not source.exists and destination.exists:
        return ReconciliationState.UNEXPECTED_DESTINATION
    if source.exists:
        return ReconciliationState.BOTH_PRESENT
    return ReconciliationState.BOTH_MISSING
