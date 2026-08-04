"""Application orchestration for organization planning and execution."""

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Protocol

from smart_file_organizer.config import (
    DEFAULT_FALLBACK_FOLDER,
    OrganizerConfig,
    load_config,
)
from smart_file_organizer.content_planning import (
    build_organization_plan_inspecting_content,
)
from smart_file_organizer.errors import DestinationConflictError, SourceSelectionError
from smart_file_organizer.execution import execute_plan
from smart_file_organizer.models import (
    ConflictStrategy,
    ExecutionResult,
    PlannedMove,
    SemanticRuleDefinition,
)
from smart_file_organizer.path_validation import (
    validate_plan_destinations,
    validate_scan_source_root,
    validate_scan_target,
    validate_source_files,
)
from smart_file_organizer.planning import (
    build_organization_plan,
    find_destination_conflicts,
    list_source_files,
    resolve_destination_conflicts,
)


logger = logging.getLogger(__name__)


class _SourceCollector(Protocol):
    """Callable boundary retained for transitional CLI compatibility."""

    def __call__(
        self,
        source_root: Path | None,
        explicit_sources: Sequence[Path],
        *,
        recursive: bool = False,
    ) -> list[Path]:
        """Collect and validate the selected sources."""


@dataclass(frozen=True, slots=True)
class PlanOrganizationRequest:
    """Inputs required to build one organization plan."""

    explicit_sources: tuple[Path, ...]
    source_root: Path | None
    recursive: bool
    target_root: Path
    config_path: Path | None
    inspect_content: bool
    conflict_strategy: ConflictStrategy

    def __post_init__(self) -> None:
        """Detach the request from a caller-owned source collection."""
        object.__setattr__(self, "explicit_sources", tuple(self.explicit_sources))


@dataclass(frozen=True, slots=True)
class OrganizationPlan:
    """An immutable, ordered plan that can be previewed or applied."""

    target_root: Path
    moves: tuple[PlannedMove, ...]

    def __post_init__(self) -> None:
        """Detach the plan from a caller-owned move collection."""
        object.__setattr__(self, "moves", tuple(self.moves))


class OrganizationPlanConflictError(DestinationConflictError):
    """A planning conflict with immutable move groups for adapter formatting."""

    conflicts: Mapping[Path, tuple[PlannedMove, ...]]

    def __init__(self, conflicts: Mapping[Path, Sequence[PlannedMove]]) -> None:
        ordered_conflicts = {
            destination: tuple(moves)
            for destination, moves in sorted(
                conflicts.items(), key=lambda item: str(item[0])
            )
        }
        self.conflicts = MappingProxyType(ordered_conflicts)
        super().__init__("destination conflicts detected")


def collect_sources(
    source_root: Path | None,
    explicit_sources: Sequence[Path],
    *,
    recursive: bool = False,
) -> list[Path]:
    """Collect validated source files from arguments or a directory scan."""
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


def _semantic_rules_from_config(
    config: OrganizerConfig | None,
) -> tuple[SemanticRuleDefinition, ...] | None:
    """Translate configuration rules for the existing planning seam."""
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


def _build_moves(
    request: PlanOrganizationRequest,
    sources: Sequence[Path],
    config: OrganizerConfig | None,
    *,
    verbose: bool,
) -> list[PlannedMove]:
    """Dispatch to the established filename or content-aware planner."""
    semantic_rules = _semantic_rules_from_config(config)
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

    if request.inspect_content:
        if uses_default_rule_policy:
            return build_organization_plan_inspecting_content(
                sources,
                request.target_root,
                semantic_rules=semantic_rules,
                fallback_folder=fallback_folder,
                verbose=verbose,
            )
        return build_organization_plan_inspecting_content(
            sources,
            request.target_root,
            semantic_rules=semantic_rules,
            fallback_folder=fallback_folder,
            rule_precedence=rule_precedence,
            disabled_builtin_rules=disabled_builtin_rules,
            verbose=verbose,
        )

    if uses_default_rule_policy:
        return build_organization_plan(
            sources,
            request.target_root,
            semantic_rules=semantic_rules,
            fallback_folder=fallback_folder,
        )
    return build_organization_plan(
        sources,
        request.target_root,
        semantic_rules=semantic_rules,
        fallback_folder=fallback_folder,
        rule_precedence=rule_precedence,
        disabled_builtin_rules=disabled_builtin_rules,
    )


def plan_organization(
    request: PlanOrganizationRequest,
    *,
    verbose: bool = False,
    _source_collector: _SourceCollector | None = None,
) -> OrganizationPlan:
    """Build and validate an immutable organization plan."""
    source_collector = (
        collect_sources if _source_collector is None else _source_collector
    )
    sources = source_collector(
        request.source_root,
        request.explicit_sources,
        recursive=request.recursive,
    )
    if request.source_root is not None:
        validate_scan_target(
            request.source_root,
            request.target_root,
            recursive=request.recursive,
        )

    logger.info("event=sources_collected count=%s", len(sources))

    config = None

    if request.config_path is not None:
        config = load_config(request.config_path)
        logger.info(
            "event=config_loaded semantic_rules=%s",
            len(config.semantic_rules),
        )
    moves = _build_moves(request, sources, config, verbose=verbose)
    conflicts = find_destination_conflicts(moves)

    if request.conflict_strategy == "rename":
        if conflicts:
            logger.info(
                "event=destination_conflicts_resolving count=%s",
                len(conflicts),
            )
            moves = resolve_destination_conflicts(moves)
    elif conflicts:
        raise OrganizationPlanConflictError(conflicts)

    validate_plan_destinations(moves, request.target_root)
    return OrganizationPlan(target_root=request.target_root, moves=tuple(moves))


def apply_organization(plan: OrganizationPlan) -> ExecutionResult:
    """Apply a previously built organization plan without replanning it."""
    return execute_plan(plan.moves, plan.target_root)
