"""Recovery-safety classification from historical and verified evidence."""

import hashlib
import os
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from smart_file_organizer.manifest_models import (
    ApplyManifest,
    CurrentIdentityObservation,
    CurrentPathObservation,
    IdentityObservationStatus,
    IdentityVerificationReason,
    IdentityVerificationState,
    ManifestCounts,
    ManifestMove,
    ManifestVerification,
    MoveIdentityVerification,
    MoveReconciliation,
    PathObservationStatus,
    RecoveryDisposition,
    ReconciliationState,
)
from smart_file_organizer.manifest_verification import verify_manifest
from smart_file_organizer.models import FileCategory, IdentityEvidence, MoveStatus
from smart_file_organizer.recovery_planning import plan_recovery
from smart_file_organizer.recovery_planning import build_recovery_plan
from smart_file_organizer.recovery_safety import (
    RecoverySafetyClassification,
    RecoverySafetyDecision,
    RecoverySafetyReason,
    RecoverySafetyState,
    classify_recovery_safety,
)


_NOW = datetime(2026, 8, 24, tzinfo=timezone.utc)


def _identity_evidence() -> IdentityEvidence:
    return IdentityEvidence(
        algorithm="sha256",
        digest="0" * 64,
        size_bytes=7,
        source_observed_at=_NOW,
        destination_observed_at=_NOW,
    )


def _move(
    *,
    original_path: Path = Path("/source.txt"),
    final_path: Path = Path("/target/documents/source.txt"),
    status: MoveStatus = MoveStatus.COMPLETED,
    identity: IdentityEvidence | None = None,
    include_identity: bool = True,
) -> ManifestMove:
    return ManifestMove(
        original_path=original_path,
        final_path=final_path,
        category=FileCategory.DOCUMENTS,
        status=status,
        timestamp=_NOW,
        error_type="PermissionError" if status is MoveStatus.FAILED else None,
        error_message="denied" if status is MoveStatus.FAILED else None,
        identity=_identity_evidence()
        if identity is None and include_identity and status is MoveStatus.COMPLETED
        else identity,
    )


def _manifest(
    moves: tuple[ManifestMove, ...],
    *,
    schema_version: int = 2,
    target_root: Path = Path("/target"),
) -> ApplyManifest:
    counts = ManifestCounts(
        completed=sum(move.status is MoveStatus.COMPLETED for move in moves),
        failed=sum(move.status is MoveStatus.FAILED for move in moves),
        in_progress=sum(move.status is MoveStatus.IN_PROGRESS for move in moves),
        unattempted=sum(move.status is MoveStatus.UNATTEMPTED for move in moves),
    )
    return ApplyManifest(
        path=target_root / ".smart-file-organizer" / "manifests" / "apply.json",
        schema_version=schema_version,
        state="completed" if counts.failed == 0 else "failed",
        target_root=target_root,
        started_at=_NOW,
        updated_at=_NOW,
        finished_at=_NOW,
        counts=counts,
        moves=moves,
    )


def _identity(
    state: IdentityVerificationState = IdentityVerificationState.IDENTITY_MATCH,
    reason: IdentityVerificationReason = IdentityVerificationReason.IDENTITY_VERIFIED,
) -> MoveIdentityVerification:
    return MoveIdentityVerification(
        state=state,
        reason=reason,
        current=CurrentIdentityObservation(
            status=IdentityObservationStatus.FINGERPRINTED
            if state is IdentityVerificationState.IDENTITY_MATCH
            else IdentityObservationStatus.NOT_OBSERVED
        ),
    )


def _path_observation(
    *,
    path: Path,
    status: PathObservationStatus,
    leaf_exists: bool | None,
    containment_safe: bool | None,
    parent_topology_safe: bool | None = True,
    parent_missing: bool = False,
) -> CurrentPathObservation:
    return CurrentPathObservation(
        path=path,
        status=status,
        leaf_exists=leaf_exists,
        parent_topology_safe=parent_topology_safe,
        parent_missing=parent_missing,
        containment_safe=containment_safe,
    )


