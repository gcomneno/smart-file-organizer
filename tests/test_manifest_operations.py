"""Behavioral contracts for strict historical-manifest operations."""

import hashlib
import json
import os
from collections.abc import Iterable
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

import smart_file_organizer.execution as execution_module
from smart_file_organizer import cli
from smart_file_organizer.errors import ManifestFormatError, ManifestPathError
from smart_file_organizer.manifest_models import (
    IdentityObservationStatus,
    IdentityVerificationReason,
    IdentityVerificationState,
    RecoveryDisposition,
    ReconciliationState,
)
from smart_file_organizer.models import (
    FileCategory,
    MoveExecutionRecord,
    MoveStatus,
    PlannedMove,
)
from smart_file_organizer import manifest_store
from smart_file_organizer import manifest_verification as manifest_verification_module
from smart_file_organizer import payload_identity as payload_identity_module
from smart_file_organizer.manifest_verification import _Observation, _observe, _state
from smart_file_organizer.manifest_store import ManifestStore
from smart_file_organizer.manifest_verification import verify_manifest
from smart_file_organizer.manifest_output import render_verification
from smart_file_organizer.recovery_planning import plan_recovery


def _payload(target: Path, *, status: str = "completed") -> dict[str, Any]:
    timestamp = datetime.now(timezone.utc).isoformat()
    source = target.parent / "source.txt"
    destination = target / "documents" / "source.txt"
    error = (
        None if status != "failed" else {"type": "PermissionError", "message": "denied"}
    )
    state = "completed" if status == "completed" else "failed"
    counts = {"completed": 0, "failed": 0, "in_progress": 0, "unattempted": 0}
    counts[status] = 1
    return {
        "schema_version": 1,
        "state": state,
        "target_root": str(target),
        "started_at": timestamp,
        "updated_at": timestamp,
        "finished_at": timestamp,
        "counts": counts,
        "moves": [
            {
                "original_path": str(source),
                "final_path": str(destination),
                "category": "documents",
                "status": status,
                "timestamp": timestamp,
                "error": error,
            }
        ],
    }


def _payload_v2(target: Path, content: bytes) -> dict[str, Any]:
    timestamp = datetime.now(timezone.utc).isoformat()
    source = target.parent / "source.txt"
    destination = target / "documents" / "source.txt"
    return {
        "schema_version": 2,
        "state": "completed",
        "target_root": str(target),
        "started_at": timestamp,
        "updated_at": timestamp,
        "finished_at": timestamp,
        "counts": {
            "completed": 1,
            "failed": 0,
            "in_progress": 0,
            "unattempted": 0,
        },
        "moves": [
            {
                "original_path": str(source),
                "final_path": str(destination),
                "category": "documents",
                "status": "completed",
                "timestamp": timestamp,
                "error": None,
                "identity": {
                    "algorithm": "sha256",
                    "digest": hashlib.sha256(content).hexdigest(),
                    "size_bytes": len(content),
                    "source_observed_at": timestamp,
                    "destination_observed_at": timestamp,
                },
            }
        ],
    }


def _write_manifest(
    target: Path,
    payload: dict[str, Any],
    name: str = "apply-20260805T120000000000Z-0123456789ab.json",
) -> Path:
    directory = target / ".smart-file-organizer" / "manifests"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _verify_payload(target: Path, payload: dict[str, Any]):
    path = _write_manifest(target, payload)
    return verify_manifest(
        ManifestStore(schema_version=execution_module.MANIFEST_SCHEMA_VERSION).load(
            path
        )
    )


def test_load_verify_and_plan_completed_manifest(tmp_path: Path) -> None:
    target = tmp_path / "target"
    payload = _payload(target)
    source = Path(payload["moves"][0]["original_path"])
    destination = Path(payload["moves"][0]["final_path"])
    destination.parent.mkdir(parents=True)
    destination.write_text("current", encoding="utf-8")
    path = _write_manifest(target, payload)

    manifest = ManifestStore(schema_version=1).load(path)
    verification = verify_manifest(manifest)
    recovery = plan_recovery(verification)

    assert not os.path.lexists(source)
    assert verification.moves[0].state is ReconciliationState.CONSISTENT
    assert recovery.items[0].disposition is RecoveryDisposition.PROPOSED
    assert recovery.items[0].recovery_source == destination
    assert recovery.items[0].recovery_destination == source


def test_v1_completed_identity_is_unverifiable_without_current_fingerprint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    payload = _payload(target)
    destination = Path(payload["moves"][0]["final_path"])
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"current")

    def unexpected_fingerprint(path: Path):
        raise AssertionError(f"v1 verification fingerprinted {path}")

    monkeypatch.setattr(
        manifest_verification_module,
        "_fingerprint_regular_file",
        unexpected_fingerprint,
    )

    identity = _verify_payload(target, payload).moves[0].identity

    assert identity.state is IdentityVerificationState.IDENTITY_UNVERIFIABLE
    assert identity.reason is IdentityVerificationReason.HISTORICAL_IDENTITY_ABSENT
    assert identity.current.status is IdentityObservationStatus.NOT_OBSERVED


