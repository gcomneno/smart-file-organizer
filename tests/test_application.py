import ast
import hashlib
import json
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import cast

import pytest

import smart_file_organizer.application as application
from smart_file_organizer.application import (
    OrganizationPlan,
    OrganizationPlanConflictError,
    PlanOrganizationRequest,
    RecoveryAssessment,
    apply_organization,
    assess_recovery,
    plan_organization,
    plan_recovery,
)
from smart_file_organizer.errors import DestinationExistsError, ManifestWriteError
from smart_file_organizer.manifest_models import (
    ApplyManifest,
    ManifestCounts,
    ManifestVerification,
    RecoveryPlan,
    RecoveryDisposition,
)
from smart_file_organizer.models import (
    ConflictStrategy,
    FileCategory,
    PlannedMove,
    TaxonomyProfileName,
)
from smart_file_organizer.recovery_safety import (
    RecoverySafetyClassification,
    RecoverySafetyReason,
    RecoverySafetyState,
)


def _request(
    *sources: Path,
    target_root: Path = Path("organized"),
    **overrides: object,
) -> PlanOrganizationRequest:
    remaining = dict(overrides)

    request = PlanOrganizationRequest(
        explicit_sources=cast(
            tuple[Path, ...],
            remaining.pop("explicit_sources", sources),
        ),
        source_root=cast(
            Path | None,
            remaining.pop("source_root", None),
        ),
        recursive=cast(
            bool,
            remaining.pop("recursive", False),
        ),
        target_root=cast(
            Path,
            remaining.pop("target_root", target_root),
        ),
        config_path=cast(
            Path | None,
            remaining.pop("config_path", None),
        ),
        inspect_content=cast(
            bool,
            remaining.pop("inspect_content", False),
        ),
        conflict_strategy=cast(
            ConflictStrategy,
            remaining.pop("conflict_strategy", "fail"),
        ),
        profile=cast(
            TaxonomyProfileName | None,
            remaining.pop("profile", None),
        ),
    )

    if remaining:
        raise AssertionError(
            "unsupported request overrides: " + ", ".join(sorted(remaining))
        )

    return request


def _move(source: Path, destination: Path) -> PlannedMove:
    return PlannedMove(
        source=source,
        destination=destination,
        category=FileCategory.DOCUMENTS,
    )


def _payload_v2(target: Path, content: bytes) -> dict[str, object]:
    timestamp = datetime.now(timezone.utc).isoformat()
    source = target.parent / "source.txt"
    destination = target / "documents" / "source.txt"
    return {
        "schema_version": 2,
        "state": "completed",
        "target_root": str(target),
        "started_at": timestamp,
        "updated_at": timestamp,
        "finished_at": timestamp,
        "counts": {
            "completed": 1,
            "failed": 0,
            "in_progress": 0,
            "unattempted": 0,
        },
        "moves": [
            {
                "original_path": str(source),
                "final_path": str(destination),
                "category": "documents",
                "status": "completed",
                "timestamp": timestamp,
                "error": None,
                "identity": {
                    "algorithm": "sha256",
                    "digest": hashlib.sha256(content).hexdigest(),
                    "size_bytes": len(content),
                    "source_observed_at": timestamp,
                    "destination_observed_at": timestamp,
                },
            }
        ],
    }


def _write_manifest(target: Path, payload: dict[str, object]) -> Path:
    directory = target / ".smart-file-organizer" / "manifests"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "apply-20260805T120000000000Z-0123456789ab.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _first_payload_move(payload: dict[str, object]) -> dict[str, object]:
    return cast(dict[str, object], cast(list[object], payload["moves"])[0])


def _empty_manifest() -> ApplyManifest:
    timestamp = datetime.now(timezone.utc)
    return ApplyManifest(
        path=Path("/target/.smart-file-organizer/manifests/apply.json"),
        schema_version=2,
        state="completed",
        target_root=Path("/target"),
        started_at=timestamp,
        updated_at=timestamp,
        finished_at=timestamp,
        counts=ManifestCounts(0, 0, 0, 0),
    )


def test_request_tuple_copies_sources_and_is_immutable() -> None:
    sources = [Path("first.txt")]
    request = PlanOrganizationRequest(
        explicit_sources=cast(tuple[Path, ...], sources),
        source_root=None,
        recursive=False,
        target_root=Path("organized"),
        config_path=None,
        inspect_content=False,
        conflict_strategy="fail",
    )
    sources.append(Path("second.txt"))

    assert request.explicit_sources == (Path("first.txt"),)
    with pytest.raises(FrozenInstanceError):
        setattr(request, "target_root", Path("other"))


