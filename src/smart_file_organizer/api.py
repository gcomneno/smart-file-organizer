"""Provisional supported Python API for planning and applying organization."""

from smart_file_organizer.application import (
    OrganizationPlan,
    OrganizationPlanConflictError,
    PlanOrganizationRequest,
    apply_organization,
    plan_organization,
)
from smart_file_organizer.errors import (
    BrokenSourceSymlinkError,
    ConfigError,
    DestinationConflictError,
    DestinationExistsError,
    DestinationParentError,
    InvalidSourceError,
    ManifestWriteError,
    SourceMissingError,
    SourceSelectionError,
    UnsafePathError,
    UnsupportedSourceSymlinkError,
)
from smart_file_organizer.models import (
    ClassificationDecision,
    ClassificationSource,
    ConflictStrategy,
    ExecutionResult,
    FileCategory,
    MoveExecutionRecord,
    MoveStatus,
    PlannedMove,
)


__all__ = [
    "BrokenSourceSymlinkError",
    "ClassificationDecision",
    "ClassificationSource",
    "ConfigError",
    "ConflictStrategy",
    "DestinationConflictError",
    "DestinationExistsError",
    "DestinationParentError",
    "ExecutionResult",
    "FileCategory",
    "InvalidSourceError",
    "ManifestWriteError",
    "MoveExecutionRecord",
    "MoveStatus",
    "OrganizationPlan",
    "OrganizationPlanConflictError",
    "PlanOrganizationRequest",
    "PlannedMove",
    "SourceMissingError",
    "SourceSelectionError",
    "UnsafePathError",
    "UnsupportedSourceSymlinkError",
    "apply_organization",
    "plan_organization",
]