def test_v2_non_completed_identity_is_unverifiable_without_current_fingerprint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    payload = _payload_v2(target, b"current")
    payload["state"] = "failed"
    payload["counts"] = {
        "completed": 0,
        "failed": 1,
        "in_progress": 0,
        "unattempted": 0,
    }
    payload["moves"][0]["status"] = "failed"
    payload["moves"][0]["error"] = {"type": "PermissionError", "message": "denied"}
    payload["moves"][0]["identity"] = None
    destination = Path(payload["moves"][0]["final_path"])
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"current")

    def unexpected_fingerprint(path: Path):
        raise AssertionError(f"non-completed v2 verification fingerprinted {path}")

    monkeypatch.setattr(
        manifest_verification_module,
        "_fingerprint_regular_file",
        unexpected_fingerprint,
    )

    identity = _verify_payload(target, payload).moves[0].identity

    assert identity.state is IdentityVerificationState.IDENTITY_UNVERIFIABLE
    assert identity.reason is IdentityVerificationReason.HISTORICAL_IDENTITY_ABSENT
    assert identity.current.status is IdentityObservationStatus.NOT_OBSERVED


def test_v2_completed_unchanged_bytes_match(tmp_path: Path) -> None:
    content = b"current"
    target = tmp_path / "target"
    payload = _payload_v2(target, content)
    destination = Path(payload["moves"][0]["final_path"])
    destination.parent.mkdir(parents=True)
    destination.write_bytes(content)

    identity = _verify_payload(target, payload).moves[0].identity

    assert identity.state is IdentityVerificationState.IDENTITY_MATCH
    assert identity.reason is IdentityVerificationReason.IDENTITY_VERIFIED
    assert identity.current.status is IdentityObservationStatus.FINGERPRINTED
    assert identity.current.algorithm == "sha256"
    assert identity.current.digest == hashlib.sha256(content).hexdigest()
    assert identity.current.size_bytes == len(content)
    assert identity.current.observed_at is not None


def test_v2_metadata_only_changes_remain_identity_match(tmp_path: Path) -> None:
    content = b"metadata-stable"
    target = tmp_path / "target"
    payload = _payload_v2(target, content)
    destination = Path(payload["moves"][0]["final_path"])
    destination.parent.mkdir(parents=True)
    destination.write_bytes(content)
    os.utime(destination, (1, 1))
    destination.chmod(0o600)

    identity = _verify_payload(target, payload).moves[0].identity

    assert identity.state is IdentityVerificationState.IDENTITY_MATCH


def test_v2_same_size_different_bytes_are_identity_mismatch(tmp_path: Path) -> None:
    target = tmp_path / "target"
    payload = _payload_v2(target, b"abc")
    destination = Path(payload["moves"][0]["final_path"])
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"xyz")

    identity = _verify_payload(target, payload).moves[0].identity

    assert identity.state is IdentityVerificationState.IDENTITY_MISMATCH
    assert identity.reason is IdentityVerificationReason.DESTINATION_CHANGED
    assert identity.current.size_bytes == 3


def test_v2_changed_size_is_identity_mismatch(tmp_path: Path) -> None:
    target = tmp_path / "target"
    payload = _payload_v2(target, b"abc")
    destination = Path(payload["moves"][0]["final_path"])
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"abcd")

    identity = _verify_payload(target, payload).moves[0].identity

    assert identity.state is IdentityVerificationState.IDENTITY_MISMATCH
    assert identity.reason is IdentityVerificationReason.DESTINATION_CHANGED
    assert identity.current.size_bytes == 4


def test_v2_missing_final_path_is_identity_unverifiable(tmp_path: Path) -> None:
    target = tmp_path / "target"
    payload = _payload_v2(target, b"current")

    identity = _verify_payload(target, payload).moves[0].identity

    assert identity.state is IdentityVerificationState.IDENTITY_UNVERIFIABLE
    assert identity.reason is IdentityVerificationReason.DESTINATION_MISSING
    assert identity.current.status is IdentityObservationStatus.MISSING


def test_v2_final_path_symlink_is_not_dereferenced(tmp_path: Path) -> None:
    content = b"current"
    target = tmp_path / "target"
    payload = _payload_v2(target, content)
    destination = Path(payload["moves"][0]["final_path"])
    destination.parent.mkdir(parents=True)
    referent = tmp_path / "referent.txt"
    referent.write_bytes(content)
    destination.symlink_to(referent)

    verification = _verify_payload(target, payload)
    identity = verification.moves[0].identity

    assert verification.moves[0].state is ReconciliationState.UNSAFE_PATH
    assert identity.state is IdentityVerificationState.IDENTITY_UNVERIFIABLE
    assert identity.reason is IdentityVerificationReason.UNSUPPORTED_FILE_TYPE
    assert identity.current.status is IdentityObservationStatus.UNSUPPORTED_FILE_TYPE


