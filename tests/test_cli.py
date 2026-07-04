from pathlib import Path

import pytest

import smart_file_organizer.cli as cli_module
from smart_file_organizer.cli import (
    build_parser,
    collect_sources,
    format_destination_conflicts,
    main,
)
from smart_file_organizer.core import FileCategory, PlannedMove
from smart_file_organizer.errors import SourceSelectionError


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


def test_main_inspect_content_uses_content_aware_plan(
    monkeypatch: pytest.MonkeyPatch,
    capsys,
) -> None:
    recorded_sources: list[Path] = []
    recorded_target: Path | None = None

    def fake_build_content_aware_plan(
        sources,
        target_root: Path,
        *,
        semantic_rules=None,
        verbose=False,
    ) -> list[PlannedMove]:
        nonlocal recorded_target
        recorded_sources.extend(sources)
        recorded_target = target_root

        return [
            PlannedMove(
                source=Path("generic.pdf"),
                destination=Path("organized/documents/taxes/generic.pdf"),
                category=FileCategory.DOCUMENTS,
            )
        ]

    monkeypatch.setattr(
        cli_module,
        "build_organization_plan_inspecting_content",
        fake_build_content_aware_plan,
        raising=False,
    )

    main(
        [
            "--inspect-content",
            "--target",
            "organized",
            "generic.pdf",
        ]
    )

    captured = capsys.readouterr()

    assert recorded_sources == [Path("generic.pdf")]
    assert recorded_target == Path("organized")
    assert captured.out == ("generic.pdf -> organized/documents/taxes/generic.pdf\n")


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


def test_main_prints_organization_plan_as_json(capsys) -> None:
    main(
        [
            "--format",
            "json",
            "--target",
            "organized",
            "photo.jpg",
            "notes.txt",
        ]
    )

    captured = capsys.readouterr()

    assert captured.out == (
        "[\n"
        "  {\n"
        '    "source": "photo.jpg",\n'
        '    "destination": "organized/images/photo.jpg",\n'
        '    "category": "images"\n'
        "  },\n"
        "  {\n"
        '    "source": "notes.txt",\n'
        '    "destination": "organized/documents/notes.txt",\n'
        '    "category": "documents"\n'
        "  }\n"
        "]\n"
    )


def test_main_plan_command_prints_organization_plan(capsys) -> None:
    main(
        [
            "plan",
            "--target",
            "organized",
            "photo.jpg",
        ]
    )

    captured = capsys.readouterr()

    assert captured.out == "photo.jpg -> organized/images/photo.jpg\n"


