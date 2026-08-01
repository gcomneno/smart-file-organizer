import json
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

    assert payload["schema_version"] == 1
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
    assert [move["final_path"] for move in payload["moves"]] == [
        str((target_root / "images" / "photo.jpg").absolute()),
        str((target_root / "documents" / "inbox" / "notes.txt").absolute()),
    ]
    assert all(move["error"] is None for move in payload["moves"])


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
    assert payload["moves"][1]["error"] == {
        "message": "synthetic permission failure",
        "type": "PermissionError",
    }
    assert payload["moves"][0]["original_path"] == str(first.absolute())
    assert payload["moves"][0]["final_path"] == str(
        (target_root / "images" / "a.jpg").absolute()
    )
