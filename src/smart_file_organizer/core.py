"""Legacy compatibility exports for historical core imports.

This module is retained for historical compatibility. The supported Python API
is :mod:`smart_file_organizer.api`; this module is not covered by that API's
stability promise. Callers should migrate to ``api.py`` for supported planning
and apply workflows.
"""

from smart_file_organizer.classification import (
    classify_path,
)
from smart_file_organizer.execution import (
    execute_plan,
    format_execution_summary,
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
    RulePrecedence,
    SemanticFolderRule,
    SemanticRuleDefinition,
)
from smart_file_organizer.planning import (
    build_organization_plan,
    build_organization_plan_with_document_texts,
    find_destination_conflicts,
    list_source_files,
    plan_file,
    plan_file_with_document_text,
    resolve_destination_conflicts,
)
from smart_file_organizer.semantic_rules import (
    infer_destination,
    infer_destination_folder,
)


__all__ = [
    "ClassificationDecision",
    "ClassificationSource",
    "ConflictStrategy",
    "ExecutionResult",
    "FileCategory",
    "MoveExecutionRecord",
    "MoveStatus",
    "PlannedMove",
    "RulePrecedence",
    "SemanticFolderRule",
    "SemanticRuleDefinition",
    "build_organization_plan",
    "build_organization_plan_with_document_texts",
    "classify_path",
    "execute_plan",
    "find_destination_conflicts",
    "format_execution_summary",
    "infer_destination",
    "infer_destination_folder",
    "list_source_files",
    "plan_file",
    "plan_file_with_document_text",
    "resolve_destination_conflicts",
]
