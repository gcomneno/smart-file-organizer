"""Command line interface for smart-file-organizer."""

import argparse
import logging
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Never

from smart_file_organizer import __version__
from smart_file_organizer.app_logging import configure_logging
from smart_file_organizer.application import (
    OrganizationPlanConflictError,
    PlanOrganizationRequest,
    apply_organization,
    collect_sources as _collect_sources,
    list_manifests,
    load_manifest,
    plan_recovery,
    plan_organization,
    verify_manifest,
)
from smart_file_organizer.core import PlannedMove, format_execution_summary
from smart_file_organizer.errors import (
    ConfigError,
    DestinationConflictError,
    DestinationExistsError,
    DestinationParentError,
    InvalidSourceError,
    ManifestWriteError,
    ManifestError,
    SourceMissingError,
    SourceSelectionError,
    UnsafePathError,
)
from smart_file_organizer.manifest_output import (
    render_manifest,
    render_recovery_plan,
    render_references,
    render_verification,
)
from smart_file_organizer.plan_output import render_plan_preview
from smart_file_organizer.models import TaxonomyProfileName


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

    manifest_parser = subparsers.add_parser(
        "manifest", help="Inspect historical apply manifests."
    )
    manifest_commands = manifest_parser.add_subparsers(dest="manifest_command")
    for name, help_text in (
        ("show", "Show one validated manifest."),
        ("verify", "Reconcile one manifest with current filesystem state."),
    ):
        command = manifest_commands.add_parser(name, help=help_text)
        command.add_argument("manifest", type=Path, metavar="MANIFEST")
        command.add_argument("--json", action="store_true", help="Render JSON output.")
    list_parser = manifest_commands.add_parser("list", help="List manifest candidates.")
    list_parser.add_argument("--target", type=Path, required=True, metavar="TARGET")
    list_parser.add_argument("--json", action="store_true", help="Render JSON output.")

    recover_parser = subparsers.add_parser(
        "recover", help="Build non-mutating manual recovery plans."
    )
    recover_commands = recover_parser.add_subparsers(dest="recover_command")
    recovery_plan_parser = recover_commands.add_parser(
        "plan", help="Plan safe manual reverse moves without executing them."
    )
    recovery_plan_parser.add_argument("manifest", type=Path, metavar="MANIFEST")
    recovery_plan_parser.add_argument(
        "--json", action="store_true", help="Render JSON output."
    )

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
        "--profile",
        choices=tuple(profile.value for profile in TaxonomyProfileName),
        help="Built-in taxonomy profile. Overrides a configured profile.",
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

    if args and args[0] in {"plan", "manifest", "recover"}:
        return args

    return ["plan", *args]


def collect_sources(
    source_root: Path | None,
    explicit_sources: Sequence[Path],
    *,
    recursive: bool = False,
) -> list[Path]:
    """Compatibility wrapper for application source collection."""
    return _collect_sources(source_root, explicit_sources, recursive=recursive)


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
    configure_logging(verbose=getattr(args, "verbose", False))

    if args.command == "manifest":
        _run_manifest_command(parser, args)
        return
    if args.command == "recover":
        _run_recovery_command(parser, args)
        return

    logger.info(
        "event=cli_started inspect_content=%s apply=%s",
        args.inspect_content,
        args.apply,
    )

    request = PlanOrganizationRequest(
        explicit_sources=tuple(args.sources),
        source_root=args.source_root,
        recursive=args.recursive,
        target_root=args.target,
        config_path=args.config,
        inspect_content=args.inspect_content,
        conflict_strategy=args.conflict_strategy,
        profile=(
            TaxonomyProfileName(args.profile) if args.profile is not None else None
        ),
    )

    try:
        plan = plan_organization(
            request,
            verbose=args.verbose,
            _source_collector=collect_sources,
        )
    except OrganizationPlanConflictError as error:
        logger.info("event=destination_conflicts count=%s", len(error.conflicts))
        parser.error(format_destination_conflicts(error.conflicts))
    except (
        OSError,
        ConfigError,
        DestinationConflictError,
        InvalidSourceError,
        SourceSelectionError,
        UnsafePathError,
    ) as error:
        parser.error(str(error))

    logger.info(
        "event=plan_built count=%s inspect_content=%s",
        len(plan.moves),
        args.inspect_content,
    )

    if not plan.moves and not args.apply and args.format == "text":
        sys.stdout.write("No files found.\n")
        logger.info("event=plan_empty")
        return

    if args.apply:
        try:
            result = apply_organization(plan)
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
            plan.moves,
            output_format=args.format,
            explain=args.explain,
        )
    )


def _run_manifest_command(
    parser: argparse.ArgumentParser, args: argparse.Namespace
) -> None:
    """Dispatch manifest CLI adapters through application services only."""
    if args.manifest_command is None:
        parser.error("manifest requires show, list, or verify")
    try:
        if args.manifest_command == "show":
            sys.stdout.write(
                render_manifest(load_manifest(args.manifest), json_output=args.json)
            )
        elif args.manifest_command == "list":
            sys.stdout.write(
                render_references(list_manifests(args.target), json_output=args.json)
            )
        else:
            sys.stdout.write(
                render_verification(
                    verify_manifest(args.manifest), json_output=args.json
                )
            )
    except ManifestError as error:
        parser.error(str(error))


def _run_recovery_command(
    parser: argparse.ArgumentParser, args: argparse.Namespace
) -> None:
    """Dispatch the non-mutating recovery-plan CLI adapter."""
    if args.recover_command is None:
        parser.error("recover requires plan")
    try:
        sys.stdout.write(
            render_recovery_plan(plan_recovery(args.manifest), json_output=args.json)
        )
    except ManifestError as error:
        parser.error(str(error))
