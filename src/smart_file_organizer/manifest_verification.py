"""Read-only current filesystem reconciliation for historical manifests."""

import stat
from dataclasses import dataclass
from pathlib import Path

from smart_file_organizer.manifest_models import (
    ApplyManifest,
    CurrentIdentityObservation,
    IdentityObservationStatus,
    IdentityVerificationReason,
    IdentityVerificationState,
    ManifestMove,
    ManifestVerification,
    MoveIdentityVerification,
    MoveReconciliation,
    ReconciliationState,
)
from smart_file_organizer.models import MoveStatus
from smart_file_organizer.payload_identity import _fingerprint_regular_file


@dataclass(frozen=True, slots=True)
class _Observation:
    exists: bool | None
    unsafe: bool = False
    is_directory: bool = False
    is_symlink: bool = False
    path_unsafe: bool = False
    unsupported_file_type: bool = False
    observation_failed: bool = False


def verify_manifest(manifest: ApplyManifest) -> ManifestVerification:
    """Compare historical records to lstat-style current observations."""
    results: list[MoveReconciliation] = []
    summary = {state: 0 for state in ReconciliationState}
    for move in manifest.moves:
        source = _observe(move.original_path)
        destination = _observe(move.final_path)
        state = _state(move.status, source, destination)
        identity = _identity(move, destination)
        summary[state] += 1
        results.append(
            MoveReconciliation(
                move,
                state,
                source.exists,
                destination.exists,
                identity,
            )
        )
    return ManifestVerification(manifest, tuple(results), summary)


def _observe(path: Path) -> _Observation:
    """Observe only regular files without treating broken links as absent."""
    if _has_symlink_parent(path):
        return _Observation(None, unsafe=True, path_unsafe=True)
    try:
        info = path.lstat()
    except FileNotFoundError:
        return _Observation(False)
    except OSError:
        return _Observation(None, observation_failed=True)
    except ValueError:
        return _Observation(None, unsafe=True, path_unsafe=True)
    is_regular = stat.S_ISREG(info.st_mode)
    return _Observation(
        True,
        unsafe=not is_regular,
        is_directory=stat.S_ISDIR(info.st_mode),
        is_symlink=stat.S_ISLNK(info.st_mode),
        unsupported_file_type=not is_regular,
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


def _identity(
    move: ManifestMove, destination: _Observation
) -> MoveIdentityVerification:
    if (
        move.status is not MoveStatus.COMPLETED
        or move.identity is None
        or move.identity.algorithm != "sha256"
    ):
        return _identity_result(
            IdentityVerificationState.IDENTITY_UNVERIFIABLE,
            IdentityVerificationReason.HISTORICAL_IDENTITY_ABSENT,
            IdentityObservationStatus.NOT_OBSERVED,
        )
    unverifiable = _unverifiable_identity_from_destination(destination)
    if unverifiable is not None:
        return unverifiable

    current_destination = _observe(move.final_path)
    unverifiable = _unverifiable_identity_from_destination(current_destination)
    if unverifiable is not None:
        return unverifiable

    try:
        current = _fingerprint_regular_file(move.final_path)
    except OSError:
        return _identity_result(
            IdentityVerificationState.IDENTITY_UNVERIFIABLE,
            IdentityVerificationReason.OBSERVATION_FAILED,
            IdentityObservationStatus.OBSERVATION_FAILED,
        )

    observation = CurrentIdentityObservation(
        status=IdentityObservationStatus.FINGERPRINTED,
        algorithm="sha256",
        digest=current.digest,
        size_bytes=current.size_bytes,
        observed_at=current.observed_at,
    )
    if (
        move.identity.digest == current.digest
        and move.identity.size_bytes == current.size_bytes
    ):
        return MoveIdentityVerification(
            IdentityVerificationState.IDENTITY_MATCH,
            IdentityVerificationReason.IDENTITY_VERIFIED,
            observation,
        )
    return MoveIdentityVerification(
        IdentityVerificationState.IDENTITY_MISMATCH,
        IdentityVerificationReason.DESTINATION_CHANGED,
        observation,
    )


def _unverifiable_identity_from_destination(
    destination: _Observation,
) -> MoveIdentityVerification | None:
    if destination.exists is False:
        return _identity_result(
            IdentityVerificationState.IDENTITY_UNVERIFIABLE,
            IdentityVerificationReason.DESTINATION_MISSING,
            IdentityObservationStatus.MISSING,
        )
    if destination.path_unsafe:
        return _identity_result(
            IdentityVerificationState.IDENTITY_UNVERIFIABLE,
            IdentityVerificationReason.UNSAFE_PATH,
            IdentityObservationStatus.UNSAFE_PATH,
        )
    if destination.unsupported_file_type:
        return _identity_result(
            IdentityVerificationState.IDENTITY_UNVERIFIABLE,
            IdentityVerificationReason.UNSUPPORTED_FILE_TYPE,
            IdentityObservationStatus.UNSUPPORTED_FILE_TYPE,
        )
    if destination.exists is None:
        return _identity_result(
            IdentityVerificationState.IDENTITY_UNVERIFIABLE,
            IdentityVerificationReason.OBSERVATION_FAILED,
            IdentityObservationStatus.OBSERVATION_FAILED,
        )
    return None


def _identity_result(
    state: IdentityVerificationState,
    reason: IdentityVerificationReason,
    status: IdentityObservationStatus,
) -> MoveIdentityVerification:
    return MoveIdentityVerification(
        state,
        reason,
        CurrentIdentityObservation(status=status),
    )
