"""Internal recovery-safety classification from verified manifest evidence."""

from collections import Counter
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from smart_file_organizer.manifest_models import (
    CurrentPathObservation,
    IdentityVerificationReason,
    IdentityVerificationState,
    ManifestVerification,
    MoveReconciliation,
    PathObservationStatus,
    ReconciliationState,
)
from smart_file_organizer.models import MoveStatus


class RecoverySafetyState(StrEnum):
    """Whether current evidence can support proposing safe recovery."""

    SAFE_TO_RECOVER = "safe_to_recover"
    REFUSED = "refused"


class RecoverySafetyReason(StrEnum):
    """Stable primary reason for one recovery-safety decision."""

    RECOVERY_PRECONDITIONS_VERIFIED = "recovery_preconditions_verified"
    IDENTITY_UNVERIFIABLE = "identity_unverifiable"
    HISTORICAL_STATE_AMBIGUOUS = "historical_state_ambiguous"
    SOURCE_CONFLICT = "source_conflict"
    DESTINATION_MISSING = "destination_missing"
    BOTH_PATHS_PRESENT = "both_paths_present"
    BOTH_PATHS_MISSING = "both_paths_missing"
    DESTINATION_CHANGED = "destination_changed"
    UNSAFE_PATH = "unsafe_path"
    UNSUPPORTED_FILE_TYPE = "unsupported_file_type"
    OBSERVATION_FAILED = "observation_failed"


@dataclass(frozen=True, slots=True)
class RecoverySafetyDecision:
    """Internal per-move recovery-safety classification."""

    reconciliation: MoveReconciliation
    state: RecoverySafetyState
    reason: RecoverySafetyReason
    explanation: str


@dataclass(frozen=True, slots=True)
class RecoverySafetyClassification:
    """Internal recovery-safety decisions for one manifest verification."""

    verification: ManifestVerification
    decisions: tuple[RecoverySafetyDecision, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "decisions", tuple(self.decisions))


def classify_recovery_safety(
    verification: ManifestVerification,
) -> RecoverySafetyClassification:
    """Classify recovery safety without observing or mutating the filesystem."""
    conflicts = _conflicting_manifest_paths(verification)
    decisions = tuple(
        _classify_move(verification, reconciliation, conflicts)
        for reconciliation in verification.moves
    )
    return RecoverySafetyClassification(verification, decisions)


def _classify_move(
    verification: ManifestVerification,
    reconciliation: MoveReconciliation,
    conflicts: frozenset[Path],
) -> RecoverySafetyDecision:
    reason = _primary_reason(verification, reconciliation, conflicts)
    if reason is RecoverySafetyReason.RECOVERY_PRECONDITIONS_VERIFIED:
        return RecoverySafetyDecision(
            reconciliation,
            RecoverySafetyState.SAFE_TO_RECOVER,
            reason,
            "recovery preconditions are verified by historical evidence and current observations",
        )
    return RecoverySafetyDecision(
        reconciliation,
        RecoverySafetyState.REFUSED,
        reason,
        _explanation(reason),
    )


def _primary_reason(
    verification: ManifestVerification,
    reconciliation: MoveReconciliation,
    conflicts: frozenset[Path],
) -> RecoverySafetyReason:
    move = reconciliation.move
    if move.status is not MoveStatus.COMPLETED:
        return RecoverySafetyReason.HISTORICAL_STATE_AMBIGUOUS
    if verification.manifest.schema_version != 2 or move.identity is None:
        return RecoverySafetyReason.IDENTITY_UNVERIFIABLE
    if move.original_path in conflicts or move.final_path in conflicts:
        return RecoverySafetyReason.HISTORICAL_STATE_AMBIGUOUS

    observation_reason = _observation_refusal(reconciliation)
    if observation_reason is not None:
        return observation_reason

    state_reason = _reconciliation_refusal(reconciliation)
    if state_reason is not None:
        return state_reason

    identity_reason = _identity_refusal(reconciliation)
    if identity_reason is not None:
        return identity_reason

    if not _required_safety_demonstrated(reconciliation):
        return _missing_safety_reason(reconciliation)
    return RecoverySafetyReason.RECOVERY_PRECONDITIONS_VERIFIED


def _conflicting_manifest_paths(verification: ManifestVerification) -> frozenset[Path]:
    paths = [
        path
        for reconciliation in verification.moves
        for path in (
            reconciliation.move.original_path,
            reconciliation.move.final_path,
        )
    ]
    counts = Counter(paths)
    return frozenset(path for path, count in counts.items() if count > 1)


def _observation_refusal(
    reconciliation: MoveReconciliation,
) -> RecoverySafetyReason | None:
    observations = (
        reconciliation.source_observation,
        reconciliation.destination_observation,
    )
    if any(
        observation.status is PathObservationStatus.UNSUPPORTED_FILE_TYPE
        for observation in observations
    ):
        return RecoverySafetyReason.UNSUPPORTED_FILE_TYPE
    if any(
        observation.status is PathObservationStatus.UNSAFE_PATH
        for observation in observations
    ):
        return RecoverySafetyReason.UNSAFE_PATH
    if any(
        observation.status is PathObservationStatus.OBSERVATION_FAILED
        for observation in observations
    ):
        return RecoverySafetyReason.OBSERVATION_FAILED
    return None