def _reconciliation(
    move: ManifestMove | None = None,
    *,
    state: ReconciliationState = ReconciliationState.CONSISTENT,
    source_exists: bool | None = False,
    destination_exists: bool | None = True,
    identity: MoveIdentityVerification | None = None,
    source_observation: CurrentPathObservation | None = None,
    destination_observation: CurrentPathObservation | None = None,
) -> MoveReconciliation:
    move = move or _move()
    return MoveReconciliation(
        move=move,
        state=state,
        source_exists=source_exists,
        destination_exists=destination_exists,
        identity=identity or _identity(),
        source_observation=source_observation
        or _path_observation(
            path=move.original_path,
            status=PathObservationStatus.MISSING,
            leaf_exists=False,
            containment_safe=None,
        ),
        destination_observation=destination_observation
        or _path_observation(
            path=move.final_path,
            status=PathObservationStatus.REGULAR_FILE,
            leaf_exists=True,
            containment_safe=True,
        ),
    )


def _verification(
    reconciliations: tuple[MoveReconciliation, ...],
    *,
    schema_version: int = 2,
) -> ManifestVerification:
    moves = tuple(reconciliation.move for reconciliation in reconciliations)
    return ManifestVerification(
        _manifest(moves, schema_version=schema_version),
        reconciliations,
        {state: 0 for state in ReconciliationState},
    )


def _decision(
    reconciliation: MoveReconciliation, *, schema_version: int = 2
) -> tuple[RecoverySafetyState, RecoverySafetyReason]:
    classification = classify_recovery_safety(
        _verification((reconciliation,), schema_version=schema_version)
    )
    decision = classification.decisions[0]
    return decision.state, decision.reason


def test_completed_v2_verified_consistent_move_is_safe_to_recover() -> None:
    assert _decision(_reconciliation()) == (
        RecoverySafetyState.SAFE_TO_RECOVER,
        RecoverySafetyReason.RECOVERY_PRECONDITIONS_VERIFIED,
    )


def test_manifest_v1_refuses_as_identity_unverifiable() -> None:
    move = _move(include_identity=False)
    reconciliation = _reconciliation(move)

    assert _decision(reconciliation, schema_version=1) == (
        RecoverySafetyState.REFUSED,
        RecoverySafetyReason.IDENTITY_UNVERIFIABLE,
    )


def test_non_completed_historical_move_refuses() -> None:
    move = _move(status=MoveStatus.FAILED, identity=None)

    assert _decision(_reconciliation(move)) == (
        RecoverySafetyState.REFUSED,
        RecoverySafetyReason.HISTORICAL_MOVE_NOT_COMPLETED,
    )


def test_identity_mismatch_refuses_as_destination_changed() -> None:
    reconciliation = _reconciliation(
        identity=_identity(
            IdentityVerificationState.IDENTITY_MISMATCH,
            IdentityVerificationReason.DESTINATION_CHANGED,
        )
    )

    assert _decision(reconciliation) == (
        RecoverySafetyState.REFUSED,
        RecoverySafetyReason.DESTINATION_CHANGED,
    )


def test_identity_unverifiable_refuses() -> None:
    reconciliation = _reconciliation(
        identity=_identity(
            IdentityVerificationState.IDENTITY_UNVERIFIABLE,
            IdentityVerificationReason.HISTORICAL_IDENTITY_ABSENT,
        )
    )

    assert _decision(reconciliation) == (
        RecoverySafetyState.REFUSED,
        RecoverySafetyReason.IDENTITY_UNVERIFIABLE,
    )


def test_original_location_occupied_refuses() -> None:
    reconciliation = _reconciliation(
        state=ReconciliationState.SOURCE_RESTORED,
        source_exists=True,
        destination_exists=False,
        source_observation=_path_observation(
            path=Path("/source.txt"),
            status=PathObservationStatus.REGULAR_FILE,
            leaf_exists=True,
            containment_safe=None,
        ),
        destination_observation=_path_observation(
            path=Path("/target/documents/source.txt"),
            status=PathObservationStatus.MISSING,
            leaf_exists=False,
            containment_safe=True,
        ),
    )

    assert _decision(reconciliation) == (
        RecoverySafetyState.REFUSED,
        RecoverySafetyReason.SOURCE_CONFLICT,
    )


