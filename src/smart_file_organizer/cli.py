"""Command line interface for smart-file-organizer."""

import argparse
import logging
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Never

from smart_file_organizer import __version__
from smart_file_organizer.app_logging import configure_logging
from smart_file_organizer.config import (
    DEFAULT_FALLBACK_FOLDER,
    OrganizerConfig,
    load_config,
)
from smart_file_organizer.content_planning import (
    build_organization_plan_inspecting_content,
)
from smart_file_organizer.core import (
    PlannedMove,
    SemanticRuleDefinition,
    build_organization_plan,
    execute_plan,
    find_destination_conflicts,
    format_execution_summary,
    list_source_files,
    resolve_destination_conflicts,
)
from smart_file_organizer.errors import (
    ConfigError,
    DestinationConflictError,
    DestinationExistsError,
    DestinationParentError,
    InvalidSourceError,
    ManifestWriteError,
    SourceMissingError,
    SourceSelectionError,
    UnsafePathError,
)
from smart_file_organizer.path_validation import (
    validate_plan_destinations,
    validate_scan_source_root,
    validate_scan_target,
    validate_source_files,
)
from smart_file_organizer.plan_output import render_plan_preview


logger = logging.getLogger(__name__)


class CliArgumentParser(argparse.ArgumentParser):
    """Argument parser with concise, stable CLI errors."""

    def error(self, message: str) -> Never:
        """Exit with one concise parser error and no usage dump."""
        self.exit(2, f"{self.prog}: error: {message}\n")


def build_parser() -> argparse.ArgumentParser:
    """Build the command line argument parser."""
    parser = CliArgumentParser(
        prog="smart-file-organizer",
        description="Preview or apply deterministic file organization plans.",
        epilog=(
            "Canonical usage: smart-file-organizer plan [options] [sources]. "
            "Direct planning options without the 'plan' command remain "
            "available as compatibility syntax."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="command")

    plan_parser = subparsers.add_parser(
        "plan",
        help="Preview or apply a file organization plan.",
        description=(
            "Preview a file organization plan without moving files by default. "
            "Pass --apply only after reviewing the plan."
        ),
    )
    _add_plan_arguments(plan_parser)

    return parser


def _add_plan_arguments(parser: argparse.ArgumentParser) -> None:
    """Add file planning arguments to a parser."""
    parser.add_argument(
        "sources",
        nargs="*",
        type=Path,
        help=(
            "Regular files or symlinks to regular files. "
            "Broken and directory symlinks are rejected."
        ),
    )
    parser.add_argument(
        "--from",
        dest="source_root",
        type=Path,
        help=("Real source directory to scan. Directory symlinks are rejected."),
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help=(
            "Scan nested directories without following directory symlinks. "
            "Hidden files are included. Disabled by default."
        ),
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
        help=(
            "Optional TOML configuration with semantic rules, "
            "precedence, and built-in rule disabling."
        ),
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
            "Inspect .txt content and the first three PDF pages. "
            "Reader failures and PDFs without text fall back to filename "
            "classification. OCR is not performed."
        ),
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable high-level application logging.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format for plan preview. Defaults to text.",
    )
    parser.add_argument(
        "--explain",
        action="store_true",
        help=(
            "Include the classification source, rule, match target, "
            "and reason in dry-run previews."
        ),
    )
    parser.add_argument(
        "--conflict-strategy",
        choices=("fail", "rename"),
        default="fail",
        help=(
            "How to handle destination conflicts. "
            "Defaults to fail, which stops on duplicate destinations."
        ),
    )


def _normalize_argv(argv: Sequence[str] | None) -> list[str]:
    """Return argv with the default command inserted for legacy invocations."""
    args = list(sys.argv[1:] if argv is None else argv)

    if args and args[0] in {
        "-h",
        "--help",
        "--version",
    }:
        return args

    if args and args[0] == "plan":
        return args

    return ["plan", *args]


def collect_sources(
    source_root: Path | None,
    explicit_sources: Sequence[Path],
    *,
    recursive: bool = False,
) -> list[Path]:
    """Collect source files from explicit arguments or a source directory."""
    if source_root is not None and explicit_sources:
        raise SourceSelectionError("pass either --from or source files, not both")

    if source_root is None and not explicit_sources:
        raise SourceSelectionError("pass at least one source file or use --from")

    if recursive and source_root is None:
        raise SourceSelectionError("--recursive requires --from")

    if source_root is not None:
        validate_scan_source_root(source_root)

        if not source_root.exists():
            raise SourceSelectionError(
                f"source directory does not exist: {source_root}"
            )

        if not source_root.is_dir():
            raise SourceSelectionError(f"source path is not a directory: {source_root}")

        return list_source_files(source_root, recursive=recursive)

    validate_source_files(explicit_sources)
    return list(explicit_sources)


