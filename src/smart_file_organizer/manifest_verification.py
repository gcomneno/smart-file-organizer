"""Read-only current filesystem reconciliation for historical manifests."""

import stat
from dataclasses import dataclass
from dataclasses import replace
from pathlib import Path

from smart_file_organizer.manifest_models import (
    ApplyManifest,
    CurrentIdentityObservation,
    CurrentPathObservation,
    IdentityObservationStatus,
    IdentityVerificationReason,
    IdentityVerificationState,
    ManifestMove,
    ManifestVerification,
    MoveIdentityVerification,
    MoveReconciliation,
    PathObservationStatus,
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
    parent_topology_safe: bool | None = True
    parent_missing: bool = False
    containment_safe: bool | None = None

    def to_path_observation(self, path: Path) -> CurrentPathObservation:
        return CurrentPathObservation(
            path=path,
            status=_path_observation_status(self),
            leaf_exists=self.exists,
            parent_topology_safe=self.parent_topology_safe,
            parent_missing=self.parent_missing,
            containment_safe=self.containment_safe,
        )


def verify_manifest(manifest: ApplyManifest) -> ManifestVerification:
    """Compare historical records to lstat-style current observations."""
    results: list[MoveReconciliation] = []
    summary = {state: 0 for state in ReconciliationState}
    for move in manifest.moves:
        source = _observe(move.original_path)
        destination = _with_containment(
            _observe(move.final_path),
            move.final_path,
            manifest.target_root,
        )
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
                source.to_path_observation(move.original_path),
                destination.to_path_observation(move.final_path),
            )
        )
    return ManifestVerification(manifest, tuple(results), summary)


def _observe(path: Path) -> _Observation:
    """Observe only regular files without treating broken links as absent."""
    parent = _observe_parent_topology(path)
    if parent.unsafe:
        return _Observation(
            None,
            unsafe=True,
            path_unsafe=True,
            parent_topology_safe=False,
            parent_missing=parent.missing,
        )
    if parent.observation_failed:
        return _Observation(
            None,
            observation_failed=True,
            parent_topology_safe=None,
            parent_missing=parent.missing,
        )
    try:
        info = path.lstat()
    except FileNotFoundError:
        return _Observation(
            False,
            parent_topology_safe=True,
            parent_missing=parent.missing,
        )
    except OSError:
        return _Observation(
            None,
            observation_failed=True,
            parent_topology_safe=True,
            parent_missing=parent.missing,
        )
    except ValueError:
        return _Observation(
            None,
            unsafe=True,
            path_unsafe=True,
            parent_topology_safe=False,
            parent_missing=parent.missing,
        )
    is_regular = stat.S_ISREG(info.st_mode)
    return _Observation(
        True,
        unsafe=not is_regular,
        is_directory=stat.S_ISDIR(info.st_mode),
        is_symlink=stat.S_ISLNK(info.st_mode),
        unsupported_file_type=not is_regular,
        parent_topology_safe=True,
        parent_missing=parent.missing,
    )


def _with_containment(
    observation: _Observation, path: Path, root: Path
) -> _Observation:
    containment_safe = _containment_safe(path, root)
    if containment_safe is False:
        return replace(
            observation,
            exists=None,
            unsafe=True,
            path_unsafe=True,
            containment_safe=False,
        )
    return replace(observation, containment_safe=containment_safe)


@dataclass(frozen=True, slots=True)
class _ParentTopology:
    unsafe: bool = False
    observation_failed: bool = False
    missing: bool = False


def _observe_parent_topology(path: Path) -> _ParentTopology:
    current = path.parent
    missing = False
    while current != current.parent:
        try:
            info = current.lstat()
        except FileNotFoundError:
            missing = True
            current = current.parent
            continue
        except OSError:
            return _ParentTopology(observation_failed=True, missing=missing)
        except ValueError:
            return _ParentTopology(unsafe=True, missing=missing)
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            return _ParentTopology(unsafe=True, missing=missing)
        current = current.parent
    return _ParentTopology(missing=missing)


def _containment_safe(path: Path, root: Path | None) -> bool | None:
    if root is None:
        return None
    try:
        return path != root and path.is_relative_to(root)
    except ValueError:
        return False


def _path_observation_status(observation: _Observation) -> PathObservationStatus:
    if observation.unsupported_file_type:
        return PathObservationStatus.UNSUPPORTED_FILE_TYPE
    if observation.path_unsafe:
        return PathObservationStatus.UNSAFE_PATH
    if observation.observation_failed:
        return PathObservationStatus.OBSERVATION_FAILED
    if observation.exists is False:
        return PathObservationStatus.MISSING
    if observation.exists is True:
        return PathObservationStatus.REGULAR_FILE
    return PathObservationStatus.NOT_OBSERVED


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