def test_build_parser_lists_plan_command(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        build_parser().parse_args(["--help"])

    captured = capsys.readouterr()

    assert exc_info.value.code == 0
    assert "plan" in captured.out


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


def test_main_recursive_scan_includes_nested_files(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    photo = tmp_path / "photo.jpg"
    notes = tmp_path / "notes.txt"
    nested_dir = tmp_path / "nested"
    nested_file = nested_dir / "ignored.txt"

    photo.write_text("fake image")
    notes.write_text("hello")
    nested_dir.mkdir()
    nested_file.write_text("include me")

    main(
        [
            "--from",
            str(tmp_path),
            "--recursive",
            "--target",
            "organized",
        ]
    )

    captured = capsys.readouterr()

    assert captured.out == (
        f"{nested_file} -> organized/documents/ignored.txt\n"
        f"{notes} -> organized/documents/notes.txt\n"
        f"{photo} -> organized/images/photo.jpg\n"
    )


def test_main_rejects_recursive_without_source_directory(capsys) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--recursive", "photo.jpg"])

    captured = capsys.readouterr()

    assert exc_info.value.code == 2
    assert "--recursive requires --from" in captured.err


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


def test_main_resolves_destination_conflicts_with_rename_strategy(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    folder_a = tmp_path / "folder-a"
    folder_b = tmp_path / "folder-b"
    folder_a.mkdir()
    folder_b.mkdir()

    photo_a = folder_a / "photo.jpg"
    photo_b = folder_b / "photo.jpg"
    photo_a.write_text("first")
    photo_b.write_text("second")

    target_root = tmp_path / "organized"

    main(
        [
            "--conflict-strategy",
            "rename",
            "--target",
            str(target_root),
            str(photo_a),
            str(photo_b),
        ]
    )

    captured = capsys.readouterr()

    assert captured.out == (
        f"{photo_a} -> {target_root}/images/photo.jpg\n"
        f"{photo_b} -> {target_root}/images/photo__folder-b.jpg\n"
    )


def test_main_applies_organization_plan_with_rename_strategy(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    folder_a = tmp_path / "folder-a"
    folder_b = tmp_path / "folder-b"
    target_root = tmp_path / "organized"
    folder_a.mkdir()
    folder_b.mkdir()

    photo_a = folder_a / "photo.jpg"
    photo_b = folder_b / "photo.jpg"
    photo_a.write_text("first")
    photo_b.write_text("second")

    main(
        [
            "--conflict-strategy",
            "rename",
            "--target",
            str(target_root),
            "--apply",
            str(photo_a),
            str(photo_b),
        ]
    )

    captured = capsys.readouterr()

    assert captured.err == ""
    assert (target_root / "images" / "photo.jpg").read_text() == "first"
    assert (target_root / "images" / "photo__folder-b.jpg").read_text() == "second"


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


def test_main_uses_configured_semantic_rules(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_file = tmp_path / "smart-file-organizer.toml"
    config_file.write_text(
        """
[[semantic_rules]]
folder = "documents/demo-utility"
keywords = ["synthetic invoice"]
""",
        encoding="utf-8",
    )

    main(
        [
            "--config",
            str(config_file),
            "--target",
            "organized",
            "synthetic-invoice.pdf",
        ]
    )

    assert capsys.readouterr().out == (
        "synthetic-invoice.pdf -> "
        "organized/documents/demo-utility/synthetic-invoice.pdf\n"
    )


def test_main_keeps_builtin_semantic_rules_with_config(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_file = tmp_path / "smart-file-organizer.toml"
    config_file.write_text(
        """
[[semantic_rules]]
folder = "documents/demo-utility"
keywords = ["synthetic invoice"]
""",
        encoding="utf-8",
    )

    main(
        [
            "--config",
            str(config_file),
            "--target",
            "organized",
            "Conto-FASTWEB-M000000000-20260501.pdf",
        ]
    )

    assert capsys.readouterr().out == (
        "Conto-FASTWEB-M000000000-20260501.pdf -> "
        "organized/documents/utilities/fastweb/"
        "Conto-FASTWEB-M000000000-20260501.pdf\n"
    )


def test_main_uses_configured_regex_patterns(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_file = tmp_path / "smart-file-organizer.toml"
    config_file.write_text(
        """
[[semantic_rules]]
folder = "documents/analisi-mediche"
patterns = ['\\d{8} analisi ade \\d+']
""",
        encoding="utf-8",
    )
    report = tmp_path / "20260626_analisi_ade_1.pdf"
    report.write_text("demo")

    main(
        [
            "--config",
            str(config_file),
            "--target",
            "organized",
            str(report),
        ]
    )

    assert capsys.readouterr().out == (
        f"{report} -> organized/documents/analisi-mediche/20260626_analisi_ade_1.pdf\n"
    )


def test_main_reports_invalid_config(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_file = tmp_path / "smart-file-organizer.toml"
    config_file.write_text(
        """
semantic_rules = "wrong"
""",
        encoding="utf-8",
    )

    with pytest.raises(SystemExit) as error:
        main(["--config", str(config_file), "notes.txt"])

    assert error.value.code == 2
    assert "semantic_rules must be a list" in capsys.readouterr().err


def test_collect_sources_raises_source_selection_error_for_conflicting_inputs(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        SourceSelectionError,
        match="pass either --from or source files, not both",
    ):
        collect_sources(tmp_path, [Path("notes.txt")])


def test_collect_sources_raises_source_selection_error_for_recursive_without_from() -> (
    None
):
    with pytest.raises(
        SourceSelectionError,
        match="--recursive requires --from",
    ):
        collect_sources(None, [Path("notes.txt")], recursive=True)


def test_main_is_quiet_by_default(capsys: pytest.CaptureFixture[str]) -> None:
    main(["photo.jpg"])

    captured = capsys.readouterr()

    assert captured.err == ""


def test_main_verbose_logs_high_level_events(
    capsys: pytest.CaptureFixture[str],
) -> None:
    main(["--verbose", "photo.jpg"])

    captured = capsys.readouterr()

    assert "event=cli_started inspect_content=False apply=False" in captured.err
    assert "event=sources_collected count=1" in captured.err
    assert "event=plan_built count=1 inspect_content=False" in captured.err
    assert "photo.jpg" not in captured.err