def semantic_rules_from_config(
    config: OrganizerConfig | None,
) -> tuple[SemanticRuleDefinition, ...] | None:
    """Return semantic rules from loaded configuration."""
    if config is None:
        return None

    return tuple(
        SemanticRuleDefinition(
            folder=rule.folder,
            keywords=rule.keywords,
            patterns=rule.patterns,
            rule_id=rule.rule_id,
        )
        for rule in config.semantic_rules
    )


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
        sources = collect_sources(
            args.source_root,
            args.sources,
            recursive=args.recursive,
        )
        if args.source_root is not None:
            validate_scan_target(
                args.source_root, args.target, recursive=args.recursive
            )
        logger.info("event=sources_collected count=%s", len(sources))

        config = load_config(args.config) if args.config is not None else None
        if config is not None:
            logger.info(
                "event=config_loaded semantic_rules=%s", len(config.semantic_rules)
            )
    except (
        OSError,
        ConfigError,
        InvalidSourceError,
        SourceSelectionError,
        UnsafePathError,
    ) as error:
        parser.error(str(error))

    semantic_rules = semantic_rules_from_config(config)
    fallback_folder = (
        config.fallback_folder if config is not None else DEFAULT_FALLBACK_FOLDER
    )
    rule_precedence = (
        config.semantic_rule_precedence if config is not None else "builtins-first"
    )
    disabled_builtin_rules = config.disabled_builtin_rules if config is not None else ()

    uses_default_rule_policy = (
        rule_precedence == "builtins-first" and not disabled_builtin_rules
    )

    try:
        if args.inspect_content:
            if uses_default_rule_policy:
                plan = build_organization_plan_inspecting_content(
                    sources,
                    args.target,
                    semantic_rules=semantic_rules,
                    fallback_folder=fallback_folder,
                    verbose=args.verbose,
                )
            else:
                plan = build_organization_plan_inspecting_content(
                    sources,
                    args.target,
                    semantic_rules=semantic_rules,
                    fallback_folder=fallback_folder,
                    rule_precedence=rule_precedence,
                    disabled_builtin_rules=disabled_builtin_rules,
                    verbose=args.verbose,
                )
        elif uses_default_rule_policy:
            plan = build_organization_plan(
                sources,
                args.target,
                semantic_rules=semantic_rules,
                fallback_folder=fallback_folder,
            )
        else:
            plan = build_organization_plan(
                sources,
                args.target,
                semantic_rules=semantic_rules,
                fallback_folder=fallback_folder,
                rule_precedence=rule_precedence,
                disabled_builtin_rules=disabled_builtin_rules,
            )
    except (InvalidSourceError, UnsafePathError) as error:
        parser.error(str(error))

    logger.info(
        "event=plan_built count=%s inspect_content=%s", len(plan), args.inspect_content
    )

    if not plan and not args.apply and args.format == "text":
        sys.stdout.write("No files found.\n")
        logger.info("event=plan_empty")
        return

    conflicts = find_destination_conflicts(plan)

    if args.conflict_strategy == "rename":
        if conflicts:
            logger.info(
                "event=destination_conflicts_resolving count=%s", len(conflicts)
            )
            try:
                plan = resolve_destination_conflicts(plan)
            except DestinationConflictError as error:
                parser.error(str(error))
    elif conflicts:
        logger.info("event=destination_conflicts count=%s", len(conflicts))
        parser.error(format_destination_conflicts(conflicts))

    try:
        validate_plan_destinations(plan, args.target)
    except UnsafePathError as error:
        parser.error(str(error))

    if args.apply:
        try:
            result = execute_plan(plan, args.target)
        except (
            DestinationExistsError,
            DestinationParentError,
            SourceMissingError,
            DestinationConflictError,
            InvalidSourceError,
            UnsafePathError,
        ) as error:
            logger.info("event=plan_apply_failed error_type=%s", type(error).__name__)
            parser.error(str(error))
        except ManifestWriteError as error:
            logger.info("event=manifest_write_failed")
            parser.exit(1, f"{parser.prog}: error: {error}\n")

        summary = format_execution_summary(result)

        if result.failed_count:
            sys.stderr.write(summary)
            logger.info(
                "event=plan_apply_partial completed=%s failed=%s unattempted=%s",
                result.completed_count,
                result.failed_count,
                result.unattempted_count,
            )
            raise SystemExit(1)

        sys.stdout.write(summary)
        logger.info("event=plan_applied count=%s", result.completed_count)
        return

    sys.stdout.write(
        render_plan_preview(
            plan,
            output_format=args.format,
            explain=args.explain,
        )
    )
