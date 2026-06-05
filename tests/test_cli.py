from pathlib import Path

import pytest

from smart_file_organizer.cli import (
    format_destination_conflicts,
    format_planned_move,
    main,
)
from smart_file_organizer.core import FileCategory, PlannedMove


def test_format_planned_move() -> None:
    move = PlannedMove(
        source=Path("photo.jpg"),
        destination=Path("organized/images/photo.jpg"),
        category=FileCategory.IMAGES,
    )

    assert format_planned_move(move) == "photo.jpg -> organized/images/photo.jpg"


def test_format_destination_conflicts() -> None:
    destination = Path("organized/images/photo.jpg")
    conflicts = {
        destination: [
            PlannedMove(
                source=Path("folder-a/photo.jpg"),
                destination=destination,
                category=FileCategory.IMAGES,
            ),
            PlannedMove(
                source=Path("folder-b/photo.jpg"),
                destination=destination,
                category=FileCategory.IMAGES,
            ),
        ],
    }

    assert format_destination_conflicts(conflicts) == (
        "destination conflicts detected:\n"
        "- organized/images/photo.jpg: folder-a/photo.jpg, folder-b/photo.jpg"
    )


def test_main_prints_organization_plan_from_explicit_sources(capsys) -> None:
    main(
        [
            "--target",
            "organized",
            "photo.jpg",
            "notes.txt",
            "script.py",
        ]
    )

    captured = capsys.readouterr()

    assert captured.out == (
        "photo.jpg -> organized/images/photo.jpg\n"
        "notes.txt -> organized/documents/notes.txt\n"
        "script.py -> organized/code/script.py\n"
    )


def test_main_prints_organization_plan_from_directory(
    tmp_path: Path,
    capsys,
) -> None:
    photo = tmp_path / "photo.jpg"
    notes = tmp_path / "notes.txt"
    nested_dir = tmp_path / "nested"

    photo.write_text("fake image")
    notes.write_text("hello")
    nested_dir.mkdir()
    (nested_dir / "ignored.txt").write_text("ignore me")

    main(
        [
            "--from",
            str(tmp_path),
            "--target",
            "organized",
        ]
    )

    captured = capsys.readouterr()

    assert captured.out == (
        f"{notes} -> organized/documents/notes.txt\n"
        f"{photo} -> organized/images/photo.jpg\n"
    )


def test_main_dry_run_does_not_move_files(
    tmp_path: Path,
    capsys,
) -> None:
    source_root = tmp_path / "source"
    target_root = tmp_path / "organized"
    source_root.mkdir()

    photo = source_root / "photo.jpg"
    photo.write_text("fake image")

    main(
        [
            "--from",
            str(source_root),
            "--target",
            str(target_root),
        ]
    )

    captured = capsys.readouterr()

    assert captured.out == f"{photo} -> {target_root}/images/photo.jpg\n"
    assert photo.read_text() == "fake image"
    assert not (target_root / "images" / "photo.jpg").exists()


def test_main_rejects_directory_and_explicit_sources(capsys) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--from", "downloads", "photo.jpg"])

    captured = capsys.readouterr()

    assert exc_info.value.code == 2
    assert "pass either --from or source files, not both" in captured.err


def test_main_rejects_missing_sources(capsys) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main([])

    captured = capsys.readouterr()

    assert exc_info.value.code == 2
    assert "pass at least one source file or use --from" in captured.err


def test_main_rejects_missing_source_directory(capsys) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--from", "does-not-exist"])

    captured = capsys.readouterr()

    assert exc_info.value.code == 2
    assert "source directory does not exist: does-not-exist" in captured.err


def test_main_rejects_source_path_that_is_not_directory(
    tmp_path: Path,
    capsys,
) -> None:
    source_file = tmp_path / "photo.jpg"
    source_file.write_text("fake image")

    with pytest.raises(SystemExit) as exc_info:
        main(["--from", str(source_file)])

    captured = capsys.readouterr()

    assert exc_info.value.code == 2
    assert f"source path is not a directory: {source_file}" in captured.err


def test_main_rejects_destination_conflicts(capsys) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["folder-a/photo.jpg", "folder-b/photo.jpg"])

    captured = capsys.readouterr()

    assert exc_info.value.code == 2
    assert "destination conflicts detected:" in captured.err
    assert "organized/images/photo.jpg" in captured.err
    assert "folder-a/photo.jpg" in captured.err
    assert "folder-b/photo.jpg" in captured.err


def test_main_applies_organization_plan(
    tmp_path: Path,
    capsys,
) -> None:
    source_root = tmp_path / "source"
    target_root = tmp_path / "organized"
    source_root.mkdir()

    photo = source_root / "photo.jpg"
    notes = source_root / "notes.txt"

    photo.write_text("fake image")
    notes.write_text("hello")

    main(
        [
            "--from",
            str(source_root),
            "--target",
            str(target_root),
            "--apply",
        ]
    )

    captured = capsys.readouterr()

    assert captured.out == ""
    assert not photo.exists()
    assert not notes.exists()
    assert (target_root / "images" / "photo.jpg").read_text() == "fake image"
    assert (target_root / "documents" / "notes.txt").read_text() == "hello"


def test_main_apply_reports_execution_errors(
    tmp_path: Path,
    capsys,
) -> None:
    source_root = tmp_path / "source"
    target_root = tmp_path / "organized"
    source_root.mkdir()

    source = source_root / "photo.jpg"
    destination = target_root / "images" / "photo.jpg"

    source.write_text("new image")
    destination.parent.mkdir(parents=True)
    destination.write_text("existing image")

    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "--from",
                str(source_root),
                "--target",
                str(target_root),
                "--apply",
            ]
        )

    captured = capsys.readouterr()

    assert exc_info.value.code == 2
    assert f"destination already exists: {destination}" in captured.err
    assert source.read_text() == "new image"
    assert destination.read_text() == "existing image"