def test_final_recovery_source_missing_refuses() -> None:
    reconciliation = _reconciliation(
        destination_exists=False,
        destination_observation=_path_observation(
            path=Path("/target/documents/source.txt"),
            status=PathObservationStatus.MISSING,
            leaf_exists=False,
            containment_safe=True,
        ),
    )

    assert _decision(reconciliation) == (
        RecoverySafetyState.REFUSED,
        RecoverySafetyReason.DESTINATION_MISSING,
    )


def test_both_paths_present_refuses() -> None:
    reconciliation = _reconciliation(
        state=ReconciliationState.BOTH_PRESENT,
        source_exists=True,
        destination_exists=True,
        source_observation=_path_observation(
            path=Path("/source.txt"),
            status=PathObservationStatus.REGULAR_FILE,
            leaf_exists=True,
            containment_safe=None,
        ),
    )

    assert _decision(reconciliation) == (
        RecoverySafetyState.REFUSED,
        RecoverySafetyReason.BOTH_PATHS_PRESENT,
    )


def test_both_paths_missing_refuses() -> None:
    reconciliation = _reconciliation(
        state=ReconciliationState.BOTH_MISSING,
        source_exists=False,
        destination_exists=False,
        destination_observation=_path_observation(
            path=Path("/target/documents/source.txt"),
            status=PathObservationStatus.MISSING,
            leaf_exists=False,
            containment_safe=True,
        ),
    )

    assert _decision(reconciliation) == (
        RecoverySafetyState.REFUSED,
        RecoverySafetyReason.BOTH_PATHS_MISSING,
    )


def test_unsafe_symlink_topology_refuses() -> None:
    reconciliation = _reconciliation(
        state=ReconciliationState.UNSAFE_PATH,
        source_exists=None,
        source_observation=_path_observation(
            path=Path("/source.txt"),
            status=PathObservationStatus.UNSAFE_PATH,
            leaf_exists=None,
            parent_topology_safe=False,
            containment_safe=None,
        ),
    )

    assert _decision(reconciliation) == (
        RecoverySafetyState.REFUSED,
        RecoverySafetyReason.UNSAFE_PATH,
    )


def test_unsupported_filesystem_object_refuses() -> None:
    reconciliation = _reconciliation(
        state=ReconciliationState.UNSAFE_PATH,
        destination_exists=True,
        destination_observation=_path_observation(
            path=Path("/target/documents/source.txt"),
            status=PathObservationStatus.UNSUPPORTED_FILE_TYPE,
            leaf_exists=True,
            containment_safe=True,
        ),
    )

    assert _decision(reconciliation) == (
        RecoverySafetyState.REFUSED,
        RecoverySafetyReason.UNSUPPORTED_FILE_TYPE,
    )


def test_parent_observation_failure_refuses() -> None:
    reconciliation = _reconciliation(
        source_exists=None,
        source_observation=_path_observation(
            path=Path("/source.txt"),
            status=PathObservationStatus.OBSERVATION_FAILED,
            leaf_exists=None,
            parent_topology_safe=None,
            containment_safe=None,
        ),
    )

    assert _decision(reconciliation) == (
        RecoverySafetyState.REFUSED,
        RecoverySafetyReason.OBSERVATION_FAILED,
    )


def test_safety_or_containment_not_demonstrated_refuses() -> None:
    reconciliation = _reconciliation(
        destination_observation=_path_observation(
            path=Path("/target/documents/source.txt"),
            status=PathObservationStatus.REGULAR_FILE,
            leaf_exists=True,
            containment_safe=None,
        ),
    )

    assert _decision(reconciliation) == (
        RecoverySafetyState.REFUSED,
        RecoverySafetyReason.SAFETY_NOT_DEMONSTRATED,
    )


