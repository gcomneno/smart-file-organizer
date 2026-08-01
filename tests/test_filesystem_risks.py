import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

import smart_file_organizer.execution as execution_module
from smart_file_organizer.cli import main


def test_public_apply_records_source_disappearance_after_preflight(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source_root = tmp_path / "source"
    target_root = tmp_path / "organized"
    source_root.mkdir()

    first = source_root / "a.jpg"
    disappearing = source_root / "b.txt"
    unattempted = source_root / "c.py"

    first.write_text("first")
    disappearing.write_text("disappearing")
    unattempted.write_text("unattempted")

    real_move = execution_module.shutil.move
    calls = 0

    def disappear_before_second_move(
        source: Path,
        destination: Path,
    ) -> Path | str:
        nonlocal calls
        calls += 1

        if calls == 2:
            source.unlink()

        return real_move(source, destination)

    monkeypatch.setattr(
        execution_module.shutil,
        "move",
        disappear_before_second_move,
    )

    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "plan",
                "--apply",
                "--target",
                str(target_root),
                str(first),
                str(disappearing),
                str(unattempted),
            ]
        )

    captured = capsys.readouterr()

    assert exc_info.value.code == 1
    assert captured.out == ""
    assert "Traceback" not in captured.err

    output_lines = captured.err.splitlines()
    assert output_lines[0] == ("Apply result: completed=1 failed=1 unattempted=1")
    assert output_lines[1].startswith("Manifest: ")
    assert output_lines[2].startswith("Failed move: ")

    manifest_path = Path(output_lines[1].removeprefix("Manifest: "))
    payload = json.loads(manifest_path.read_text())

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
    assert payload["moves"][1]["error"]["type"] == ("FileNotFoundError")

    assert not first.exists()
    assert (target_root / "images" / "a.jpg").read_text() == "first"
    assert not disappearing.exists()
    assert unattempted.read_text() == "unattempted"


def test_linux_read_only_parent_reports_one_concise_error(
    tmp_path: Path,
) -> None:
    if not sys.platform.startswith("linux"):
        pytest.skip("Linux is the only claimed operating system")

    if os.geteuid() == 0:
        pytest.skip("permission semantics are not reliable as root")

    source = tmp_path / "notes.txt"
    read_only_parent = tmp_path / "read-only-parent"
    target_root = read_only_parent / "organized"

    source.write_text("notes")
    read_only_parent.mkdir()
    read_only_parent.chmod(0o500)

    command = [
        sys.executable,
        "-c",
        ("from smart_file_organizer.cli import main; main()"),
        "plan",
        "--apply",
        "--target",
        str(target_root),
        str(source),
    ]

    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
        )
    finally:
        read_only_parent.chmod(0o700)

    assert completed.returncode == 2
    assert completed.stdout == ""
    assert completed.stderr.startswith(
        "smart-file-organizer: error: destination parent is unusable: "
    )
    assert completed.stderr.count("\n") == 1
    assert "ERROR smart_file_organizer.cli" not in (completed.stderr)
    assert "Traceback" not in completed.stderr
    assert source.read_text() == "notes"
    assert not target_root.exists()
    assert list(tmp_path.rglob("*.json")) == []


def test_linux_case_distinct_sources_remain_distinct_on_apply(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    if not sys.platform.startswith("linux"):
        pytest.skip("Linux is the only claimed operating system")

    source_root = tmp_path / "source"
    target_root = tmp_path / "organized"
    source_root.mkdir()

    upper = source_root / "Report.txt"
    lower = source_root / "report.txt"

    upper.write_text("upper")
    lower.write_text("lower")

    assert upper.exists()
    assert lower.exists()
    assert upper != lower

    main(
        [
            "plan",
            "--apply",
            "--from",
            str(source_root),
            "--target",
            str(target_root),
        ]
    )

    captured = capsys.readouterr()

    assert captured.err == ""
    assert captured.out.startswith("Apply result: completed=2 failed=0 unattempted=0\n")
    assert (target_root / "documents" / "inbox" / "Report.txt").read_text() == "upper"
    assert (target_root / "documents" / "inbox" / "report.txt").read_text() == "lower"


def test_bounded_512_file_tree_dry_run_through_public_cli(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source_root = tmp_path / "source"
    target_root = tmp_path / "organized"
    source_root.mkdir()

    extensions = (".txt", ".jpg", ".py", ".bin")
    file_count = 512

    for index in range(file_count):
        extension = extensions[index % len(extensions)]
        source = source_root / f"synthetic-{index:04d}{extension}"
        source.write_text(f"synthetic file {index}\n")

    main(
        [
            "plan",
            "--from",
            str(source_root),
            "--target",
            str(target_root),
        ]
    )

    captured = capsys.readouterr()
    output_lines = captured.out.splitlines()

    assert captured.err == ""
    assert len(output_lines) == file_count
    assert all(" -> " in line for line in output_lines)
    assert not target_root.exists()
