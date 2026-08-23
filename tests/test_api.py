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
    "ApplyManifest",
    "BrokenSourceSymlinkError",
    "ClassificationCandidate",
    "ClassificationDecision",
    "ClassificationEvidence",
    "ClassificationOutcome",
    "ClassificationSource",
    "ConfigError",
    "ConflictStrategy",
    "CurrentIdentityObservation",
    "DestinationConflictError",
    "DestinationExistsError",
    "DestinationParentError",
    "ExecutionResult",
    "EvidenceSource",
    "EvidenceStrength",
    "FileCategory",
    "IdentityObservationStatus",
    "IdentityVerificationReason",
    "IdentityVerificationState",
    "InvalidSourceError",
    "ManifestAccessError",
    "ManifestCounts",
    "ManifestError",
    "ManifestFormatError",
    "ManifestMove",
    "ManifestPathError",
    "ManifestReference",
    "ManifestReferenceStatus",
    "ManifestVerification",
    "ManifestWriteError",
    "MatchMechanism",
    "MoveExecutionRecord",
    "MoveIdentityVerification",
    "MoveReconciliation",
    "MoveStatus",
    "OrganizationPlan",
    "OrganizationPlanConflictError",
    "PlanOrganizationRequest",
    "PlannedMove",
    "ReconciliationState",
    "RecoveryDisposition",
    "RecoveryPlan",
    "RecoveryPlanItem",
    "SourceMissingError",
    "SourceSelectionError",
    "TaxonomyProfileName",
    "UnsafePathError",
    "UnsupportedSourceSymlinkError",
    "apply_organization",
    "list_manifests",
    "load_manifest",
    "plan_recovery",
    "plan_organization",
    "verify_manifest",
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
    "DocumentInspectionResult",
    "DocumentInspectionStatus",
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
    assert not hasattr(api, "DocumentInspectionResult")
    assert not hasattr(api, "DocumentInspectionStatus")


def test_package_root_remains_version_only() -> None:
    assert package_all == ["__version__", "get_version"]


def test_package_declares_inline_typing_support() -> None:
    assert Path(api.__file__).with_name("py.typed").is_file()


def test_public_functions_are_the_application_functions() -> None:
    assert api.plan_organization is application.plan_organization
    assert api.apply_organization is application.apply_organization
    assert api.load_manifest is application.load_manifest
    assert api.list_manifests is application.list_manifests
    assert api.verify_manifest is application.verify_manifest
    assert api.plan_recovery is application.plan_recovery


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


def test_manifest_models_are_frozen_slotted_and_copy_collections() -> None:
    timestamp = datetime.now(timezone.utc)
    observation = api.CurrentIdentityObservation(
        status=api.IdentityObservationStatus.FINGERPRINTED,
        algorithm="sha256",
        digest="0" * 64,
        size_bytes=0,
        observed_at=timestamp,
    )
    identity = api.MoveIdentityVerification(
        state=api.IdentityVerificationState.IDENTITY_MATCH,
        reason=api.IdentityVerificationReason.IDENTITY_VERIFIED,
        current=observation,
    )
    move = api.ManifestMove(
        original_path=Path("/source.txt"),
        final_path=Path("/target/documents/source.txt"),
        category=api.FileCategory.DOCUMENTS,
        status=api.MoveStatus.COMPLETED,
        timestamp=timestamp,
    )
    moves = [move]
    manifest = api.ApplyManifest(
        path=Path("/target/.smart-file-organizer/manifests/apply.json"),
        schema_version=1,
        state="completed",
        target_root=Path("/target"),
        started_at=timestamp,
        updated_at=timestamp,
        finished_at=timestamp,
        counts=api.ManifestCounts(1, 0, 0, 0),
        moves=cast(tuple[api.ManifestMove, ...], moves),
    )
    moves.clear()

    assert manifest.moves == (move,)
    assert hasattr(manifest, "__slots__")
    assert hasattr(identity, "__slots__")
    reconciliation = api.MoveReconciliation(
        move,
        api.ReconciliationState.CONSISTENT,
        source_exists=False,
        destination_exists=True,
    )
    assert reconciliation.identity.state is (
        api.IdentityVerificationState.IDENTITY_UNVERIFIABLE
    )
    assert reconciliation.identity.reason is (
        api.IdentityVerificationReason.HISTORICAL_IDENTITY_ABSENT
    )
    with pytest.raises(FrozenInstanceError):
        setattr(manifest, "state", "failed")
    with pytest.raises(FrozenInstanceError):
        setattr(identity, "state", api.IdentityVerificationState.IDENTITY_MISMATCH)


def test_public_evidence_models_are_slotted_frozen_and_copy_collections() -> None:
    evidence = api.ClassificationEvidence(
        rule_id="local:demo",
        source=api.EvidenceSource.FILENAME,
        mechanism=api.MatchMechanism.TOKEN,
        strength=api.EvidenceStrength.STRONG,
        reason="configured keyword matched filename",
        matched_value="demo",
    )
    items = [evidence]
    candidate = api.ClassificationCandidate(
        folder=Path("documents/demo"),
        rule_id="local:demo",
        rule_origin=api.ClassificationSource.CONFIGURED_RULE,
        aggregate_strength=api.EvidenceStrength.STRONG,
        evidence=cast(tuple[api.ClassificationEvidence, ...], items),
    )
    items.clear()
    assert candidate.evidence == (evidence,)
    assert hasattr(candidate, "__slots__")
    with pytest.raises(FrozenInstanceError):
        setattr(candidate, "rule_id", "other")


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
