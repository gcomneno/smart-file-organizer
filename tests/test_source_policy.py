from pathlib import Path

import pytest

from smart_file_organizer.cli import collect_sources, main
from smart_file_organizer.core import list_source_files
from smart_file_organizer.errors import (
    BrokenSourceSymlinkError,
    UnsupportedSourceSymlinkError,
)
from smart_file_organizer.path_validation import validate_source_file


def test_validate_source_file_accepts_symlink_to_regular_file(
    tmp_path: Path,
) -> None:
    referent = tmp_path / "referent.txt"
    source = tmp_path / "source.txt"

    referent.write_text("content")
    source.symlink_to(referent)

    validate_source_file(source)


def test_validate_source_file_rejects_broken_symlink(
    tmp_path: Path,
) -> None:
    source = tmp_path / "broken.txt"
    source.symlink_to(tmp_path / "missing.txt")

    with pytest.raises(
        BrokenSourceSymlinkError,
        match=f"source symlink is broken: {source}",
    ):
        validate_source_file(source)


def test_validate_source_file_rejects_directory_symlink(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "directory"
    source = tmp_path / "linked-directory"

    directory.mkdir()
    source.symlink_to(directory, target_is_directory=True)

    with pytest.raises(
        UnsupportedSourceSymlinkError,
        match="source symlink must point to a regular file",
    ):
        validate_source_file(source)


def test_collect_sources_rejects_symlinked_scan_root(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "directory"
    source_root = tmp_path / "linked-directory"

    directory.mkdir()
    source_root.symlink_to(directory, target_is_directory=True)

    with pytest.raises(
        UnsupportedSourceSymlinkError,
        match="source directory symlinks are not supported",
    ):
        collect_sources(source_root, [])


def test_direct_scan_includes_hidden_files_and_file_symlinks_only(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "source"
    nested = source_root / "nested"
    outside_file = tmp_path / "outside.txt"

    source_root.mkdir()
    nested.mkdir()

    visible = source_root / "visible.txt"
    hidden = source_root / ".hidden.txt"
    file_link = source_root / "linked.txt"
    directory_link = source_root / "linked-directory"
    broken_link = source_root / "broken.txt"

    visible.write_text("visible")
    hidden.write_text("hidden")
    nested.joinpath("nested.txt").write_text("nested")
    outside_file.write_text("outside")

    file_link.symlink_to(outside_file)
    directory_link.symlink_to(nested, target_is_directory=True)
    broken_link.symlink_to(tmp_path / "missing.txt")

    assert list_source_files(source_root) == sorted(
        [visible, hidden, file_link],
        key=str,
    )


def test_recursive_scan_includes_hidden_tree_without_following_links(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "source"
    nested = source_root / "nested"
    hidden_directory = source_root / ".hidden-directory"
    outside_directory = tmp_path / "outside"

    source_root.mkdir()
    nested.mkdir()
    hidden_directory.mkdir()
    outside_directory.mkdir()

    visible = source_root / "visible.txt"
    hidden = source_root / ".hidden.txt"
    nested_file = nested / "nested.txt"
    hidden_nested_file = hidden_directory / ".nested-hidden.txt"
    outside_file = outside_directory / "outside.txt"

    file_link = source_root / "linked-file.txt"
    directory_link = source_root / "linked-directory"
    broken_link = source_root / "broken.txt"
    cycle_link = nested / "cycle"

    visible.write_text("visible")
    hidden.write_text("hidden")
    nested_file.write_text("nested")
    hidden_nested_file.write_text("nested hidden")
    outside_file.write_text("outside")

    file_link.symlink_to(outside_file)
    directory_link.symlink_to(
        outside_directory,
        target_is_directory=True,
    )
    broken_link.symlink_to(tmp_path / "missing.txt")
    cycle_link.symlink_to(source_root, target_is_directory=True)

    discovered = list_source_files(source_root, recursive=True)

    assert discovered == sorted(
        [
            visible,
            hidden,
            nested_file,
            hidden_nested_file,
            file_link,
        ],
        key=str,
    )

    assert directory_link not in discovered
    assert broken_link not in discovered
    assert cycle_link not in discovered
    assert directory_link / "outside.txt" not in discovered


def test_main_previews_explicit_file_symlink(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    referent = tmp_path / "referent.jpg"
    source = tmp_path / "linked.jpg"
    target_root = tmp_path / "organized"

    referent.write_text("image")
    source.symlink_to(referent)

    main(
        [
            "--target",
            str(target_root),
            str(source),
        ]
    )

    captured = capsys.readouterr()

    assert captured.err == ""
    assert captured.out == (f"{source} -> {target_root / 'images' / 'linked.jpg'}\n")


def test_main_rejects_broken_explicit_symlink_without_traceback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "broken.txt"
    source.symlink_to(tmp_path / "missing.txt")

    with pytest.raises(SystemExit) as exc_info:
        main([str(source)])

    captured = capsys.readouterr()

    assert exc_info.value.code == 2
    assert f"source symlink is broken: {source}" in captured.err
    assert "Traceback" not in captured.err


def test_plan_help_documents_symlink_and_hidden_file_policy(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["plan", "--help"])

    captured = capsys.readouterr()
    normalized_help = " ".join(captured.out.split())

    assert exc_info.value.code == 0
    assert "Broken and directory symlinks are rejected." in normalized_help
    assert "Directory symlinks are rejected." in normalized_help
    assert (
        "without following directory symlinks. Hidden files are included."
        in normalized_help
    )
