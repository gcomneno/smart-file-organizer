from pathlib import Path

import pytest

import smart_file_organizer.content_planning as content_planning
from smart_file_organizer.content_planning import (
    build_organization_plan_inspecting_content,
    build_organization_plan_with_extracted_text,
)
from smart_file_organizer.core import FileCategory, PlannedMove


def test_build_organization_plan_with_extracted_text_uses_injected_extractor() -> None:
    extracted_paths: list[Path] = []

    def fake_extract_text(path: Path) -> str:
        extracted_paths.append(path)

        if path == Path("generic.pdf"):
            return "Demo Fiscal Agency\nCertificazione Unica\n"

        return ""

    plan = build_organization_plan_with_extracted_text(
        [
            Path("generic.pdf"),
            Path("photo.jpg"),
        ],
        Path("organized"),
        extract_text=fake_extract_text,
    )

    assert extracted_paths == [
        Path("generic.pdf"),
        Path("photo.jpg"),
    ]
    assert plan == [
        PlannedMove(
            source=Path("generic.pdf"),
            destination=Path("organized/documents/taxes/generic.pdf"),
            category=FileCategory.DOCUMENTS,
        ),
        PlannedMove(
            source=Path("photo.jpg"),
            destination=Path("organized/images/photo.jpg"),
            category=FileCategory.IMAGES,
        ),
    ]


def test_build_organization_plan_inspecting_content_uses_default_extractor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    extracted_paths: list[Path] = []

    def fake_extract_document_text(path: Path, *, verbose: bool = False) -> str:
        extracted_paths.append(path)

        if path == Path("generic.pdf"):
            return "Demo Fiscal Agency\nCertificazione Unica\n"

        return ""

    monkeypatch.setattr(
        content_planning,
        "extract_document_text",
        fake_extract_document_text,
    )

    plan = build_organization_plan_inspecting_content(
        [
            Path("generic.pdf"),
            Path("photo.jpg"),
        ],
        Path("organized"),
    )

    assert extracted_paths == [
        Path("generic.pdf"),
        Path("photo.jpg"),
    ]
    assert plan == [
        PlannedMove(
            source=Path("generic.pdf"),
            destination=Path("organized/documents/taxes/generic.pdf"),
            category=FileCategory.DOCUMENTS,
        ),
        PlannedMove(
            source=Path("photo.jpg"),
            destination=Path("organized/images/photo.jpg"),
            category=FileCategory.IMAGES,
        ),
    ]


def test_build_organization_plan_with_extracted_text_uses_configured_rules() -> None:
    source = Path("notes.txt")
    rules = (
        (
            "learning/demo-course",
            ("demo course",),
        ),
    )

    plan = build_organization_plan_with_extracted_text(
        [source],
        Path("organized"),
        extract_text=lambda _: "Notes from a demo course.",
        semantic_rules=rules,
    )

    assert plan[0].destination == Path("organized/learning/demo-course/notes.txt")