def _reconciliation_refusal(
    reconciliation: MoveReconciliation,
) -> RecoverySafetyReason | None:
    if reconciliation.state is ReconciliationState.BOTH_PRESENT:
        return RecoverySafetyReason.BOTH_PATHS_PRESENT
    if reconciliation.state is ReconciliationState.BOTH_MISSING:
        return RecoverySafetyReason.BOTH_PATHS_MISSING
    if reconciliation.source_exists is True:
        return RecoverySafetyReason.SOURCE_CONFLICT
    if reconciliation.destination_exists is False:
        return RecoverySafetyReason.DESTINATION_MISSING
    if reconciliation.state is ReconciliationState.UNSAFE_PATH:
        return RecoverySafetyReason.UNSAFE_PATH
    if reconciliation.state is not ReconciliationState.CONSISTENT:
        return RecoverySafetyReason.HISTORICAL_STATE_AMBIGUOUS
    return None


def _identity_refusal(
    reconciliation: MoveReconciliation,
) -> RecoverySafetyReason | None:
    identity = reconciliation.identity
    if identity.state is IdentityVerificationState.IDENTITY_MATCH:
        return None
    if identity.state is IdentityVerificationState.IDENTITY_MISMATCH:
        return RecoverySafetyReason.DESTINATION_CHANGED
    if identity.reason is IdentityVerificationReason.DESTINATION_MISSING:
        return RecoverySafetyReason.DESTINATION_MISSING
    if identity.reason is IdentityVerificationReason.UNSAFE_PATH:
        return RecoverySafetyReason.UNSAFE_PATH
    if identity.reason is IdentityVerificationReason.UNSUPPORTED_FILE_TYPE:
        return RecoverySafetyReason.UNSUPPORTED_FILE_TYPE
    if identity.reason is IdentityVerificationReason.OBSERVATION_FAILED:
        return RecoverySafetyReason.OBSERVATION_FAILED
    return RecoverySafetyReason.IDENTITY_UNVERIFIABLE


def _required_safety_demonstrated(reconciliation: MoveReconciliation) -> bool:
    source = reconciliation.source_observation
    destination = reconciliation.destination_observation
    return (
        _source_restoration_path_available(source)
        and _destination_recovery_source_available(destination)
        and reconciliation.source_exists is False
        and reconciliation.destination_exists is True
    )


def _missing_safety_reason(
    reconciliation: MoveReconciliation,
) -> RecoverySafetyReason:
    observations = (
        reconciliation.source_observation,
        reconciliation.destination_observation,
    )
    if (
        any(
            observation.status is PathObservationStatus.OBSERVATION_FAILED
            or observation.leaf_exists is None
            or observation.parent_topology_safe is None
            for observation in observations
        )
        or reconciliation.destination_observation.containment_safe is None
    ):
        return RecoverySafetyReason.OBSERVATION_FAILED
    if any(
        observation.status is PathObservationStatus.UNSAFE_PATH
        or observation.containment_safe is False
        or observation.parent_topology_safe is False
        for observation in observations
    ):
        return RecoverySafetyReason.UNSAFE_PATH
    if reconciliation.source_observation.parent_missing:
        return RecoverySafetyReason.SOURCE_CONFLICT
    return RecoverySafetyReason.HISTORICAL_STATE_AMBIGUOUS


def _source_restoration_path_available(observation: CurrentPathObservation) -> bool:
    return (
        observation.status is PathObservationStatus.MISSING
        and observation.leaf_exists is False
        and observation.parent_missing is False
        and observation.parent_topology_safe is True
        and observation.containment_safe is not False
    )


def _destination_recovery_source_available(
    observation: CurrentPathObservation,
) -> bool:
    return (
        observation.status is PathObservationStatus.REGULAR_FILE
        and observation.leaf_exists is True
        and observation.parent_topology_safe is True
        and observation.containment_safe is True
    )


def _explanation(reason: RecoverySafetyReason) -> str:
    return {
        RecoverySafetyReason.IDENTITY_UNVERIFIABLE: "historical identity evidence is insufficient for safe recovery",
        RecoverySafetyReason.HISTORICAL_STATE_AMBIGUOUS: "historical or reconciled state is ambiguous for safe recovery",
        RecoverySafetyReason.SOURCE_CONFLICT: "original location is occupied",
        RecoverySafetyReason.DESTINATION_MISSING: "current recovery source is missing",
        RecoverySafetyReason.BOTH_PATHS_PRESENT: "original and final paths are both present",
        RecoverySafetyReason.BOTH_PATHS_MISSING: "original and final paths are both missing",
        RecoverySafetyReason.DESTINATION_CHANGED: "current recovery source does not match recorded identity evidence",
        RecoverySafetyReason.UNSAFE_PATH: "a required path has unsafe topology or containment",
        RecoverySafetyReason.UNSUPPORTED_FILE_TYPE: "a required filesystem object is unsupported",
        RecoverySafetyReason.OBSERVATION_FAILED: "a required filesystem observation failed",
    }[reason]