def test_missing_parent_component_refuses_as_safety_not_demonstrated() -> None:
    reconciliation = _reconciliation(
        source_observation=_path_observation(
            path=Path("/missing-parent/source.txt"),
            status=PathObservationStatus.MISSING,
            leaf_exists=False,
            parent_topology_safe=True,
            parent_missing=True,
            containment_safe=None,
        )
    )

    assert reconciliation.source_observation.parent_missing is True
    assert _decision(reconciliation) == (
        RecoverySafetyState.REFUSED,
        RecoverySafetyReason.SAFETY_NOT_DEMONSTRATED,
    )


def test_duplicate_manifest_path_participation_refuses() -> None:
    move = _move()
    other = _move(
        original_path=Path("/other.txt"),
        final_path=move.final_path,
    )
    reconciliations = (_reconciliation(move), _reconciliation(other))

    classification = classify_recovery_safety(_verification(reconciliations))

    assert [decision.reason for decision in classification.decisions] == [
        RecoverySafetyReason.MANIFEST_PATH_CONFLICT,
        RecoverySafetyReason.MANIFEST_PATH_CONFLICT,
    ]


def test_reason_precedence_is_deterministic() -> None:
    move = _move(final_path=Path("/target/documents/conflict.txt"))
    other = _move(
        original_path=Path("/other.txt"),
        final_path=move.final_path,
    )
    unsafe = _reconciliation(
        move,
        state=ReconciliationState.UNSAFE_PATH,
        source_observation=_path_observation(
            path=move.original_path,
            status=PathObservationStatus.UNSAFE_PATH,
            leaf_exists=None,
            parent_topology_safe=False,
            containment_safe=None,
        ),
    )
    classification = classify_recovery_safety(
        _verification((unsafe, _reconciliation(other)))
    )

    assert classification.decisions[0].reason is (
        RecoverySafetyReason.MANIFEST_PATH_CONFLICT
    )


def test_classifier_performs_no_filesystem_access_hashing_or_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    marker = tmp_path / "marker.txt"
    marker.write_text("unchanged", encoding="utf-8")
    before = marker.read_text(encoding="utf-8")

    def forbidden(*_args: object, **_kwargs: object) -> object:
        pytest.fail("classifier attempted filesystem access or hashing")

    with monkeypatch.context() as patched:
        patched.setattr(Path, "lstat", forbidden)
        patched.setattr(Path, "open", forbidden)
        patched.setattr(Path, "write_text", forbidden)
        patched.setattr(hashlib, "sha256", forbidden)

        assert _decision(_reconciliation()) == (
            RecoverySafetyState.SAFE_TO_RECOVER,
            RecoverySafetyReason.RECOVERY_PRECONDITIONS_VERIFIED,
        )
    assert marker.read_text(encoding="utf-8") == before


def _safety_decision(
    reconciliation: MoveReconciliation,
    *,
    state: RecoverySafetyState,
    reason: RecoverySafetyReason,
) -> RecoverySafetyDecision:
    return RecoverySafetyDecision(
        reconciliation,
        state,
        reason,
        "structured safety explanation",
    )


def _classification(
    *decisions: RecoverySafetyDecision,
) -> RecoverySafetyClassification:
    verification = _verification(
        tuple(decision.reconciliation for decision in decisions)
    )
    return RecoverySafetyClassification(verification, decisions)


def test_recovery_planner_maps_safe_to_recover_to_proposed() -> None:
    reconciliation = _reconciliation()
    decision = _safety_decision(
        reconciliation,
        state=RecoverySafetyState.SAFE_TO_RECOVER,
        reason=RecoverySafetyReason.RECOVERY_PRECONDITIONS_VERIFIED,
    )

    plan = build_recovery_plan(_classification(decision))
    item = plan.items[0]

    assert item.disposition is RecoveryDisposition.PROPOSED
    assert item.recovery_source == reconciliation.move.final_path
    assert item.recovery_destination == reconciliation.move.original_path
    assert item.reason == "recovery_preconditions_verified"
    assert item.safety_decision is decision


