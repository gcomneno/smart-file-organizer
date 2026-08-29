import json
import hashlib
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

import pytest

import smart_file_organizer.cli as cli_module
import smart_file_organizer.execution as execution_module
from smart_file_organizer.application import (
    OrganizationPlan,
    OrganizationPlanConflictError,
    PlanOrganizationRequest,
)
from smart_file_organizer.cli import (
    build_parser,
    collect_sources,
    format_destination_conflicts,
    main,
)
from smart_file_organizer.core import FileCategory, PlannedMove
from smart_file_organizer.errors import ManifestWriteError, SourceSelectionError
from smart_file_organizer.manifest_models import RecoveryDisposition


@pytest.fixture
def explicit_source_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Provide real files for CLI examples that use relative sources."""
    monkeypatch.chdir(tmp_path)
    for relative_path in (
        "generic.pdf",
        "photo.jpg",
        "notes.txt",
        "script.py",
        "synthetic-invoice.pdf",
        "mystery.pdf",
        "Conto-FASTWEB-M000000000-20260501.pdf",
        "folder-a/photo.jpg",
        "folder-b/photo.jpg",
    ):
        path = Path(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("synthetic fixture")


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


def _recovery_payload_v1(target: Path) -> dict[str, Any]:
    timestamp = datetime.now(timezone.utc).isoformat()
    source = target.parent / "source.txt"
    destination = target / "documents" / "source.txt"
    return {
        "schema_version": 1,
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
            }
        ],
    }


def _recovery_payload_v2(target: Path, content: bytes) -> dict[str, Any]:
    payload = _recovery_payload_v1(target)
    timestamp = cast(str, payload["started_at"])
    payload["schema_version"] = 2
    cast(list[dict[str, Any]], payload["moves"])[0]["identity"] = {
        "algorithm": "sha256",
        "digest": hashlib.sha256(content).hexdigest(),
        "size_bytes": len(content),
        "source_observed_at": timestamp,
        "destination_observed_at": timestamp,
    }
    return payload


def _write_recovery_manifest(target: Path, payload: dict[str, Any]) -> Path:
    directory = target / ".smart-file-organizer" / "manifests"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "apply-20260805T120000000000Z-0123456789ab.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _first_recovery_move(payload: dict[str, Any]) -> dict[str, Any]:
    return cast(list[dict[str, Any]], payload["moves"])[0]


def test_main_maps_inspect_content_request_and_renders_application_plan(
    monkeypatch: pytest.MonkeyPatch,
    capsys,
    explicit_source_files: None,
) -> None:
    recorded_request: PlanOrganizationRequest | None = None
    recorded_verbose: bool | None = None
    recorded_source_collector: object | None = None

    def fake_plan_organization(
        request,
        *,
        verbose=False,
        _source_collector=None,
    ) -> OrganizationPlan:
        nonlocal recorded_request
        nonlocal recorded_verbose
        nonlocal recorded_source_collector

        recorded_request = request
        recorded_verbose = verbose
        recorded_source_collector = _source_collector
        return OrganizationPlan(
            Path("organized"),
            (
                PlannedMove(
                    source=Path("generic.pdf"),
                    destination=Path("organized/documents/taxes/generic.pdf"),
                    category=FileCategory.DOCUMENTS,
                ),
            ),
        )

    monkeypatch.setattr(
        cli_module,
        "plan_organization",
        fake_plan_organization,
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

    assert recorded_request is not None
    assert recorded_request.explicit_sources == (Path("generic.pdf"),)
    assert recorded_request.target_root == Path("organized")
    assert recorded_request.inspect_content is True
    assert recorded_request.conflict_strategy == "fail"
    assert recorded_verbose is False
    assert recorded_source_collector is cli_module.collect_sources
    assert captured.out == ("generic.pdf -> organized/documents/taxes/generic.pdf\n")


def test_main_preserves_collect_sources_compatibility_seam(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    explicit_source_files: None,
) -> None:
    original_collect_sources = cli_module.collect_sources
    calls: list[tuple[Path | None, tuple[Path, ...], bool]] = []

    def recording_collect_sources(
        source_root: Path | None,
        explicit_sources: Sequence[Path],
        *,
        recursive: bool = False,
    ) -> list[Path]:
        source_tuple = tuple(explicit_sources)
        calls.append((source_root, source_tuple, recursive))

        return original_collect_sources(
            source_root,
            source_tuple,
            recursive=recursive,
        )

    monkeypatch.setattr(
        cli_module,
        "collect_sources",
        recording_collect_sources,
    )

    main(["generic.pdf"])

    assert calls == [
        (
            None,
            (Path("generic.pdf"),),
            False,
        )
    ]
    assert capsys.readouterr().out == (
        "generic.pdf -> organized/documents/inbox/generic.pdf\n"
    )


def test_main_prints_organization_plan_from_explicit_sources(
    capsys, explicit_source_files: None
) -> None:
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
        "notes.txt -> organized/documents/inbox/notes.txt\n"
        "script.py -> organized/code/script.py\n"
    )


def test_main_prints_organization_plan_as_json(
    capsys, explicit_source_files: None
) -> None:
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
        '    "destination": "organized/documents/inbox/notes.txt",\n'
        '    "category": "documents"\n'
        "  }\n"
        "]\n"
    )


def test_main_plan_command_prints_organization_plan(
    capsys, explicit_source_files: None
) -> None:
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
        f"{notes} -> organized/documents/inbox/notes.txt\n"
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
        f"{nested_file} -> organized/documents/inbox/ignored.txt\n"
        f"{notes} -> organized/documents/inbox/notes.txt\n"
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


def test_main_rejects_destination_conflicts(
    capsys, explicit_source_files: None
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["folder-a/photo.jpg", "folder-b/photo.jpg"])

    captured = capsys.readouterr()

    assert exc_info.value.code == 2
    assert captured.out == ""
    assert "destination conflicts detected:" in captured.err
    assert "organized/images/photo.jpg" in captured.err
    assert "folder-a/photo.jpg" in captured.err
    assert "folder-b/photo.jpg" in captured.err
    assert "WARNING smart_file_organizer.cli" not in captured.err
    assert "Traceback" not in captured.err
    assert "usage:" not in captured.err


def test_main_formats_application_conflicts_at_cli_boundary(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    explicit_source_files: None,
) -> None:
    destination = Path("organized/images/photo.jpg")
    conflicts = {
        destination: (
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
        )
    }

    def fail_planning(*_args, **_kwargs) -> OrganizationPlan:
        raise OrganizationPlanConflictError(conflicts)

    monkeypatch.setattr(cli_module, "plan_organization", fail_planning)

    with pytest.raises(SystemExit) as exc_info:
        main(["photo.jpg"])

    captured = capsys.readouterr()
    assert exc_info.value.code == 2
    assert captured.err == (
        "smart-file-organizer: error: destination conflicts detected:\n"
        "- organized/images/photo.jpg: folder-a/photo.jpg, folder-b/photo.jpg\n"
    )


def test_main_verbose_logs_destination_conflict_event(
    capsys,
    explicit_source_files: None,
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "--verbose",
                "folder-a/photo.jpg",
                "folder-b/photo.jpg",
            ]
        )

    captured = capsys.readouterr()

    assert exc_info.value.code == 2
    assert captured.out == ""
    assert (
        "INFO smart_file_organizer.cli event=destination_conflicts count=1"
    ) in captured.err
    assert "destination conflicts detected:" in captured.err
    assert "Traceback" not in captured.err


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


def test_main_resolves_repeated_parent_labels_with_rename_strategy(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source_root = tmp_path / "source"
    target_root = tmp_path / "organized"

    tools = []

    for snapshot in ("snapshot-a", "snapshot-b", "snapshot-c"):
        device = source_root / snapshot / "device"
        device.mkdir(parents=True)
        tool = device / "tool"
        tool.write_text(snapshot)
        tools.append(tool)

    main(
        [
            "plan",
            "--recursive",
            "--conflict-strategy",
            "rename",
            "--from",
            str(source_root),
            "--target",
            str(target_root),
        ]
    )

    captured = capsys.readouterr()

    assert captured.err == ""
    assert captured.out == (
        f"{tools[0]} -> {target_root}/other/tool\n"
        f"{tools[1]} -> {target_root}/other/tool__device\n"
        f"{tools[2]} -> {target_root}/other/tool__device-2\n"
    )
    assert not target_root.exists()


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

    output_lines = captured.out.splitlines()
    assert output_lines[0] == "Apply result: completed=2 failed=0 unattempted=0"
    assert output_lines[1].startswith("Manifest: ")
    assert Path(output_lines[1].removeprefix("Manifest: ")).is_file()
    assert captured.err == ""
    assert not photo.exists()
    assert not notes.exists()
    assert (target_root / "images" / "photo.jpg").read_text() == "fake image"
    assert (target_root / "documents" / "inbox" / "notes.txt").read_text() == "hello"


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


def test_main_maps_manifest_write_error_to_status_one(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    explicit_source_files: None,
) -> None:
    def fail_apply(_plan: OrganizationPlan) -> None:
        raise ManifestWriteError("could not persist apply manifest")

    monkeypatch.setattr(cli_module, "apply_organization", fail_apply)

    with pytest.raises(SystemExit) as exc_info:
        main(["--apply", "photo.jpg"])

    captured = capsys.readouterr()
    assert exc_info.value.code == 1
    assert captured.out == ""
    assert captured.err == (
        "smart-file-organizer: error: could not persist apply manifest\n"
    )


def test_main_uses_configured_semantic_rules(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    explicit_source_files: None,
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


def test_main_uses_configured_fallback_folder(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    explicit_source_files: None,
) -> None:
    config_file = tmp_path / "smart-file-organizer.toml"
    config_file.write_text(
        """
