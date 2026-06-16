"""Command line interface for smart-file-organizer."""

import argparse
import logging
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from smart_file_organizer.app_logging import configure_logging
from smart_file_organizer.config import OrganizerConfig, load_config
from smart_file_organizer.content_planning import (
    build_organization_plan_inspecting_content,
)
from smart_file_organizer.core import (
    PlannedMove,
    SemanticFolderRule,
    build_organization_plan,
    execute_plan,
    find_destination_conflicts,
    list_source_files,
)
from smart_file_organizer.errors import (
    ConfigError,
    DestinationConflictError,
    DestinationExistsError,
    SourceMissingError,
    SourceSelectionError,
)


logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    """Build the command line argument parser."""
    parser = argparse.ArgumentParser(
        prog="smart-file-organizer",
        description="Organize files through safe command groups.",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="command")

    plan_parser = subparsers.add_parser(
        "plan",
        help="Build or apply a file organization plan.",
        description="Build a file organization plan without moving files by default.",
    )
    _add_plan_arguments(plan_parser)

    return parser


def _add_plan_arguments(parser: argparse.ArgumentParser) -> None:
    """Add file planning arguments to a parser."""
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
        "--config",
        type=Path,
        help="Optional TOML configuration file with semantic rules.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Execute the organization plan. Without this flag, only print the plan.",
    )
    parser.add_argument(
        "--inspect-content",
        action="store_true",
        help=(
            "Inspect supported document content when building the plan. "
            "Disabled by default."
        ),
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable high-level application logging.",
    )


def _normalize_argv(argv: Sequence[str] | None) -> list[str]:
    """Return argv with the default command inserted for legacy invocations."""
    args = list(sys.argv[1:] if argv is None else argv)

    if args and args[0] in {"-h", "--help"}:
        return args

    if args and args[0] == "plan":
        return args

    return ["plan", *args]


def collect_sources(
    source_root: Path | None,
    explicit_sources: Sequence[Path],
) -> list[Path]:
    """Collect source files from explicit arguments or a source directory."""
    if source_root is not None and explicit_sources:
        raise SourceSelectionError("pass either --from or source files, not both")

    if source_root is None and not explicit_sources:
        raise SourceSelectionError("pass at least one source file or use --from")

    if source_root is not None:
        if not source_root.exists():
            raise SourceSelectionError(
                f"source directory does not exist: {source_root}"
            )

        if not source_root.is_dir():
            raise SourceSelectionError(f"source path is not a directory: {source_root}")

        return list_source_files(source_root)

    return list(explicit_sources)


def semantic_rules_from_config(
    config: OrganizerConfig | None,
) -> tuple[SemanticFolderRule, ...] | None:
    """Return semantic rules from loaded configuration."""
    if config is None:
        return None

    return tuple((rule.folder, rule.keywords) for rule in config.semantic_rules)


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
    args = parser.parse_args(_normalize_argv(argv))
    configure_logging(verbose=args.verbose)

    logger.info(
        "event=cli_started inspect_content=%s apply=%s",
        args.inspect_content,
        args.apply,
    )

    try:
        sources = collect_sources(args.source_root, args.sources)
        logger.info("event=sources_collected count=%s", len(sources))

        config = load_config(args.config) if args.config is not None else None
        if config is not None:
            logger.info(
                "event=config_loaded semantic_rules=%s", len(config.semantic_rules)
            )
    except (OSError, ConfigError, SourceSelectionError) as error:
        parser.error(str(error))

    semantic_rules = semantic_rules_from_config(config)

    if args.inspect_content:
        plan = build_organization_plan_inspecting_content(
            sources,
            args.target,
            semantic_rules=semantic_rules,
        )
    else:
        plan = build_organization_plan(
            sources,
            args.target,
            semantic_rules=semantic_rules,
        )

    logger.info(
        "event=plan_built count=%s inspect_content=%s", len(plan), args.inspect_content
    )

    conflicts = find_destination_conflicts(plan)

    if conflicts:
        logger.warning("event=destination_conflicts count=%s", len(conflicts))
        parser.error(format_destination_conflicts(conflicts))

    if args.apply:
        try:
            execute_plan(plan)
        except (
            DestinationExistsError,
            SourceMissingError,
            DestinationConflictError,
        ) as error:
            logger.error("event=plan_apply_failed error_type=%s", type(error).__name__)
            parser.error(str(error))

        logger.info("event=plan_applied count=%s", len(plan))
        return

    for move in plan:
        print(format_planned_move(move))
