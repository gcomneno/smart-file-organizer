"""Compatibility exports for core file organization logic."""

from smart_file_organizer.classification import _EXTENSION_CATEGORIES, classify_path
from smart_file_organizer.models import FileCategory, PlannedMove, SemanticFolderRule
from smart_file_organizer.planning import (
    build_organization_plan,
    build_organization_plan_with_document_texts,
    execute_plan,
    find_destination_conflicts,
    list_source_files,
    plan_file,
    plan_file_with_document_text,
)
from smart_file_organizer.semantic_rules import (
    _SEMANTIC_FOLDER_RULES,
    _match_semantic_folder,
    _normalize_search_text,
    _normalize_semantic_rules,
    _path_search_text,
    infer_destination_folder,
)

__all__ = [
    "FileCategory",
    "PlannedMove",
    "SemanticFolderRule",
    "_EXTENSION_CATEGORIES",
    "_SEMANTIC_FOLDER_RULES",
    "_match_semantic_folder",
    "_normalize_search_text",
    "_normalize_semantic_rules",
    "_path_search_text",
    "build_organization_plan",
    "build_organization_plan_with_document_texts",
    "classify_path",
    "execute_plan",
    "find_destination_conflicts",
    "infer_destination_folder",
    "list_source_files",
    "plan_file",
    "plan_file_with_document_text",
]