def test_organization_plan_tuple_copies_moves_and_preserves_lexical_target() -> None:
    moves = [_move(Path("a.txt"), Path("relative-target/custom/a.txt"))]
    plan = OrganizationPlan(
        Path("relative-target/../relative-target"),
        cast(tuple[PlannedMove, ...], moves),
    )
    moves.clear()

    assert plan.target_root == Path("relative-target/../relative-target")
    assert len(plan.moves) == 1
    with pytest.raises(FrozenInstanceError):
        setattr(plan, "moves", ())


def test_plan_preserves_explicit_source_order(tmp_path: Path) -> None:
    second = tmp_path / "second.txt"
    first = tmp_path / "first.jpg"
    second.write_text("second")
    first.write_text("first")

    plan = plan_organization(_request(second, first, target_root=tmp_path / "target"))

    assert [move.source for move in plan.moves] == [second, first]


def test_plan_scans_sources_in_deterministic_order(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    later = source_root / "z.txt"
    earlier = source_root / "a.jpg"
    later.write_text("later")
    earlier.write_text("earlier")

    plan = plan_organization(
        _request(
            source_root=source_root,
            recursive=False,
            target_root=tmp_path / "target",
        )
    )

    assert [move.source for move in plan.moves] == [earlier, later]


def test_planning_is_callable_without_cli(tmp_path: Path) -> None:
    source = tmp_path / "notes.txt"
    source.write_text("notes")

    plan = plan_organization(_request(source, target_root=tmp_path / "target"))

    assert plan.moves[0].destination == tmp_path / "target/documents/inbox/notes.txt"


def test_configured_rules_precedence_fallback_and_disabled_builtins_are_preserved(
    tmp_path: Path,
) -> None:
    source = tmp_path / "Conto-FASTWEB-M000000000-20260501.pdf"
    source.write_text("statement")
    config = tmp_path / "config.toml"
    config.write_text(
        """
fallback_folder = "documents/fallback"
disabled_builtin_rules = ["builtin:documents/utilities/fastweb"]

[[semantic_rules]]
folder = "documents/custom"
keywords = ["fastweb"]
""",
        encoding="utf-8",
    )

    plan = plan_organization(
        _request(source, target_root=tmp_path / "target", config_path=config)
    )

    assert plan.moves[0].destination == (
        tmp_path / "target/documents/custom/Conto-FASTWEB-M000000000-20260501.pdf"
    )

    precedence_config = tmp_path / "precedence.toml"
    precedence_config.write_text(
        """
semantic_rule_precedence = "configured-first"

[[semantic_rules]]
folder = "documents/precedence"
keywords = ["fastweb"]
""",
        encoding="utf-8",
    )
    precedence_plan = plan_organization(
        _request(source, target_root=tmp_path / "target", config_path=precedence_config)
    )
    assert precedence_plan.moves[0].destination == (
        tmp_path / "target/documents/precedence/Conto-FASTWEB-M000000000-20260501.pdf"
    )

    unknown = tmp_path / "unknown.pdf"
    unknown.write_text("unknown")
    fallback_plan = plan_organization(
        _request(unknown, target_root=tmp_path / "target", config_path=config)
    )
    assert fallback_plan.moves[0].destination == (
        tmp_path / "target/documents/fallback/unknown.pdf"
    )


def test_content_aware_planning_uses_existing_inspection_seam(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "notes.txt"
    source.write_text("notes")
    called: dict[str, object] = {}

    def fake_content_planner(
        sources,
        target_root: Path,
        *,
        semantic_rules=None,
        fallback_folder=None,
        verbose=False,
    ):
        called["sources"] = list(sources)
        called["target_root"] = target_root
        called["semantic_rules"] = semantic_rules
        called["fallback_folder"] = fallback_folder
        called["verbose"] = verbose
        return [_move(source, target_root / "documents/content/notes.txt")]

    monkeypatch.setattr(
        application,
        "build_organization_plan_inspecting_content",
        fake_content_planner,
    )

    plan = plan_organization(
        _request(source, target_root=tmp_path / "target", inspect_content=True),
        verbose=True,
    )

    assert called == {
        "sources": [source],
        "target_root": tmp_path / "target",
        "semantic_rules": None,
        "fallback_folder": "documents/inbox",
        "verbose": True,
    }
    assert plan.moves[0].destination == tmp_path / "target/documents/content/notes.txt"


def test_conflict_fail_has_safe_deterministic_conflicts(tmp_path: Path) -> None:
    first = tmp_path / "a" / "photo.jpg"
    second = tmp_path / "b" / "photo.jpg"
    first.parent.mkdir()
    second.parent.mkdir()
    first.write_text("first")
    second.write_text("second")

    with pytest.raises(OrganizationPlanConflictError) as error:
        plan_organization(_request(second, first, target_root=tmp_path / "target"))

    conflicts = error.value.conflicts
    destination, moves = next(iter(conflicts.items()))
    assert destination == tmp_path / "target/images/photo.jpg"
    assert tuple(move.source for move in moves) == (second, first)
    assert all(move.destination == destination for move in moves)
    assert all(move.category == FileCategory.IMAGES for move in moves)
    assert all(move.classification is not None for move in moves)

    with pytest.raises(TypeError):
        cast(
            dict[Path, tuple[PlannedMove, ...]],
            conflicts,
        )[destination] = ()


def test_rename_conflicts_remain_deterministic_for_repeated_parent_labels(
    tmp_path: Path,
) -> None:
    sources = []
    for snapshot in ("snapshot-a", "snapshot-b", "snapshot-c"):
        source = tmp_path / snapshot / "device" / "tool"
        source.parent.mkdir(parents=True)
        source.write_text(snapshot)
        sources.append(source)

    plan = plan_organization(
        _request(
            *sources,
            target_root=tmp_path / "target",
            conflict_strategy="rename",
        )
    )

    assert [move.destination.name for move in plan.moves] == [
        "tool",
        "tool__device",
        "tool__device-2",
    ]


def test_final_destination_validation_remains_active(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.txt"
    source.write_text("source")
    monkeypatch.setattr(
        application,
        "build_organization_plan",
        lambda *_args, **_kwargs: [_move(source, tmp_path / "outside.txt")],
    )

    with pytest.raises(ValueError, match="destination is outside target directory"):
        plan_organization(_request(source, target_root=tmp_path / "target"))


def test_apply_uses_hand_built_plan_without_replanning(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    target = tmp_path / "target"
    source.write_text("source")
    plan = OrganizationPlan(
        target,
        (_move(source, target / "custom" / "intentionally-hand-built.txt"),),
    )

    result = apply_organization(plan)

    assert result.completed_count == 1
    assert not source.exists()
    assert (target / "custom/intentionally-hand-built.txt").read_text() == "source"


def test_empty_plan_applies_with_existing_zero_count_manifest(tmp_path: Path) -> None:
    result = apply_organization(OrganizationPlan(tmp_path / "target", ()))

    assert result.completed_count == 0
    assert result.manifest_path.is_file()


def test_assess_recovery_returns_immutable_proposed_v2_assessment(
    tmp_path: Path,
) -> None:
    target = tmp_path / "target"
    payload = _payload_v2(target, b"current")
    destination = Path(cast(str, _first_payload_move(payload)["final_path"]))
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"current")
    manifest_path = _write_manifest(target, payload)

    assessment = assess_recovery(manifest_path)

    assert assessment.manifest is assessment.verification.manifest
    assert assessment.safety_classification.verification is assessment.verification
    assert assessment.plan.manifest is assessment.manifest
    assert assessment.plan.verification is assessment.verification
    assert assessment.safety_classification.decisions[0].state is (
        RecoverySafetyState.SAFE_TO_RECOVER
    )
    assert assessment.plan.items[0].disposition is RecoveryDisposition.PROPOSED
    assert (
        assessment.plan.items[0].safety_decision
        is (assessment.safety_classification.decisions[0])
    )
    assert hasattr(assessment, "__slots__")
    with pytest.raises(FrozenInstanceError):
        setattr(assessment, "plan", assessment.plan)


def test_assess_recovery_returns_refused_v2_assessment_for_identity_mismatch(
    tmp_path: Path,
) -> None:
    target = tmp_path / "target"
    payload = _payload_v2(target, b"historical")
    move = _first_payload_move(payload)
    destination = Path(cast(str, move["final_path"]))
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"changed")
    manifest_path = _write_manifest(target, payload)

    assessment = assess_recovery(manifest_path)

    assert assessment.safety_classification.decisions[0].state is (
        RecoverySafetyState.REFUSED
    )
    assert assessment.safety_classification.decisions[0].reason is (
        RecoverySafetyReason.DESTINATION_CHANGED
    )
    assert assessment.plan.items[0].disposition is RecoveryDisposition.REFUSED


def test_assess_recovery_uses_single_canonical_pipeline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _empty_manifest()
    verification = ManifestVerification(manifest, (), {})
    classification = RecoverySafetyClassification(verification, ())
    recovery_plan = RecoveryPlan(manifest, verification, ())
    calls: list[str] = []

    def fake_load_manifest(path: Path) -> ApplyManifest:
        calls.append(f"load:{path}")
        return manifest

    def fake_verify_manifest(received: ApplyManifest) -> ManifestVerification:
        calls.append("verify")
        assert received is manifest
        return verification

    def fake_classify_recovery_safety(
        received: ManifestVerification,
    ) -> RecoverySafetyClassification:
        calls.append("classify")
        assert received is verification
        return classification

    def fake_plan_recovery(
        received: RecoverySafetyClassification,
    ) -> RecoveryPlan:
        calls.append("plan")
        assert received is classification
        return recovery_plan

    monkeypatch.setattr(application, "load_manifest", fake_load_manifest)
    monkeypatch.setattr(application, "_verify_manifest", fake_verify_manifest)
    monkeypatch.setattr(
        application,
        "classify_recovery_safety",
        fake_classify_recovery_safety,
    )
    monkeypatch.setattr(application, "_plan_recovery", fake_plan_recovery)

    assessment = assess_recovery(manifest.path)

    assert assessment == RecoveryAssessment(
        manifest,
        verification,
        classification,
        recovery_plan,
    )
    assert calls == [f"load:{manifest.path}", "verify", "classify", "plan"]


def test_recovery_assessment_fails_closed_for_contradictory_alignment(
    tmp_path: Path,
) -> None:
    target = tmp_path / "target"
    payload = _payload_v2(target, b"current")
    manifest_path = _write_manifest(target, payload)
    manifest = application.load_manifest(manifest_path)
    verification = ManifestVerification(manifest, (), {})
    classification = RecoverySafetyClassification(verification, ())
    other_manifest = replace(manifest, state="failed")
    plan = application.RecoveryPlan(
        other_manifest,
        ManifestVerification(other_manifest, (), {}),
        (),
    )

    with pytest.raises(ValueError, match="plan does not match manifest"):
        RecoveryAssessment(manifest, verification, classification, plan)


def test_recovery_assessment_fails_closed_for_plan_safety_contradiction(
    tmp_path: Path,
) -> None:
    target = tmp_path / "target"
    payload = _payload_v2(target, b"current")
    destination = Path(cast(str, _first_payload_move(payload)["final_path"]))
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"current")
    manifest_path = _write_manifest(target, payload)
    assessment = assess_recovery(manifest_path)
    bad_item = replace(
        assessment.plan.items[0],
        disposition=RecoveryDisposition.REFUSED,
        recovery_source=None,
        recovery_destination=None,
    )
    bad_plan = replace(assessment.plan, items=(bad_item,))

    with pytest.raises(ValueError, match="plan item is misaligned"):
        RecoveryAssessment(
            assessment.manifest,
            assessment.verification,
            assessment.safety_classification,
            bad_plan,
        )


def test_plan_recovery_delegates_to_canonical_assessment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Assessment:
        plan = object()

    path = Path(
        "/target/.smart-file-organizer/manifests/"
        "apply-20260805T120000000000Z-0123456789ab.json"
    )

    def fake_assess_recovery(received: Path) -> _Assessment:
        assert received == path
        return _Assessment()

    monkeypatch.setattr(application, "assess_recovery", fake_assess_recovery)

    assert plan_recovery(path) is _Assessment.plan


@pytest.mark.parametrize(
    "error",
    [ManifestWriteError("manifest"), DestinationExistsError("exists")],
)
def test_apply_propagates_execution_errors_unchanged(
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
) -> None:
    plan = OrganizationPlan(Path("target"), ())

    def fail_execute(*_args: object, **_kwargs: object):
        raise error

    monkeypatch.setattr(application, "execute_plan", fail_execute)

    with pytest.raises(type(error)) as raised:
        apply_organization(plan)

    assert raised.value is error


def test_application_has_no_adapter_or_rendering_dependencies() -> None:
    source = Path(application.__file__).read_text(encoding="utf-8")
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

    assert "argparse" not in imported_names | imported_modules
    assert "sys" not in imported_names | imported_modules
    assert "smart_file_organizer.cli" not in imported_names | imported_modules
    assert "smart_file_organizer.plan_output" not in imported_names | imported_modules
