import ast
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import cast

import pytest

import smart_file_organizer.application as application
from smart_file_organizer.application import (
    OrganizationPlan,
    OrganizationPlanConflictError,
    PlanOrganizationRequest,
    apply_organization,
    plan_organization,
)
from smart_file_organizer.errors import DestinationExistsError, ManifestWriteError
from smart_file_organizer.models import (
    ConflictStrategy,
    FileCategory,
    PlannedMove,
    TaxonomyProfileName,
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
