"""Immutable public models for historical apply manifests."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING

from smart_file_organizer.models import FileCategory, IdentityEvidence, MoveStatus

if TYPE_CHECKING:
    from smart_file_organizer.recovery_safety import RecoverySafetyDecision


class ManifestReferenceStatus(StrEnum):
    """Whether a manifest candidate could be loaded safely."""

    VALID = "valid"
    INVALID = "invalid"


class ReconciliationState(StrEnum):
    """Current filesystem observation relative to one historical move."""

    CONSISTENT = "consistent"
    SOURCE_RESTORED = "source_restored"
    BOTH_PRESENT = "both_present"
    BOTH_MISSING = "both_missing"
    UNEXPECTED_DESTINATION = "unexpected_destination"
    DESTINATION_MISSING = "destination_missing"
    INDETERMINATE = "indeterminate"
    UNSAFE_PATH = "unsafe_path"


class IdentityVerificationState(StrEnum):
    """Byte-identity comparison result for one historical move."""

    IDENTITY_MATCH = "identity_match"
    IDENTITY_MISMATCH = "identity_mismatch"
    IDENTITY_UNVERIFIABLE = "identity_unverifiable"


class IdentityObservationStatus(StrEnum):
    """Current destination identity observation status."""

    FINGERPRINTED = "fingerprinted"
    NOT_OBSERVED = "not_observed"
    MISSING = "missing"
    UNSAFE_PATH = "unsafe_path"
    UNSUPPORTED_FILE_TYPE = "unsupported_file_type"
    OBSERVATION_FAILED = "observation_failed"


class IdentityVerificationReason(StrEnum):
    """Stable reason for one byte-identity verification result."""

    IDENTITY_VERIFIED = "identity_verified"
    DESTINATION_CHANGED = "destination_changed"
    HISTORICAL_IDENTITY_ABSENT = "historical_identity_absent"
    DESTINATION_MISSING = "destination_missing"
    UNSAFE_PATH = "unsafe_path"
    UNSUPPORTED_FILE_TYPE = "unsupported_file_type"
    OBSERVATION_FAILED = "observation_failed"


class PathObservationStatus(StrEnum):
    """Current path observation status for internal recovery-safety decisions."""

    NOT_OBSERVED = "not_observed"
    REGULAR_FILE = "regular_file"
    MISSING = "missing"
    UNSAFE_PATH = "unsafe_path"
    UNSUPPORTED_FILE_TYPE = "unsupported_file_type"
    OBSERVATION_FAILED = "observation_failed"


class RecoveryDisposition(StrEnum):
    """Read-only recovery decision for one manifest record."""

    PROPOSED = "proposed"
    ALREADY_RESTORED = "already_restored"
    NO_ACTION = "no_action"
    REFUSED = "refused"
    UNSAFE = "unsafe"


@dataclass(frozen=True, slots=True)
class ManifestCounts:
    """Durable counts recorded by a supported manifest writer."""

    completed: int
    failed: int
    in_progress: int
    unattempted: int

    def count(self, status: MoveStatus) -> int:
        """Return the count for one durable move status."""
        return getattr(self, status.value)

    @property
    def total(self) -> int:
        """Return the number of durable move records."""
        return self.completed + self.failed + self.in_progress + self.unattempted


@dataclass(frozen=True, slots=True)
class ManifestMove:
    """A validated historical move record, without raw JSON retention."""

    original_path: Path
    final_path: Path
    category: FileCategory
    status: MoveStatus
    timestamp: datetime
    error_type: str | None = None
    error_message: str | None = None
    identity: IdentityEvidence | None = None


@dataclass(frozen=True, slots=True)
class ApplyManifest:
    """Validated historical evidence from one supported apply manifest."""

    path: Path
    schema_version: int
    state: str
    target_root: Path
    started_at: datetime
    updated_at: datetime
    finished_at: datetime | None
    counts: ManifestCounts
    moves: tuple[ManifestMove, ...] = ()

    def __post_init__(self) -> None:
        """Detach the manifest from caller-owned move collections."""
        object.__setattr__(self, "moves", tuple(self.moves))


@dataclass(frozen=True, slots=True)
class ManifestReference:
    """A deterministic listing entry for either valid or invalid candidates."""

    path: Path
    status: ManifestReferenceStatus
    manifest: ApplyManifest | None = None
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class CurrentIdentityObservation:
    """Freshly observed destination payload identity, when available."""

    status: IdentityObservationStatus
    algorithm: str | None = None
    digest: str | None = None
    size_bytes: int | None = None
    observed_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class MoveIdentityVerification:
    """Current byte-identity comparison for one historical move."""

    state: IdentityVerificationState
    reason: IdentityVerificationReason
    current: CurrentIdentityObservation


@dataclass(frozen=True, slots=True)
class CurrentPathObservation:
    """Structured current path evidence captured during manifest verification."""

    path: Path | None = None
    status: PathObservationStatus = PathObservationStatus.NOT_OBSERVED
    leaf_exists: bool | None = None
    parent_topology_safe: bool | None = None
    parent_missing: bool = False
    containment_safe: bool | None = None


def _default_identity_verification() -> MoveIdentityVerification:
    return MoveIdentityVerification(
        IdentityVerificationState.IDENTITY_UNVERIFIABLE,
        IdentityVerificationReason.HISTORICAL_IDENTITY_ABSENT,
        CurrentIdentityObservation(IdentityObservationStatus.NOT_OBSERVED),
    )


@dataclass(frozen=True, slots=True)
class MoveReconciliation:
    """Current non-mutating observation for one historical move."""

    move: ManifestMove
    state: ReconciliationState
    source_exists: bool | None
    destination_exists: bool | None
    identity: MoveIdentityVerification = field(
        default_factory=_default_identity_verification
    )
    source_observation: CurrentPathObservation = field(
        default_factory=CurrentPathObservation
    )
    destination_observation: CurrentPathObservation = field(
        default_factory=CurrentPathObservation
    )


@dataclass(frozen=True, slots=True)
class ManifestVerification:
    """All current observations for one validated manifest, in record order."""

    manifest: ApplyManifest
    moves: tuple[MoveReconciliation, ...] = ()
    _summary: Mapping[ReconciliationState, int] = field(
        default_factory=dict,
        repr=False,
    )

    def __post_init__(self) -> None:
        """Detach collections and expose a read-only deterministic summary."""
        object.__setattr__(self, "moves", tuple(self.moves))
        ordered = {
            state: int(self._summary.get(state, 0)) for state in ReconciliationState
        }
        object.__setattr__(self, "_summary", MappingProxyType(ordered))

    @property
    def summary(self) -> Mapping[ReconciliationState, int]:
        """Return counts for every reconciliation state."""
        return self._summary

    def count(self, state: ReconciliationState) -> int:
        """Return the count for one reconciliation state."""
        return self._summary[state]


@dataclass(frozen=True, slots=True)
class RecoveryPlanItem:
    """One proposed reverse move or explicit refusal."""

    move: ManifestMove
    reconciliation: MoveReconciliation
    disposition: RecoveryDisposition
    recovery_source: Path | None
    recovery_destination: Path | None
    reason: str
    safety_decision: "RecoverySafetyDecision | None" = None


@dataclass(frozen=True, slots=True)
class RecoveryPlan:
    """A read-only, non-reserving manual recovery plan."""

    manifest: ApplyManifest
    verification: ManifestVerification
    items: tuple[RecoveryPlanItem, ...] = ()

    def __post_init__(self) -> None:
        """Detach the plan from caller-owned item collections."""
        object.__setattr__(self, "items", tuple(self.items))

    @property
    def proposed_count(self) -> int:
        """Return the number of safe reverse moves proposed."""
        return sum(
            item.disposition is RecoveryDisposition.PROPOSED for item in self.items
        )