@pytest.mark.parametrize(
    "reason",
    (
        RecoverySafetyReason.IDENTITY_UNVERIFIABLE,
        RecoverySafetyReason.DESTINATION_CHANGED,
        RecoverySafetyReason.SOURCE_CONFLICT,
        RecoverySafetyReason.DESTINATION_MISSING,
        RecoverySafetyReason.BOTH_PATHS_PRESENT,
        RecoverySafetyReason.BOTH_PATHS_MISSING,
        RecoverySafetyReason.UNSAFE_PATH,
        RecoverySafetyReason.UNSUPPORTED_FILE_TYPE,
        RecoverySafetyReason.OBSERVATION_FAILED,
        RecoverySafetyReason.MANIFEST_PATH_CONFLICT,
        RecoverySafetyReason.SAFETY_NOT_DEMONSTRATED,
    ),
)
def test_recovery_planner_maps_refused_safety_to_refused(
    reason: RecoverySafetyReason,
) -> None:
    reconciliation = _reconciliation()
    decision = _safety_decision(
        reconciliation,
        state=RecoverySafetyState.REFUSED,
        reason=reason,
    )

    item = build_recovery_plan(_classification(decision)).items[0]

    assert item.disposition is RecoveryDisposition.REFUSED
    assert item.recovery_source is None
    assert item.recovery_destination is None
    assert item.reason == reason.value
    assert item.safety_decision is decision


def test_recovery_planner_preserves_deterministic_decision_order() -> None:
    first = _safety_decision(
        _reconciliation(_move(original_path=Path("/b.txt"))),
        state=RecoverySafetyState.REFUSED,
        reason=RecoverySafetyReason.IDENTITY_UNVERIFIABLE,
    )
    second = _safety_decision(
        _reconciliation(_move(original_path=Path("/a.txt"))),
        state=RecoverySafetyState.SAFE_TO_RECOVER,
        reason=RecoverySafetyReason.RECOVERY_PRECONDITIONS_VERIFIED,
    )

    plan = build_recovery_plan(_classification(first, second))

    assert [item.move.original_path for item in plan.items] == [
        Path("/b.txt"),
        Path("/a.txt"),
    ]


def test_recovery_planner_fails_closed_for_misaligned_classification() -> None:
    first = _reconciliation(_move(original_path=Path("/first.txt")))
    second = _reconciliation(_move(original_path=Path("/second.txt")))
    verification = _verification((first,))
    classification = RecoverySafetyClassification(
        verification,
        (
            _safety_decision(
                second,
                state=RecoverySafetyState.SAFE_TO_RECOVER,
                reason=RecoverySafetyReason.RECOVERY_PRECONDITIONS_VERIFIED,
            ),
        ),
    )

    with pytest.raises(ValueError, match="malformed or misaligned"):
        build_recovery_plan(classification)


def test_recovery_planner_fails_closed_for_malformed_cardinality() -> None:
    reconciliation = _reconciliation()
    verification = _verification((reconciliation,))
    classification = RecoverySafetyClassification(verification, ())

    with pytest.raises(ValueError, match="malformed or misaligned"):
        build_recovery_plan(classification)


def test_recovery_planner_performs_no_filesystem_access_hashing_or_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    marker = tmp_path / "marker.txt"
    marker.write_text("unchanged", encoding="utf-8")
    before = marker.read_text(encoding="utf-8")
    decision = _safety_decision(
        _reconciliation(),
        state=RecoverySafetyState.SAFE_TO_RECOVER,
        reason=RecoverySafetyReason.RECOVERY_PRECONDITIONS_VERIFIED,
    )

    def forbidden(*_args: object, **_kwargs: object) -> object:
        pytest.fail("planner attempted filesystem access, hashing, or mutation")

    with monkeypatch.context() as patched:
        patched.setattr(Path, "lstat", forbidden)
        patched.setattr(Path, "stat", forbidden)
        patched.setattr(Path, "open", forbidden)
        patched.setattr(Path, "write_text", forbidden)
        patched.setattr(Path, "write_bytes", forbidden)
        patched.setattr(Path, "rename", forbidden)
        patched.setattr(Path, "replace", forbidden)
        patched.setattr(Path, "unlink", forbidden)
        patched.setattr(os.path, "lexists", forbidden)
        patched.setattr(hashlib, "sha256", forbidden)

        plan = build_recovery_plan(_classification(decision))

    assert plan.items[0].disposition is RecoveryDisposition.PROPOSED
    assert marker.read_text(encoding="utf-8") == before


