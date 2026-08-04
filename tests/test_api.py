"""Contract tests for the provisional supported Python API."""

import ast
import os
import re
import subprocess
import sys
from dataclasses import FrozenInstanceError, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import cast

import pytest

import smart_file_organizer.api as api
import smart_file_organizer.application as application
from smart_file_organizer import __all__ as package_all
from smart_file_organizer.models import FileCategory


EXPECTED_EXPORTS = [
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

FORBIDDEN_EXPORTS = {
    "_SourceCollector",
    "_EXTENSION_CATEGORIES",
    "_SEMANTIC_FOLDER_RULES",
    "_match_semantic_folder",
    "_normalize_search_text",
    "_normalize_semantic_rules",
    "_path_search_text",
    "OrganizerConfig",
    "SemanticFolderRule",
    "SemanticRule",
    "SemanticRuleDefinition",
    "RulePrecedence",
    "build_organization_plan",
    "collect_sources",
    "execute_plan",
    "load_config",
    "MANIFEST_SCHEMA_VERSION",
    "_MANIFEST_DIRECTORY",
    "DEFAULT_FALLBACK_FOLDER",
    "format_execution_summary",
    "parse_config",
    "render_plan",
    "validate_plan_destinations",
    "__version__",
    "get_version",
}


def _request(*sources: Path, target_root: Path) -> api.PlanOrganizationRequest:
    return api.PlanOrganizationRequest(
        explicit_sources=sources,
        source_root=None,
        recursive=False,
        target_root=target_root,
        config_path=None,
        inspect_content=False,
        conflict_strategy="fail",
    )


def test_api_all_is_the_exact_ordered_public_contract() -> None:
    assert api.__all__ == EXPECTED_EXPORTS
    assert all(hasattr(api, name) for name in api.__all__)
    assert all(not name.startswith("_") for name in api.__all__)
    assert not FORBIDDEN_EXPORTS & set(api.__all__)


def test_package_root_remains_version_only() -> None:
    assert package_all == ["__version__", "get_version"]


def test_package_declares_inline_typing_support() -> None:
    assert Path(api.__file__).with_name("py.typed").is_file()


def test_public_functions_are_the_application_functions() -> None:
    assert api.plan_organization is application.plan_organization
    assert api.apply_organization is application.apply_organization


def test_importing_api_does_not_import_cli(tmp_path: Path) -> None:
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment["PYTHONNOUSERSITE"] = "1"

    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys\n"
                "import smart_file_organizer.api as api\n"
                "assert api.__all__\n"
                "assert 'smart_file_organizer.cli' not in sys.modules\n"
            ),
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr


def test_api_imports_only_the_public_facade_dependencies() -> None:
    source = Path(api.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    imported_names = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    forbidden_modules = {
        "argparse",
        "smart_file_organizer.cli",
        "smart_file_organizer.plan_output",
        "smart_file_organizer.classification",
        "smart_file_organizer.semantic_rules",
        "smart_file_organizer.planning",
        "smart_file_organizer.execution",
    }
    forbidden_names = {
        "_EXTENSION_CATEGORIES",
        "_SEMANTIC_FOLDER_RULES",
        "_match_semantic_folder",
        "_normalize_search_text",
        "_normalize_semantic_rules",
        "_path_search_text",
    }

    assert not forbidden_modules & (imported_modules | imported_names)
    assert not forbidden_names & {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }


def test_request_and_plan_are_frozen_and_copy_caller_collections() -> None:
    sources = [Path("source.txt")]
    request = api.PlanOrganizationRequest(
        explicit_sources=cast(tuple[Path, ...], sources),
        source_root=None,
        recursive=False,
        target_root=Path("target"),
        config_path=None,
        inspect_content=False,
        conflict_strategy="fail",
    )
    moves = [
        api.PlannedMove(
            source=Path("source.txt"),
            destination=Path("target/documents/inbox/source.txt"),
            category=api.FileCategory.DOCUMENTS,
        )
    ]
    plan = api.OrganizationPlan(
        Path("target"),
        cast(tuple[api.PlannedMove, ...], moves),
    )
    sources.append(Path("later.txt"))
    moves.clear()

    assert request.explicit_sources == (Path("source.txt"),)
    assert len(plan.moves) == 1
    with pytest.raises(FrozenInstanceError):
        setattr(request, "target_root", Path("other"))
    with pytest.raises(FrozenInstanceError):
        setattr(plan, "moves", ())


def test_public_result_values_are_structured_and_immutable() -> None:
    decision = api.ClassificationDecision(
        folder=Path("documents/inbox"),
        source=api.ClassificationSource.FALLBACK,
        reason="test",
    )
    move = api.PlannedMove(
        source=Path("source.txt"),
        destination=Path("target/documents/inbox/source.txt"),
        category=api.FileCategory.DOCUMENTS,
        classification=decision,
    )
    record = api.MoveExecutionRecord(
        original_path=move.source,
        final_path=move.destination,
        category=FileCategory.DOCUMENTS,
        status=api.MoveStatus.COMPLETED,
        timestamp=datetime.now(timezone.utc),
    )
    records = [record]
    result = api.ExecutionResult(
        manifest_path=Path("target/manifest.json"),
        started_at=record.timestamp,
        finished_at=record.timestamp,
        moves=cast(tuple[api.MoveExecutionRecord, ...], records),
    )
    records.clear()

    assert result.moves == (record,)

    for value in (decision, move, record, result):
        assert is_dataclass(value)
        with pytest.raises(FrozenInstanceError):
            setattr(value, next(iter(value.__dataclass_fields__)), None)


def test_public_api_plans_in_a_temporary_directory(tmp_path: Path) -> None:
    source = tmp_path / "notes.txt"
    source.write_text("notes", encoding="utf-8")

    plan = api.plan_organization(_request(source, target_root=tmp_path / "target"))

    assert plan.moves[0].source == source
    assert plan.moves[0].classification is not None
    assert plan.moves[0].destination == tmp_path / "target/documents/inbox/notes.txt"


def test_applying_a_reviewed_hand_built_plan_does_not_replan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.txt"
    target = tmp_path / "target"
    destination = target / "reviewed" / "source.txt"
    source.write_text("source", encoding="utf-8")
    plan = api.OrganizationPlan(
        target,
        (
            api.PlannedMove(
                source=source,
                destination=destination,
                category=api.FileCategory.DOCUMENTS,
            ),
        ),
    )

    monkeypatch.setattr(
        application,
        "build_organization_plan",
        lambda *_args, **_kwargs: pytest.fail("apply must not plan"),
    )
    result = api.apply_organization(plan)

    assert result.successful
    assert destination.read_text(encoding="utf-8") == "source"


def test_structured_public_exceptions_propagate_unchanged(tmp_path: Path) -> None:
    with pytest.raises(api.SourceSelectionError) as selection_error:
        api.plan_organization(_request(target_root=tmp_path / "target"))
    assert type(selection_error.value) is api.SourceSelectionError

    source = tmp_path / "same.txt"
    source.write_text("same", encoding="utf-8")
    with pytest.raises(api.OrganizationPlanConflictError) as conflict_error:
        api.plan_organization(_request(source, source, target_root=tmp_path / "target"))
    assert type(conflict_error.value) is api.OrganizationPlanConflictError
    assert conflict_error.value.conflicts
    with pytest.raises(TypeError):
        cast(dict[Path, tuple[api.PlannedMove, ...]], conflict_error.value.conflicts)[
            Path("another-destination")
        ] = ()


def test_apply_exposes_destination_conflicts_without_mutation(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    target = tmp_path / "target"
    destination = target / "documents" / "inbox" / "same.txt"

    first.write_text("first", encoding="utf-8")
    second.write_text("second", encoding="utf-8")

    plan = api.OrganizationPlan(
        target,
        (
            api.PlannedMove(
                source=first,
                destination=destination,
                category=api.FileCategory.DOCUMENTS,
            ),
            api.PlannedMove(
                source=second,
                destination=destination,
                category=api.FileCategory.DOCUMENTS,
            ),
        ),
    )

    with pytest.raises(api.DestinationConflictError) as error:
        api.apply_organization(plan)

    assert type(error.value) is api.DestinationConflictError
    assert first.read_text(encoding="utf-8") == "first"
    assert second.read_text(encoding="utf-8") == "second"
    assert not target.exists()


def test_readme_marked_python_api_example_executes() -> None:
    readme = (Path(__file__).resolve().parents[1] / "README.md").read_text(
        encoding="utf-8"
    )
    match = re.search(
        r"<!-- python-api-example:start -->\s*~~~python\n(.*?)~~~\n"
        r"<!-- python-api-example:end -->",
        readme,
        flags=re.DOTALL,
    )

    assert match is not None
    exec(compile(match.group(1), "README Python API example", "exec"), {})


def test_core_no_longer_exports_or_has_private_helpers() -> None:
    import smart_file_organizer.core as core

    removed = {
        "_EXTENSION_CATEGORIES",
        "_SEMANTIC_FOLDER_RULES",
        "_match_semantic_folder",
        "_normalize_search_text",
        "_normalize_semantic_rules",
        "_path_search_text",
    }
    assert all(not name.startswith("_") for name in core.__all__)
    assert not removed & set(core.__all__)
    assert all(not hasattr(core, name) for name in removed)


def test_non_private_legacy_core_imports_continue_to_work() -> None:
    from smart_file_organizer.core import (  # noqa: PLC0415
        PlannedMove,
        build_organization_plan,
        classify_path,
        execute_plan,
        infer_destination_folder,
    )

    assert PlannedMove is api.PlannedMove
    assert callable(build_organization_plan)
    assert callable(classify_path)
    assert callable(execute_plan)
    assert callable(infer_destination_folder)
