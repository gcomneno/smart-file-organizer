"""Command line interface for smart-file-organizer."""

import argparse
from collections.abc import Mapping, Sequence
from pathlib import Path

from smart_file_organizer.core import (
    PlannedMove,
    build_organization_plan,
    execute_plan,
    find_destination_conflicts,
    list_source_files,
)


def build_parser() -> argparse.ArgumentParser:
    """Build the command line argument parser."""
    parser = argparse.ArgumentParser(
        prog="smart-file-organizer",
        description="Build a file organization plan without moving files.",
    )
    parser.add_argument(
        "sources",
        nargs="*",
        type=Path,
        help="Files to include in the organization plan.",
    )
    parser.add_argument(
        "--from",
        dest="source_root",
        type=Path,
        help="Source directory to scan for direct files.",
    )
    parser.add_argument(
        "--target",
        type=Path,
        default=Path("organized"),
        help="Target root directory for organized files. Defaults to 'organized'.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Execute the organization plan. Without this flag, only print the plan.",
    )

    return parser


def collect_sources(
    source_root: Path | None,
    explicit_sources: Sequence[Path],
) -> list[Path]:
    """Collect source files from explicit arguments or a source directory."""
    if source_root is not None and explicit_sources:
        raise ValueError("pass either --from or source files, not both")

    if source_root is None and not explicit_sources:
        raise ValueError("pass at least one source file or use --from")

    if source_root is not None:
        if not source_root.exists():
            raise ValueError(f"source directory does not exist: {source_root}")

        if not source_root.is_dir():
            raise ValueError(f"source path is not a directory: {source_root}")

        return list_source_files(source_root)

    return list(explicit_sources)


def format_planned_move(move: PlannedMove) -> str:
    """Format a planned move for terminal output."""
    return f"{move.source} -> {move.destination}"


def format_destination_conflicts(
    conflicts: Mapping[Path, Sequence[PlannedMove]],
) -> str:
    """Format destination conflicts for terminal output."""
    lines = ["destination conflicts detected:"]

    for destination, moves in sorted(conflicts.items(), key=lambda item: str(item[0])):
        sources = ", ".join(str(move.source) for move in moves)
        lines.append(f"- {destination}: {sources}")

    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> None:
    """Run the smart-file-organizer command."""
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        sources = collect_sources(args.source_root, args.sources)
    except ValueError as error:
        parser.error(str(error))

    plan = build_organization_plan(sources, args.target)
    conflicts = find_destination_conflicts(plan)

    if conflicts:
        parser.error(format_destination_conflicts(conflicts))

    if args.apply:
        try:
            execute_plan(plan)
        except (FileExistsError, FileNotFoundError, ValueError) as error:
            parser.error(str(error))
        return

    for move in plan:
        print(format_planned_move(move))
