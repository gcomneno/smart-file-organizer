import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path

import pytest

import smart_file_organizer.execution as execution_module
from smart_file_organizer.core import (
    FileCategory,
    MoveStatus,
    PlannedMove,
    build_organization_plan,
    execute_plan,
)
from smart_file_organizer.errors import DestinationParentError


def test_execute_plan_returns_result_and_writes_success_manifest(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "source"
    target_root = tmp_path / "organized"
    source_root.mkdir()

    photo = source_root / "photo.jpg"
    notes = source_root / "notes.txt"
    photo.write_text("photo")
    notes.write_text("notes")

    plan = build_organization_plan([photo, notes], target_root)

    result = execute_plan(plan, target_root)

    assert result.successful
    assert result.completed_count == 2
    assert result.failed_count == 0
    assert result.unattempted_count == 0
    assert [record.status for record in result.moves] == [
        MoveStatus.COMPLETED,
        MoveStatus.COMPLETED,
    ]

    assert result.manifest_path.parent == (
        target_root.absolute() / ".smart-file-organizer" / "manifests"
    )
    assert result.manifest_path.is_file()

    payload = json.loads(result.manifest_path.read_text())

    assert payload["schema_version"] == 2
    assert payload["state"] == "completed"
    assert payload["target_root"] == str(target_root.absolute())
    assert payload["finished_at"] is not None
    assert payload["counts"] == {
        "completed": 2,
        "failed": 0,
        "in_progress": 0,
        "unattempted": 0,
    }

    assert [move["original_path"] for move in payload["moves"]] == [
        str(photo.absolute()),
        str(notes.absolute()),
    ]
    destinations = [
        target_root / "images" / "photo.jpg",
        target_root / "documents" / "inbox" / "notes.txt",
    ]
    assert [move["final_path"] for move in payload["moves"]] == [
        str(path.absolute()) for path in destinations
    ]
    assert all(move["error"] is None for move in payload["moves"])

    for move, destination in zip(payload["moves"], destinations, strict=True):
        identity = move["identity"]
        assert identity["algorithm"] == "sha256"
        expected = destination.read_bytes()
        assert identity["digest"] == hashlib.sha256(expected).hexdigest()
        assert identity["size_bytes"] == len(expected)
        source_observed_at = datetime.fromisoformat(identity["source_observed_at"])
        destination_observed_at = datetime.fromisoformat(
            identity["destination_observed_at"]
        )
        completed_at = datetime.fromisoformat(move["timestamp"])
        assert source_observed_at.tzinfo is not None
        assert destination_observed_at.tzinfo is not None
        assert source_observed_at <= destination_observed_at <= completed_at


def test_execute_plan_preflight_rejects_parent_component_that_is_file(
    tmp_path: Path,
) -> None:
    source = tmp_path / "notes.txt"
    source.write_text("notes")

    target_root = tmp_path / "organized"
    target_root.mkdir()
    blocked_parent = target_root / "documents"
    blocked_parent.write_text("not a directory")

    plan = [
        PlannedMove(
            source=source,
            destination=blocked_parent / "inbox" / "notes.txt",
            category=FileCategory.DOCUMENTS,
        )
    ]

    with pytest.raises(DestinationParentError, match="destination parent"):
        execute_plan(plan, target_root)

    assert source.read_text() == "notes"
    assert list(target_root.rglob("*.json")) == []


def test_execute_plan_records_partial_failure_and_unattempted_moves(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root = tmp_path / "source"
    target_root = tmp_path / "organized"
    source_root.mkdir()

    first = source_root / "a.jpg"
    second = source_root / "b.txt"
    third = source_root / "c.py"

    first.write_text("first")
    second.write_text("second")
    third.write_text("third")

    plan = build_organization_plan([first, second, third], target_root)

    real_move = execution_module.shutil.move
    calls = 0

    def fail_second_move(source: Path, destination: Path) -> Path | str:
        nonlocal calls
        calls += 1

        if calls == 2:
            raise PermissionError("synthetic permission failure")

        return real_move(source, destination)

    monkeypatch.setattr(execution_module.shutil, "move", fail_second_move)

    result = execute_plan(plan, target_root)

    assert not result.successful
    assert result.completed_count == 1
    assert result.failed_count == 1
    assert result.unattempted_count == 1
    assert [record.status for record in result.moves] == [
        MoveStatus.COMPLETED,
        MoveStatus.FAILED,
        MoveStatus.UNATTEMPTED,
    ]

    assert not first.exists()
    assert (target_root / "images" / "a.jpg").read_text() == "first"
    assert second.read_text() == "second"
    assert third.read_text() == "third"

    payload = json.loads(result.manifest_path.read_text())

    assert payload["state"] == "failed"
    assert payload["counts"] == {
        "completed": 1,
        "failed": 1,
        "in_progress": 0,
        "unattempted": 1,
    }
    assert [move["status"] for move in payload["moves"]] == [
        "completed",
        "failed",
        "unattempted",
    ]
    assert payload["moves"][0]["identity"] is not None
    assert payload["moves"][1]["identity"] is None
    assert payload["moves"][2]["identity"] is None
    assert payload["moves"][1]["error"] == {
        "message": "synthetic permission failure",
        "type": "PermissionError",
    }
    assert payload["moves"][0]["original_path"] == str(first.absolute())
    assert payload["moves"][0]["final_path"] == str(
        (target_root / "images" / "a.jpg").absolute()
    )


def test_planning_does_not_fingerprint_payloads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "notes.txt"
    source.write_text("notes")

    def unexpected_fingerprint(path: Path):
        raise AssertionError(f"planning fingerprinted {path}")

    monkeypatch.setattr(
        execution_module,
        "_fingerprint_regular_file",
        unexpected_fingerprint,
    )

    plan = build_organization_plan([source], tmp_path / "target")

    assert plan[0].source == source
    assert source.read_text() == "notes"


def test_same_filesystem_apply_observes_source_and_destination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "notes.txt"
    source.write_text("notes")
    target = tmp_path / "target"
    destination = target / "documents" / "notes.txt"
    plan = [PlannedMove(source, destination, FileCategory.DOCUMENTS)]

    real_fingerprint = execution_module._fingerprint_regular_file
    observed: list[Path] = []

    def recording_fingerprint(path: Path):
        observed.append(path)
        return real_fingerprint(path)

    monkeypatch.setattr(
        execution_module,
        "_fingerprint_regular_file",
        recording_fingerprint,
    )

    result = execute_plan(plan, target)

    assert result.successful
    assert observed == [source, destination]


def test_copy_delete_move_still_requires_two_sided_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"copy-delete-payload")
    target = tmp_path / "target"
    destination = target / "other" / source.name
    plan = [PlannedMove(source, destination, FileCategory.OTHER)]

    def copy_delete_move(source_path: Path, destination_path: Path) -> Path:
        shutil.copyfile(source_path, destination_path)
        source_path.unlink()
        return destination_path

    monkeypatch.setattr(execution_module.shutil, "move", copy_delete_move)

    result = execute_plan(plan, target)
    payload = json.loads(result.manifest_path.read_text())
    identity = payload["moves"][0]["identity"]

    assert result.successful
    assert identity["digest"] == hashlib.sha256(b"copy-delete-payload").hexdigest()
    assert identity["size_bytes"] == len(b"copy-delete-payload")


def test_source_fingerprint_failure_prevents_move(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.txt"
    source.write_text("source")
    target = tmp_path / "target"
    destination = target / "documents" / source.name
    plan = [PlannedMove(source, destination, FileCategory.DOCUMENTS)]
    move_called = False

    def fail_fingerprint(path: Path):
        raise PermissionError(f"cannot read {path}")

    def unexpected_move(source_path: Path, destination_path: Path):
        nonlocal move_called
        move_called = True
        raise AssertionError("move must not be attempted")

    monkeypatch.setattr(execution_module, "_fingerprint_regular_file", fail_fingerprint)
    monkeypatch.setattr(execution_module.shutil, "move", unexpected_move)

    result = execute_plan(plan, target)
    payload = json.loads(result.manifest_path.read_text())

    assert not move_called
    assert source.read_text() == "source"
    assert not destination.exists()
    assert result.failed_count == 1
    assert payload["moves"][0]["status"] == "failed"
    assert payload["moves"][0]["identity"] is None


def test_destination_fingerprint_failure_records_truthful_partial_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.txt"
    source.write_text("source")
    target = tmp_path / "target"
    destination = target / "documents" / source.name
    plan = [PlannedMove(source, destination, FileCategory.DOCUMENTS)]

    real_fingerprint = execution_module._fingerprint_regular_file
    calls = 0

    def fail_destination(path: Path):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise PermissionError("synthetic destination read failure")
        return real_fingerprint(path)

    monkeypatch.setattr(execution_module, "_fingerprint_regular_file", fail_destination)

    result = execute_plan(plan, target)
    payload = json.loads(result.manifest_path.read_text())

    assert result.failed_count == 1
    assert not source.exists()
    assert destination.read_text() == "source"
    assert payload["state"] == "failed"
    assert payload["moves"][0]["status"] == "failed"
    assert payload["moves"][0]["identity"] is None
    assert payload["moves"][0]["error"] == {
        "message": "synthetic destination read failure",
        "type": "PermissionError",
    }


def test_destination_fingerprint_mismatch_is_failed_not_warning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.txt"
    source.write_text("source")
    target = tmp_path / "target"
    destination = target / "documents" / source.name
    plan = [PlannedMove(source, destination, FileCategory.DOCUMENTS)]

    real_fingerprint = execution_module._fingerprint_regular_file
    calls = 0

    def mismatching_destination(path: Path):
        nonlocal calls
        calls += 1
        observed = real_fingerprint(path)
        if calls == 2:
            return execution_module._Fingerprint(
                digest="0" * 64,
                size_bytes=observed.size_bytes,
                observed_at=observed.observed_at,
            )
        return observed

    monkeypatch.setattr(
        execution_module,
        "_fingerprint_regular_file",
        mismatching_destination,
    )

    result = execute_plan(plan, target)
    payload = json.loads(result.manifest_path.read_text())

    assert result.failed_count == 1
    assert destination.read_text() == "source"
    assert payload["moves"][0]["status"] == "failed"
    assert payload["moves"][0]["identity"] is None
    assert payload["moves"][0]["error"]["message"] == (
        "destination fingerprint does not match source fingerprint"
    )