def test_v2_directory_final_path_is_identity_unverifiable(tmp_path: Path) -> None:
    target = tmp_path / "target"
    payload = _payload_v2(target, b"current")
    destination = Path(payload["moves"][0]["final_path"])
    destination.mkdir(parents=True)

    verification = _verify_payload(target, payload)
    identity = verification.moves[0].identity

    assert verification.moves[0].state is ReconciliationState.UNSAFE_PATH
    assert identity.state is IdentityVerificationState.IDENTITY_UNVERIFIABLE
    assert identity.reason is IdentityVerificationReason.UNSUPPORTED_FILE_TYPE


def test_v2_fifo_final_path_is_identity_unverifiable(tmp_path: Path) -> None:
    target = tmp_path / "target"
    payload = _payload_v2(target, b"current")
    destination = Path(payload["moves"][0]["final_path"])
    destination.parent.mkdir(parents=True)
    os.mkfifo(destination)

    verification = _verify_payload(target, payload)
    identity = verification.moves[0].identity

    assert verification.moves[0].state is ReconciliationState.UNSAFE_PATH
    assert identity.state is IdentityVerificationState.IDENTITY_UNVERIFIABLE
    assert identity.reason is IdentityVerificationReason.UNSUPPORTED_FILE_TYPE


def test_fingerprint_refuses_fifo_replacement_before_open_without_blocking(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if not hasattr(os, "mkfifo") or not hasattr(os, "O_NONBLOCK"):
        pytest.skip("FIFO nonblocking-open regression requires POSIX O_NONBLOCK")
    path = tmp_path / "payload.txt"
    path.write_bytes(b"payload")
    original_open = payload_identity_module.os.open
    replaced = False

    def replace_regular_file_with_fifo_before_open(
        name: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal replaced
        if os.fspath(name) == os.fspath(path) and not replaced:
            replaced = True
            path.unlink()
            os.mkfifo(path)
            assert flags & os.O_NONBLOCK
        return original_open(name, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(
        payload_identity_module.os,
        "open",
        replace_regular_file_with_fifo_before_open,
    )

    with pytest.raises(OSError, match="not a regular file|changed during observation"):
        payload_identity_module._fingerprint_regular_file(path)

    assert replaced


def test_v2_identity_revalidates_parent_topology_before_fingerprinting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    content = b"current"
    target = tmp_path / "target"
    payload = _payload_v2(target, content)
    destination = Path(payload["moves"][0]["final_path"])
    destination.parent.mkdir(parents=True)
    destination.write_bytes(content)
    manifest = ManifestStore(schema_version=2).load(_write_manifest(target, payload))
    original_observe = manifest_verification_module._observe
    fingerprinted: list[Path] = []
    replaced = False

    def replace_parent_after_first_destination_observation(path: Path) -> _Observation:
        nonlocal replaced
        observation = original_observe(path)
        if path == destination and not replaced:
            replaced = True
            replacement = target / "moved-documents"
            destination.parent.rename(replacement)
            destination.parent.symlink_to(replacement, target_is_directory=True)
        return observation

    real_fingerprint = manifest_verification_module._fingerprint_regular_file

    def recording_fingerprint(path: Path):
        fingerprinted.append(path)
        return real_fingerprint(path)

    monkeypatch.setattr(
        manifest_verification_module,
        "_observe",
        replace_parent_after_first_destination_observation,
    )
    monkeypatch.setattr(
        manifest_verification_module,
        "_fingerprint_regular_file",
        recording_fingerprint,
    )

    verification = verify_manifest(manifest)
    identity = verification.moves[0].identity

    assert replaced
    assert fingerprinted == []
    assert identity.state is IdentityVerificationState.IDENTITY_UNVERIFIABLE
    assert identity.reason is IdentityVerificationReason.UNSAFE_PATH
    assert identity.current.status is IdentityObservationStatus.UNSAFE_PATH


def test_v2_fingerprint_failure_is_identity_unverifiable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    payload = _payload_v2(target, b"current")
    destination = Path(payload["moves"][0]["final_path"])
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"current")

    def fail_fingerprint(path: Path):
        raise PermissionError(f"cannot read {path}")

    monkeypatch.setattr(
        manifest_verification_module,
        "_fingerprint_regular_file",
        fail_fingerprint,
    )

    identity = _verify_payload(target, payload).moves[0].identity

    assert identity.state is IdentityVerificationState.IDENTITY_UNVERIFIABLE
    assert identity.reason is IdentityVerificationReason.OBSERVATION_FAILED
    assert identity.current.status is IdentityObservationStatus.OBSERVATION_FAILED


def test_v2_identity_verification_does_not_mutate_manifest_or_payload(
    tmp_path: Path,
) -> None:
    content = b"current"
    target = tmp_path / "target"
    payload = _payload_v2(target, content)
    destination = Path(payload["moves"][0]["final_path"])
    destination.parent.mkdir(parents=True)
    destination.write_bytes(content)
    path = _write_manifest(target, payload)
    manifest_bytes = path.read_bytes()
    payload_bytes = destination.read_bytes()

    verify_manifest(ManifestStore(schema_version=2).load(path))

    assert path.read_bytes() == manifest_bytes
    assert destination.read_bytes() == payload_bytes


def test_verification_renders_deterministic_identity_output(tmp_path: Path) -> None:
    content = b"current"
    target = tmp_path / "target"
    payload = _payload_v2(target, content)
    destination = Path(payload["moves"][0]["final_path"])
    destination.parent.mkdir(parents=True)
    destination.write_bytes(content)
    verification = _verify_payload(target, payload)

    json_output = json.loads(render_verification(verification, json_output=True))
    text_output = render_verification(verification, json_output=False)

    identity_json = json_output["moves"][0]["identity"]
    assert identity_json["state"] == "identity_match"
    assert identity_json["reason"] == "identity_verified"
    assert identity_json["current"]["status"] == "fingerprinted"
    assert identity_json["current"]["algorithm"] == "sha256"
    assert identity_json["current"]["digest"] == hashlib.sha256(content).hexdigest()
    assert identity_json["current"]["size_bytes"] == len(content)
    assert "identity=identity_match reason=identity_verified current=fingerprinted" in (
        text_output
    )


def test_existing_recovery_planning_semantics_ignore_identity_mismatch(
    tmp_path: Path,
) -> None:
    target = tmp_path / "target"
    payload = _payload_v2(target, b"old")
    destination = Path(payload["moves"][0]["final_path"])
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"new")

    verification = _verify_payload(target, payload)
    recovery = plan_recovery(verification)

    assert verification.moves[0].identity.state is (
        IdentityVerificationState.IDENTITY_MISMATCH
    )
    assert verification.moves[0].state is ReconciliationState.CONSISTENT
    assert recovery.items[0].disposition is RecoveryDisposition.PROPOSED


def test_store_loads_interrupted_zero_move_manifest_from_current_writer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    write_manifest = execution_module._write_manifest

    def interrupt_after_initial_manifest(
        manifest_path: Path,
        *,
        target_root: Path,
        started_at: datetime,
        finished_at: datetime | None,
        records: Iterable[MoveExecutionRecord],
    ) -> None:
        write_manifest(
            manifest_path,
            target_root=target_root,
            started_at=started_at,
            finished_at=finished_at,
            records=records,
        )
        raise KeyboardInterrupt

    monkeypatch.setattr(
        execution_module, "_write_manifest", interrupt_after_initial_manifest
    )

    with pytest.raises(KeyboardInterrupt):
        execution_module.execute_plan((), target)

    path = next((target / ".smart-file-organizer" / "manifests").iterdir())
    manifest = ManifestStore(
        schema_version=execution_module.MANIFEST_SCHEMA_VERSION
    ).load(path)

    assert manifest.state == "running"
    assert manifest.finished_at is None
    assert manifest.counts.total == 0
    assert manifest.moves == ()


def test_store_loads_and_lists_manifest_written_through_target_root_symlink(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.txt"
    source.write_text("source", encoding="utf-8")
    physical_target = tmp_path / "physical-target"
    physical_target.mkdir()
    target = tmp_path / "target-link"
    target.symlink_to(physical_target, target_is_directory=True)
    plan = (
        PlannedMove(
            source=source,
            destination=target / "documents" / "source.txt",
            category=FileCategory.DOCUMENTS,
        ),
    )

    result = execution_module.execute_plan(plan, target)
    store = ManifestStore(schema_version=execution_module.MANIFEST_SCHEMA_VERSION)

    manifest = store.load(result.manifest_path)
    references = store.list_for_target(target)

    assert manifest.target_root == target.absolute()
    assert [reference.path for reference in references] == [result.manifest_path]
    assert references[0].manifest == manifest


@pytest.mark.parametrize("kind", ("broken", "looping"))
def test_store_reports_unresolvable_target_root_aliases_as_controlled_errors(
    tmp_path: Path, kind: str
) -> None:
    target = tmp_path / "target-link"
    if kind == "broken":
        target.symlink_to(tmp_path / "missing-target", target_is_directory=True)
    else:
        target.symlink_to(target, target_is_directory=True)

    with pytest.raises(ManifestPathError, match="target root"):
        ManifestStore(schema_version=1).list_for_target(target)


def test_store_rejects_alias_store_manifest_with_mismatched_lexical_target(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.txt"
    source.write_text("source", encoding="utf-8")
    physical_target = tmp_path / "physical-target"
    physical_target.mkdir()
    target = tmp_path / "target-link"
    target.symlink_to(physical_target, target_is_directory=True)
    result = execution_module.execute_plan(
        (
            PlannedMove(
                source,
                target / "documents" / source.name,
                FileCategory.DOCUMENTS,
            ),
        ),
        target,
    )
    payload = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    payload["target_root"] = str(physical_target.absolute())
    payload["moves"][0]["final_path"] = str(physical_target / "documents" / source.name)
    result.manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ManifestPathError, match="declared target root"):
        ManifestStore(schema_version=execution_module.MANIFEST_SCHEMA_VERSION).load(
            result.manifest_path
        )


def test_store_loads_interrupted_multi_move_writer_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    first.write_text("first", encoding="utf-8")
    second.write_text("second", encoding="utf-8")
    plan = (
        PlannedMove(first, target / "documents" / first.name, FileCategory.DOCUMENTS),
        PlannedMove(second, target / "documents" / second.name, FileCategory.DOCUMENTS),
    )
    write_manifest = execution_module._write_manifest
    writes = 0

    def interrupt_after_first_completed_manifest(
        manifest_path: Path,
        *,
        target_root: Path,
        started_at: datetime,
        finished_at: datetime | None,
        records: Iterable[MoveExecutionRecord],
    ) -> None:
        nonlocal writes
        writes += 1
        write_manifest(
            manifest_path,
            target_root=target_root,
            started_at=started_at,
            finished_at=finished_at,
            records=records,
        )
        if writes == 3:
            raise KeyboardInterrupt

    monkeypatch.setattr(
        execution_module, "_write_manifest", interrupt_after_first_completed_manifest
    )

    with pytest.raises(KeyboardInterrupt):
        execution_module.execute_plan(plan, target)

    path = next((target / ".smart-file-organizer" / "manifests").iterdir())
    manifest = ManifestStore(
        schema_version=execution_module.MANIFEST_SCHEMA_VERSION
    ).load(path)

    assert manifest.state == "running"
    assert [move.status for move in manifest.moves] == [
        MoveStatus.COMPLETED,
        MoveStatus.UNATTEMPTED,
    ]


def test_v1_limited_store_rejects_current_v2_writer_manifest(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.txt"
    source.write_text("source", encoding="utf-8")
    target = tmp_path / "target"
    plan = (
        PlannedMove(
            source,
            target / "documents" / source.name,
            FileCategory.DOCUMENTS,
        ),
    )

    result = execution_module.execute_plan(plan, target)

    with pytest.raises(
        ManifestFormatError,
        match="schema version is unsupported",
    ):
        ManifestStore(schema_version=1).load(result.manifest_path)


@pytest.mark.parametrize("suffix", ("/.", "//"))
def test_store_rejects_raw_noncanonical_manifest_paths(
    tmp_path: Path, suffix: str
) -> None:
    target = tmp_path / "target"
    payload = _payload(target)
    payload["target_root"] = f"{target}{suffix}"
    path = _write_manifest(target, payload)

    with pytest.raises(ManifestFormatError, match="target root is unsafe"):
        ManifestStore(schema_version=1).load(path)


def test_store_rejects_duplicate_keys_and_boolean_counts(tmp_path: Path) -> None:
    target = tmp_path / "target"
    path = _write_manifest(target, _payload(target))
    path.write_text('{"schema_version": 1, "schema_version": 1}', encoding="utf-8")
    with pytest.raises(ManifestFormatError, match="malformed"):
        ManifestStore(schema_version=1).load(path)

    payload = _payload(target)
    payload["counts"]["completed"] = True
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ManifestFormatError, match="count completed"):
        ManifestStore(schema_version=1).load(path)


@pytest.mark.parametrize("field", ("target_root", "original_path", "final_path"))
def test_store_rejects_embedded_nul_paths_during_schema_validation(
    tmp_path: Path, field: str
) -> None:
    target = tmp_path / "target"
    payload = _payload(target)
    if field == "target_root":
        payload[field] = f"{target}\x00"
    else:
        payload["moves"][0][field] = f"{payload['moves'][0][field]}\x00"
    path = _write_manifest(target, payload)

    with pytest.raises(ManifestFormatError, match="is invalid"):
        ManifestStore(schema_version=1).load(path)


def test_listing_reports_matching_nul_path_manifest_as_invalid(tmp_path: Path) -> None:
    target = tmp_path / "target"
    payload = _payload(target)
    payload["moves"][0]["final_path"] = f"{payload['moves'][0]['final_path']}\x00"
    path = _write_manifest(target, payload)

    references = ManifestStore(schema_version=1).list_for_target(target)

    assert references[0].path == path
    assert references[0].status.value == "invalid"
    assert references[0].error_code == "invalid_manifest"


@pytest.mark.parametrize("state", ([], {}, True, 1))
def test_store_rejects_non_string_execution_state(
    tmp_path: Path, state: object
) -> None:
    target = tmp_path / "target"
    payload = _payload(target)
    payload["state"] = state
    path = _write_manifest(target, payload)

    with pytest.raises(ManifestFormatError, match="execution state"):
        ManifestStore(schema_version=1).load(path)


def test_store_rejects_unknown_fields_and_moves_after_terminal_finish(
    tmp_path: Path,
) -> None:
    target = tmp_path / "target"
    payload = _payload(target)
    payload["unknown"] = None
    path = _write_manifest(target, payload)

    with pytest.raises(ManifestFormatError, match="top-level"):
        ManifestStore(schema_version=1).load(path)

    payload = _payload(target)
    payload["started_at"] = "2026-08-05T11:00:00+00:00"
    payload["finished_at"] = "2026-08-05T12:00:00+00:00"
    payload["updated_at"] = "2026-08-05T13:00:00+00:00"
    payload["moves"][0]["timestamp"] = "2026-08-05T12:30:00+00:00"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ManifestFormatError, match="move timestamp"):
        ManifestStore(schema_version=1).load(path)


@pytest.mark.parametrize(
    ("status", "nested_field", "message"),
    (
        ("completed", "counts", "counts fields"),
        ("completed", "move", "move fields"),
        ("failed", "error", "move error fields"),
    ),
)
def test_store_rejects_unknown_nested_fields(
    tmp_path: Path, status: str, nested_field: str, message: str
) -> None:
    target = tmp_path / "target"
    payload = _payload(target, status=status)
    if nested_field == "counts":
        payload["counts"]["unknown"] = 0
    elif nested_field == "move":
        payload["moves"][0]["unknown"] = None
    else:
        payload["moves"][0]["error"]["unknown"] = None
    path = _write_manifest(target, payload)

    with pytest.raises(ManifestFormatError, match=message):
        ManifestStore(schema_version=1).load(path)


def test_store_rejects_naive_timestamps_and_count_status_contradictions(
    tmp_path: Path,
) -> None:
    target = tmp_path / "target"
    payload = _payload(target)
    payload["started_at"] = "2026-08-05T12:00:00"
    path = _write_manifest(target, payload)

    with pytest.raises(ManifestFormatError, match="started timestamp"):
        ManifestStore(schema_version=1).load(path)

    payload = _payload(target)
    payload["counts"] = {
        "completed": 0,
        "failed": 0,
        "in_progress": 0,
        "unattempted": 1,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ManifestFormatError, match="counts do not match"):
        ManifestStore(schema_version=1).load(path)


def test_listing_is_deterministic_and_reports_invalid_candidates(
    tmp_path: Path,
) -> None:
    target = tmp_path / "target"
    first = _write_manifest(
        target, _payload(target), "apply-20260805T120000000000Z-0123456789ab.json"
    )
    second = _write_manifest(
        target, _payload(target), "apply-20260805T120001000000Z-0123456789ac.json"
    )
    second.write_text("not json", encoding="utf-8")
    (first.parent / "ordinary.json").write_text("ignored", encoding="utf-8")

    references = ManifestStore(schema_version=1).list_for_target(target)

    assert [reference.path.name for reference in references] == [
        first.name,
        second.name,
    ]
    assert references[0].manifest is not None
    assert references[1].error_code == "invalid_manifest"


def test_recovery_refuses_ambiguous_or_restored_files(tmp_path: Path) -> None:
    target = tmp_path / "target"
    payload = _payload(target)
    move = payload["moves"][0]
    source = Path(move["original_path"])
    destination = Path(move["final_path"])
    source.write_text("restored", encoding="utf-8")
    destination.parent.mkdir(parents=True)
    destination.write_text("copy", encoding="utf-8")
    path = _write_manifest(target, payload)

    plan = plan_recovery(verify_manifest(ManifestStore(schema_version=1).load(path)))

    assert plan.items[0].disposition is RecoveryDisposition.REFUSED
    assert plan.items[0].reconciliation.state is ReconciliationState.BOTH_PRESENT


def test_recovery_marks_parent_symlink_created_after_verification_as_unsafe(
    tmp_path: Path,
) -> None:
    target = tmp_path / "target"
    source_parent = tmp_path / "source-parent"
    source_parent.mkdir()
    payload = _payload(target)
    payload["moves"][0]["original_path"] = str(source_parent / "source.txt")
    destination = Path(payload["moves"][0]["final_path"])
    destination.parent.mkdir(parents=True)
    destination.write_text("current", encoding="utf-8")
    path = _write_manifest(target, payload)

    verification = verify_manifest(ManifestStore(schema_version=1).load(path))
    moved_parent = tmp_path / "moved-source-parent"
    source_parent.rename(moved_parent)
    source_parent.symlink_to(moved_parent, target_is_directory=True)

    recovery = plan_recovery(verification)

    assert recovery.items[0].disposition is RecoveryDisposition.UNSAFE
    assert recovery.items[0].reason == "recovery destination parent is unsafe"


def test_recovery_rechecks_source_parent_after_verification(
    tmp_path: Path,
) -> None:
    target = tmp_path / "target"
    payload = _payload(target)
    destination = Path(payload["moves"][0]["final_path"])
    destination.parent.mkdir(parents=True)
    destination.write_text("current", encoding="utf-8")
    path = _write_manifest(target, payload)

    verification = verify_manifest(ManifestStore(schema_version=1).load(path))
    moved_parent = target / "moved-documents"
    destination.parent.rename(moved_parent)
    destination.parent.symlink_to(moved_parent, target_is_directory=True)

    recovery = plan_recovery(verification)

    assert recovery.items[0].disposition is RecoveryDisposition.UNSAFE
    assert recovery.items[0].reason == "recovery source parent is unsafe"


def test_recovery_rejects_special_files_replacing_completed_destination(
    tmp_path: Path,
) -> None:
    target = tmp_path / "target"
    payload = _payload(target)
    destination = Path(payload["moves"][0]["final_path"])
    destination.parent.mkdir(parents=True)
    destination.write_text("current", encoding="utf-8")
    path = _write_manifest(target, payload)

    verification = verify_manifest(ManifestStore(schema_version=1).load(path))
    destination.unlink()
    os.mkfifo(destination)

    recovery = plan_recovery(verification)

    assert recovery.items[0].disposition is RecoveryDisposition.UNSAFE
    assert recovery.items[0].reason == "recovery source has an unsafe file type"


def test_verification_marks_special_files_as_unsafe(tmp_path: Path) -> None:
    target = tmp_path / "target"
    payload = _payload(target)
    destination = Path(payload["moves"][0]["final_path"])
    destination.parent.mkdir(parents=True)
    os.mkfifo(destination)
    path = _write_manifest(target, payload)

    verification = verify_manifest(ManifestStore(schema_version=1).load(path))

    assert verification.moves[0].state is ReconciliationState.UNSAFE_PATH


def test_store_rejects_manifest_file_symlinks(tmp_path: Path) -> None:
    target = tmp_path / "target"
    path = _write_manifest(target, _payload(target))
    link = path.with_name("apply-20260805T120001000000Z-0123456789ac.json")
    link.symlink_to(path)
    with pytest.raises(ManifestPathError, match="symlinks"):
        ManifestStore(schema_version=1).load(link)


def test_store_rejects_metadata_directory_symlinks(tmp_path: Path) -> None:
    target = tmp_path / "target"
    path = _write_manifest(target, _payload(target))
    metadata = path.parent.parent
    replacement = target / "replacement-metadata"
    metadata.rename(replacement)
    metadata.symlink_to(replacement, target_is_directory=True)

    with pytest.raises(ManifestPathError, match="symlinks"):
        ManifestStore(schema_version=1).load(path)


def test_store_rejects_manifest_directory_symlinks(tmp_path: Path) -> None:
    target = tmp_path / "target"
    path = _write_manifest(target, _payload(target))
    directory = path.parent
    replacement = target / "replacement"
    directory.rename(replacement)
    directory.symlink_to(replacement, target_is_directory=True)

    with pytest.raises(ManifestPathError, match="symlinks"):
        ManifestStore(schema_version=1).list_for_target(target)


@pytest.mark.parametrize("entry", ("source", "destination"))
@pytest.mark.parametrize("kind", ("broken_symlink", "symlink", "directory"))
def test_verification_marks_direct_unsafe_entries(
    tmp_path: Path, entry: str, kind: str
) -> None:
    target = tmp_path / "target"
    payload = _payload(target)
    source = Path(payload["moves"][0]["original_path"])
    destination = Path(payload["moves"][0]["final_path"])
    unsafe_path = source if entry == "source" else destination
    unsafe_path.parent.mkdir(parents=True, exist_ok=True)
    if kind == "broken_symlink":
        unsafe_path.symlink_to(tmp_path / "missing-target")
    elif kind == "symlink":
        referent = tmp_path / "symlink-referent"
        referent.write_text("current", encoding="utf-8")
        unsafe_path.symlink_to(referent)
    else:
        unsafe_path.mkdir(parents=True)
    if unsafe_path != destination:
        destination.parent.mkdir(parents=True)
        destination.write_text("current", encoding="utf-8")
    path = _write_manifest(target, payload)

    verification = verify_manifest(ManifestStore(schema_version=1).load(path))

    assert verification.moves[0].state is ReconciliationState.UNSAFE_PATH
    assert (
        plan_recovery(verification).items[0].disposition is RecoveryDisposition.UNSAFE
    )


@pytest.mark.parametrize(
    ("status", "source_exists", "destination_exists", "expected"),
    (
        (MoveStatus.COMPLETED, False, True, ReconciliationState.CONSISTENT),
        (MoveStatus.COMPLETED, True, False, ReconciliationState.SOURCE_RESTORED),
        (MoveStatus.COMPLETED, True, True, ReconciliationState.BOTH_PRESENT),
        (MoveStatus.COMPLETED, False, False, ReconciliationState.BOTH_MISSING),
        (MoveStatus.FAILED, True, False, ReconciliationState.CONSISTENT),
        (MoveStatus.FAILED, False, True, ReconciliationState.UNEXPECTED_DESTINATION),
        (MoveStatus.FAILED, True, True, ReconciliationState.BOTH_PRESENT),
        (MoveStatus.FAILED, False, False, ReconciliationState.DESTINATION_MISSING),
        (MoveStatus.UNATTEMPTED, True, False, ReconciliationState.CONSISTENT),
        (
            MoveStatus.UNATTEMPTED,
            False,
            True,
            ReconciliationState.UNEXPECTED_DESTINATION,
        ),
        (MoveStatus.UNATTEMPTED, True, True, ReconciliationState.BOTH_PRESENT),
        (MoveStatus.UNATTEMPTED, False, False, ReconciliationState.BOTH_MISSING),
        (MoveStatus.IN_PROGRESS, True, False, ReconciliationState.INDETERMINATE),
        (MoveStatus.IN_PROGRESS, False, True, ReconciliationState.INDETERMINATE),
        (MoveStatus.IN_PROGRESS, True, True, ReconciliationState.INDETERMINATE),
        (MoveStatus.IN_PROGRESS, False, False, ReconciliationState.INDETERMINATE),
    ),
)
def test_reconciliation_covers_every_status_and_existence_combination(
    status: MoveStatus,
    source_exists: bool,
    destination_exists: bool,
    expected: ReconciliationState,
) -> None:
    observation_source = _Observation(source_exists)
    observation_destination = _Observation(destination_exists)

    assert _state(status, observation_source, observation_destination) is expected


def test_manifest_cli_reports_malformed_state_as_controlled_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "target"
    payload = _payload(target)
    payload["state"] = []
    path = _write_manifest(target, payload)

    with pytest.raises(SystemExit) as exc_info:
        cli.main(["manifest", "show", str(path)])

    captured = capsys.readouterr()
    assert exc_info.value.code == 2
    assert captured.out == ""
    assert "manifest execution state is invalid" in captured.err
    assert "Traceback" not in captured.err


@pytest.mark.parametrize(
    "arguments",
    (
        ("manifest", "show"),
        ("manifest", "verify"),
        ("recover", "plan"),
    ),
)
def test_manifest_cli_commands_control_nul_path_diagnostics(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    arguments: tuple[str, str],
) -> None:
    target = tmp_path / "target"
    payload = _payload(target)
    payload["moves"][0]["original_path"] = f"{payload['moves'][0]['original_path']}\x00"
    path = _write_manifest(target, payload)

    with pytest.raises(SystemExit) as exc_info:
        cli.main([*arguments, str(path)])

    captured = capsys.readouterr()
    assert exc_info.value.code == 2
    assert "manifest original path is invalid" in captured.err
    assert "Traceback" not in captured.err


def test_manifest_list_cli_reports_nul_path_candidate_as_invalid(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "target"
    payload = _payload(target)
    payload["moves"][0]["final_path"] = f"{payload['moves'][0]['final_path']}\x00"
    _write_manifest(target, payload)

    cli.main(["manifest", "list", "--target", str(target)])

    captured = capsys.readouterr()
    assert "invalid_manifest" in captured.out
    assert "Traceback" not in captured.err


def test_observation_of_manually_constructed_nul_path_is_unsafe() -> None:
    observation = _observe(Path("\x00"))

    assert observation.exists is None
    assert observation.unsafe


def test_public_model_with_nul_path_is_safe_to_verify_and_plan(tmp_path: Path) -> None:
    target = tmp_path / "target"
    manifest = ManifestStore(schema_version=1).load(
        _write_manifest(target, _payload(target))
    )
    unsafe_manifest = replace(
        manifest,
        moves=(replace(manifest.moves[0], original_path=Path("\x00")),),
    )

    verification = verify_manifest(unsafe_manifest)
    recovery = plan_recovery(verification)

    assert verification.moves[0].state is ReconciliationState.UNSAFE_PATH
    assert recovery.items[0].disposition is RecoveryDisposition.UNSAFE


def test_verification_and_recovery_planning_do_not_mutate_filesystem(
    tmp_path: Path,
) -> None:
    target = tmp_path / "target"
    payload = _payload(target)
    source = Path(payload["moves"][0]["original_path"])
    destination = Path(payload["moves"][0]["final_path"])
    destination.parent.mkdir(parents=True)
    destination.write_text("current", encoding="utf-8")
    path = _write_manifest(target, payload)
    manifest_bytes = path.read_bytes()
    destination_bytes = destination.read_bytes()

    verification = verify_manifest(ManifestStore(schema_version=1).load(path))
    plan_recovery(verification)

    assert not os.path.lexists(source)
    assert destination.read_bytes() == destination_bytes
    assert path.read_bytes() == manifest_bytes


def test_store_does_not_use_pathname_open_or_iteration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    path = _write_manifest(target, _payload(target))

    monkeypatch.setattr(
        Path, "open", lambda *_args, **_kwargs: pytest.fail("unsafe pathname open")
    )
    monkeypatch.setattr(
        Path,
        "iterdir",
        lambda *_args, **_kwargs: pytest.fail("unsafe pathname iteration"),
    )

    store = ManifestStore(schema_version=1)
    assert store.load(path).path == path
    assert store.list_for_target(target)[0].status.value == "valid"


def test_store_refuses_file_replaced_by_symlink_before_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    path = _write_manifest(target, _payload(target))
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps(_payload(target)), encoding="utf-8")
    original_open = manifest_store.os.open
    replaced = False

    def replace_before_open(
        name: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal replaced
        if name == path.name and not replaced:
            replaced = True
            path.unlink()
            path.symlink_to(outside)
        return original_open(name, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(manifest_store.os, "open", replace_before_open)

    with pytest.raises(ManifestPathError, match="symlinks"):
        ManifestStore(schema_version=1).load(path)


def test_listing_refuses_directory_replaced_by_symlink_after_enumeration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    path = _write_manifest(target, _payload(target))
    directory = path.parent
    replacement = target / "replacement"
    original_listdir = manifest_store.os.listdir
    replaced = False

    def replace_after_listing(fd: int) -> list[str]:
        nonlocal replaced
        names = original_listdir(fd)
        if not replaced:
            replaced = True
            directory.rename(replacement)
            directory.symlink_to(replacement, target_is_directory=True)
        return names

    monkeypatch.setattr(manifest_store.os, "listdir", replace_after_listing)

    references = ManifestStore(schema_version=1).list_for_target(target)

    assert references[0].status.value == "invalid"
    assert references[0].error_code == "unsafe_path"