def test_verify_manifest_records_recovery_path_observations(tmp_path: Path) -> None:
    content = b"current"
    target = tmp_path / "target"
    source = tmp_path / "source.txt"
    destination = target / "documents" / "source.txt"
    destination.parent.mkdir(parents=True)
    destination.write_bytes(content)
    move = _move(
        original_path=source,
        final_path=destination,
        identity=IdentityEvidence(
            algorithm="sha256",
            digest=hashlib.sha256(content).hexdigest(),
            size_bytes=len(content),
            source_observed_at=_NOW,
            destination_observed_at=_NOW,
        ),
    )
    verification = verify_manifest(_manifest((move,), target_root=target))
    reconciliation = verification.moves[0]

    assert reconciliation.source_observation.status is PathObservationStatus.MISSING
    assert reconciliation.source_observation.parent_topology_safe is True
    assert reconciliation.destination_observation.status is (
        PathObservationStatus.REGULAR_FILE
    )
    assert reconciliation.destination_observation.containment_safe is True


def test_verify_manifest_records_missing_parent_component_as_refused(
    tmp_path: Path,
) -> None:
    content = b"current"
    target = tmp_path / "target"
    source = tmp_path / "missing-parent" / "source.txt"
    destination = target / "documents" / "source.txt"
    destination.parent.mkdir(parents=True)
    destination.write_bytes(content)
    move = _move(
        original_path=source,
        final_path=destination,
        identity=IdentityEvidence(
            algorithm="sha256",
            digest=hashlib.sha256(content).hexdigest(),
            size_bytes=len(content),
            source_observed_at=_NOW,
            destination_observed_at=_NOW,
        ),
    )
    verification = verify_manifest(_manifest((move,), target_root=target))
    decision = classify_recovery_safety(verification).decisions[0]

    assert verification.moves[0].source_observation.parent_missing is True
    assert decision.state is RecoverySafetyState.REFUSED
    assert decision.reason is RecoverySafetyReason.SAFETY_NOT_DEMONSTRATED


def test_verify_manifest_records_parent_observation_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    source_parent = tmp_path / "source-parent"
    source_parent.mkdir()
    source = source_parent / "source.txt"
    destination = target / "documents" / "source.txt"
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"current")
    move = _move(original_path=source, final_path=destination)
    original_lstat = Path.lstat

    def fail_source_parent(path: Path):
        if path == source_parent:
            raise PermissionError("cannot inspect parent")
        return original_lstat(path)

    monkeypatch.setattr(Path, "lstat", fail_source_parent)

    verification = verify_manifest(_manifest((move,), target_root=target))
    decision = classify_recovery_safety(verification).decisions[0]

    assert verification.moves[0].source_observation.status is (
        PathObservationStatus.OBSERVATION_FAILED
    )
    assert decision.reason is RecoverySafetyReason.OBSERVATION_FAILED


def test_recovery_planning_refuses_identity_mismatch(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.txt"
    destination = tmp_path / "target" / "documents" / "source.txt"
    destination.parent.mkdir(parents=True)
    destination.write_text("current", encoding="utf-8")
    move = _move(original_path=source, final_path=destination)
    reconciliation = _reconciliation(
        move,
        identity=_identity(
            IdentityVerificationState.IDENTITY_MISMATCH,
            IdentityVerificationReason.DESTINATION_CHANGED,
        ),
    )
    verification = _verification((reconciliation,))
    verification = replace(verification, manifest=_manifest((move,)))

    classification = classify_recovery_safety(verification)
    recovery = plan_recovery(classification)

    assert recovery.items[0].disposition is RecoveryDisposition.REFUSED
    assert recovery.items[0].reason == "destination_changed"
    assert recovery.items[0].safety_decision is classification.decisions[0]