fallback_folder = "documents/inbox"

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
            "mystery.pdf",
        ]
    )

    assert capsys.readouterr().out == (
        "mystery.pdf -> organized/documents/inbox/mystery.pdf\n"
    )


def test_main_keeps_builtin_semantic_rules_with_config(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    explicit_source_files: None,
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
    explicit_source_files: None,
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


def test_main_is_quiet_by_default(
    capsys: pytest.CaptureFixture[str], explicit_source_files: None
) -> None:
    main(["photo.jpg"])

    captured = capsys.readouterr()

    assert captured.err == ""


def test_main_verbose_logs_high_level_events(
    capsys: pytest.CaptureFixture[str],
    explicit_source_files: None,
) -> None:
    main(["--verbose", "photo.jpg"])

    captured = capsys.readouterr()

    assert "event=cli_started inspect_content=False apply=False" in captured.err
    assert (
        "INFO smart_file_organizer.application event=sources_collected count=1"
    ) in captured.err
    assert "event=plan_built count=1 inspect_content=False" in captured.err
    assert "photo.jpg" not in captured.err


def test_main_verbose_logs_loaded_configuration(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    explicit_source_files: None,
) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
[[semantic_rules]]
folder = "documents/custom"
keywords = ["synthetic"]
""",
        encoding="utf-8",
    )

    main(
        [
            "--verbose",
            "--config",
            str(config_file),
            "notes.txt",
        ]
    )

    captured = capsys.readouterr()

    assert (
        "INFO smart_file_organizer.application event=config_loaded semantic_rules=1"
    ) in captured.err


def test_main_verbose_logs_conflict_resolution(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    first_parent = tmp_path / "first"
    second_parent = tmp_path / "second"
    first_parent.mkdir()
    second_parent.mkdir()

    first = first_parent / "photo.jpg"
    second = second_parent / "photo.jpg"
    first.write_text("first", encoding="utf-8")
    second.write_text("second", encoding="utf-8")

    main(
        [
            "--verbose",
            "--conflict-strategy",
            "rename",
            str(first),
            str(second),
        ]
    )

    captured = capsys.readouterr()

    assert (
        "INFO smart_file_organizer.application "
        "event=destination_conflicts_resolving count=1"
    ) in captured.err


@pytest.mark.parametrize(
    ("source_kind", "message"),
    [
        ("missing", "source file does not exist"),
        ("directory", "source path is not a file"),
    ],
)
def test_main_rejects_invalid_explicit_source_without_preview_or_traceback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    source_kind: str,
    message: str,
) -> None:
    source = tmp_path / source_kind
    if source_kind == "directory":
        source.mkdir()

    with pytest.raises(SystemExit) as exc_info:
        main([str(source)])

    captured = capsys.readouterr()
    assert exc_info.value.code == 2
    assert captured.out == ""
    assert message in captured.err
    assert "Traceback" not in captured.err


def test_main_rejects_target_equal_to_scanned_source(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "notes.txt").write_text("notes")

    with pytest.raises(SystemExit) as exc_info:
        main(["--from", str(tmp_path), "--target", str(tmp_path)])

    captured = capsys.readouterr()
    assert exc_info.value.code == 2
    assert captured.out == ""
    assert "target directory must differ from source directory" in captured.err
    assert "Traceback" not in captured.err


def test_main_rejects_recursive_target_inside_scanned_source(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    (source_root / "notes.txt").write_text("notes")

    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "--from",
                str(source_root),
                "--recursive",
                "--target",
                str(source_root / "organized"),
            ]
        )

    captured = capsys.readouterr()
    assert exc_info.value.code == 2
    assert captured.out == ""
    assert "must not be inside a recursively scanned source" in captured.err
    assert "Traceback" not in captured.err


def test_main_reports_unsafe_config_folder_without_traceback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "notes.txt"
    source.write_text("notes")
    config_file = tmp_path / "unsafe.toml"
    config_file.write_text('fallback_folder = "/escaped"\n')

    with pytest.raises(SystemExit) as exc_info:
        main(["--config", str(config_file), str(source)])

    captured = capsys.readouterr()
    assert exc_info.value.code == 2
    assert captured.out == ""
    assert "destination folder must be relative" in captured.err
    assert "Traceback" not in captured.err


def test_main_allows_non_recursive_target_inside_scanned_source(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()

    source = source_root / "notes.txt"
    source.write_text("notes")

    target_root = source_root / "organized"

    main(
        [
            "--from",
            str(source_root),
            "--target",
            str(target_root),
        ]
    )

    captured = capsys.readouterr()
    assert captured.out == (f"{source} -> {target_root}/documents/inbox/notes.txt\n")
    assert captured.err == ""
    assert not target_root.exists()


def test_main_reports_partial_apply_with_durable_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
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

    real_move = execution_module.shutil.move
    calls = 0

    def fail_second_move(source: Path, destination: Path) -> Path | str:
        nonlocal calls
        calls += 1

        if calls == 2:
            raise PermissionError("synthetic permission failure")

        return real_move(source, destination)

    monkeypatch.setattr(execution_module.shutil, "move", fail_second_move)

    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "--target",
                str(target_root),
                "--apply",
                str(first),
                str(second),
                str(third),
            ]
        )

    captured = capsys.readouterr()

    assert exc_info.value.code == 1
    assert captured.out == ""
    assert "Traceback" not in captured.err

    output_lines = captured.err.splitlines()
    assert output_lines[0] == "Apply result: completed=1 failed=1 unattempted=1"
    assert output_lines[1].startswith("Manifest: ")
    assert output_lines[2].startswith("Failed move: ")

    manifest_path = Path(output_lines[1].removeprefix("Manifest: "))
    payload = json.loads(manifest_path.read_text())

    assert payload["state"] == "failed"
    assert [move["status"] for move in payload["moves"]] == [
        "completed",
        "failed",
        "unattempted",
    ]

    assert not first.exists()
    assert second.exists()
    assert third.exists()


def test_main_reports_empty_directory_scan(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source_root = tmp_path / "empty-source"
    target_root = tmp_path / "organized"
    source_root.mkdir()

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

    assert captured.out == "No files found.\n"
    assert captured.err == ""
    assert not target_root.exists()


def test_main_preserves_json_contract_for_empty_scan(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source_root = tmp_path / "empty-source"
    source_root.mkdir()

    main(
        [
            "plan",
            "--format",
            "json",
            "--from",
            str(source_root),
        ]
    )

    captured = capsys.readouterr()

    assert captured.out == "[]\n"
    assert captured.err == ""


def test_main_empty_apply_reports_zero_counts_and_manifest(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source_root = tmp_path / "empty-source"
    target_root = tmp_path / "organized"
    source_root.mkdir()

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
    output_lines = captured.out.splitlines()

    assert output_lines[0] == ("Apply result: completed=0 failed=0 unattempted=0")
    assert output_lines[1].startswith("Manifest: ")
    assert Path(output_lines[1].removeprefix("Manifest: ")).is_file()
    assert captured.err == ""


def test_main_expected_error_is_concise_without_usage_or_traceback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    missing_source = tmp_path / "missing.txt"

    with pytest.raises(SystemExit) as exc_info:
        main(["plan", str(missing_source)])

    captured = capsys.readouterr()

    assert exc_info.value.code == 2
    assert captured.out == ""
    assert captured.err == (
        f"smart-file-organizer: error: source file does not exist: {missing_source}\n"
    )
    assert "usage:" not in captured.err
    assert "Traceback" not in captured.err


def test_top_level_help_identifies_canonical_and_compatibility_syntax(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])

    captured = capsys.readouterr()
    normalized = " ".join(captured.out.split())

    assert exc_info.value.code == 0
    assert captured.err == ""
    assert "Canonical usage: smart-file-organizer plan" in normalized
    assert "compatibility syntax" in normalized


def test_recover_plan_text_separates_reconciliation_identity_safety_and_plan(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "target"
    content = b"current"
    payload = _recovery_payload_v2(target, content)
    destination = Path(_first_recovery_move(payload)["final_path"])
    destination.parent.mkdir(parents=True)
    destination.write_bytes(content)
    manifest_path = _write_recovery_manifest(target, payload)

    main(["recover", "plan", str(manifest_path)])

    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out == (
        f"- {tmp_path}/source.txt -> {destination}\n"
        "  reconciliation: consistent\n"
        "  identity: identity_match (identity_verified)\n"
        "  safety: safe_to_recover (recovery_preconditions_verified) - "
        "recovery preconditions are verified by historical evidence and current observations\n"
        f"  plan: proposed {destination} -> {tmp_path}/source.txt\n"
    )


def test_recover_plan_refused_text_does_not_imply_mutation_authority(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "target"
    payload = _recovery_payload_v1(target)
    destination = Path(_first_recovery_move(payload)["final_path"])
    destination.parent.mkdir(parents=True)
    destination.write_text("v1-current", encoding="utf-8")
    manifest_path = _write_recovery_manifest(target, payload)

    main(["recover", "plan", str(manifest_path)])

    captured = capsys.readouterr()
    assert captured.err == ""
    assert "identity: identity_unverifiable (historical_identity_absent)" in (
        captured.out
    )
    assert "safety: refused (identity_unverifiable)" in captured.out
    assert "plan: refused" in captured.out
    assert "proposed" not in captured.out


def test_recover_plan_json_schema_v1_for_proposed_assessment(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "target"
    content = b"private payload should not be emitted"
    payload = _recovery_payload_v2(target, content)
    destination = Path(_first_recovery_move(payload)["final_path"])
    destination.parent.mkdir(parents=True)
    destination.write_bytes(content)
    manifest_path = _write_recovery_manifest(target, payload)

    main(["recover", "plan", str(manifest_path), "--json"])
    first = capsys.readouterr().out
    main(["recover", "plan", str(manifest_path), "--json"])
    second = capsys.readouterr().out
    data = json.loads(first)

    assert first == second
    assert data["recovery_assessment_schema_version"] == 1
    assert data["manifest"] == {
        "path": str(manifest_path),
        "schema_version": 2,
        "state": "completed",
    }
    assert data["summary"] == {
        "total": 1,
        "proposed": 1,
        "refused": 0,
        "reconciliation": {"consistent": 1},
        "safety": {"refused": 0, "safe_to_recover": 1},
    }
    assert data["items"] == [
        {
            "index": 0,
            "historical": {
                "original_path": str(tmp_path / "source.txt"),
                "final_path": str(destination),
                "category": "documents",
                "status": "completed",
            },
            "identity": {
                "state": "identity_match",
                "reason": "identity_verified",
            },
            "plan": {
                "disposition": "proposed",
                "recovery_source": str(destination),
                "recovery_destination": str(tmp_path / "source.txt"),
            },
            "reconciliation": {
                "state": "consistent",
                "source_exists": False,
                "destination_exists": True,
            },
            "safety": {
                "state": "safe_to_recover",
                "reason": "recovery_preconditions_verified",
                "explanation": (
                    "recovery preconditions are verified by historical evidence "
                    "and current observations"
                ),
            },
        }
    ]
    assert "private payload" not in first
    assert "digest" not in first
    assert "size_bytes" not in first
    assert "observed_at" not in first
    assert "timestamp" not in first


def test_recover_plan_json_schema_v1_for_refused_v1_assessment(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "target"
    payload = _recovery_payload_v1(target)
    destination = Path(_first_recovery_move(payload)["final_path"])
    destination.parent.mkdir(parents=True)
    destination.write_text("current", encoding="utf-8")
    manifest_path = _write_recovery_manifest(target, payload)

    main(["recover", "plan", str(manifest_path), "--json"])

    data = json.loads(capsys.readouterr().out)
    item = data["items"][0]
    assert data["summary"]["proposed"] == 0
    assert data["summary"]["refused"] == 1
    assert item["identity"] == {
        "state": "identity_unverifiable",
        "reason": "historical_identity_absent",
    }
    assert item["safety"]["state"] == "refused"
    assert item["safety"]["reason"] == "identity_unverifiable"
    assert item["plan"] == {"disposition": "refused"}
    assert "recovery_source" not in item["plan"]
    assert "recovery_destination" not in item["plan"]


def test_recover_plan_refused_assessment_exits_successfully(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "target"
    payload = _recovery_payload_v1(target)
    destination = Path(_first_recovery_move(payload)["final_path"])
    destination.parent.mkdir(parents=True)
    destination.write_text("current", encoding="utf-8")
    manifest_path = _write_recovery_manifest(target, payload)

    main(["recover", "plan", str(manifest_path), "--json"])

    assert json.loads(capsys.readouterr().out)["items"][0]["plan"] == {
        "disposition": "refused"
    }


def test_recover_plan_malformed_input_exits_two(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "target"
    manifest_path = _write_recovery_manifest(target, _recovery_payload_v1(target))
    manifest_path.write_text("{", encoding="utf-8")

    with pytest.raises(SystemExit) as exc_info:
        main(["recover", "plan", str(manifest_path)])

    captured = capsys.readouterr()
    assert exc_info.value.code == 2
    assert captured.out == ""
    assert "manifest JSON is malformed" in captured.err


def test_recover_plan_unsupported_schema_exits_two(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "target"
    payload = _recovery_payload_v1(target)
    payload["schema_version"] = 999
    manifest_path = _write_recovery_manifest(target, payload)

    with pytest.raises(SystemExit) as exc_info:
        main(["recover", "plan", str(manifest_path)])

    captured = capsys.readouterr()
    assert exc_info.value.code == 2
    assert captured.out == ""
    assert "manifest schema version is unsupported" in captured.err


def test_recover_plan_access_failure_exits_one(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fail_assessment(_path: Path):
        raise cli_module.ManifestAccessError("manifest cannot be read")

    monkeypatch.setattr(cli_module, "assess_recovery", fail_assessment)

    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "recover",
                "plan",
                "/tmp/target/.smart-file-organizer/manifests/"
                "apply-20260805T120000000000Z-0123456789ab.json",
            ]
        )

    captured = capsys.readouterr()
    assert exc_info.value.code == 1
    assert captured.out == ""
    assert captured.err == "smart-file-organizer: error: manifest cannot be read\n"


def test_recover_plan_cli_uses_assess_recovery_without_orchestration_bypass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "target"
    content = b"current"
    payload = _recovery_payload_v2(target, content)
    destination = Path(_first_recovery_move(payload)["final_path"])
    destination.parent.mkdir(parents=True)
    destination.write_bytes(content)
    manifest_path = _write_recovery_manifest(target, payload)
    assessment = cli_module.assess_recovery(manifest_path)

    monkeypatch.setattr(cli_module, "assess_recovery", lambda _path: assessment)
    monkeypatch.setattr(
        cli_module,
        "verify_manifest",
        lambda _path: pytest.fail("recovery CLI bypassed assess_recovery"),
    )
    monkeypatch.setattr(
        cli_module,
        "load_manifest",
        lambda _path: pytest.fail("recovery CLI bypassed assess_recovery"),
    )

    main(["recover", "plan", str(manifest_path), "--json"])

    data = json.loads(capsys.readouterr().out)
    assert data["items"][0]["plan"]["disposition"] == RecoveryDisposition.PROPOSED


def test_recover_plan_renderer_does_not_hash_or_reinterpret_recovery_semantics() -> (
    None
):
    source = Path(cli_module.render_recovery_assessment.__code__.co_filename).read_text(
        encoding="utf-8"
    )

    assert "hashlib" not in source
    assert "_fingerprint" not in source
    assert "classify_recovery_safety" not in source
    assert "build_recovery_plan" not in source


def test_recover_plan_matches_application_assessment_semantics(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "target"
    content = b"current"
    payload = _recovery_payload_v2(target, content)
    destination = Path(_first_recovery_move(payload)["final_path"])
    destination.parent.mkdir(parents=True)
    destination.write_bytes(content)
    manifest_path = _write_recovery_manifest(target, payload)
    assessment = cli_module.assess_recovery(manifest_path)

    main(["recover", "plan", str(manifest_path), "--json"])

    item = json.loads(capsys.readouterr().out)["items"][0]
    assert item["identity"]["state"] == assessment.verification.moves[0].identity.state
    assert item["safety"]["reason"] == (
        assessment.safety_classification.decisions[0].reason
    )
    assert item["plan"]["disposition"] == assessment.plan.items[0].disposition


def test_recover_plan_does_not_mutate_filesystem(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "target"
    content = b"current"
    payload = _recovery_payload_v2(target, content)
    source = Path(_first_recovery_move(payload)["original_path"])
    destination = Path(_first_recovery_move(payload)["final_path"])
    destination.parent.mkdir(parents=True)
    destination.write_bytes(content)
    manifest_path = _write_recovery_manifest(target, payload)
    manifest_bytes = manifest_path.read_bytes()
    destination_bytes = destination.read_bytes()

    main(["recover", "plan", str(manifest_path), "--json"])

    assert capsys.readouterr().err == ""
    assert not source.exists()
    assert destination.read_bytes() == destination_bytes
    assert manifest_path.read_bytes() == manifest_bytes
