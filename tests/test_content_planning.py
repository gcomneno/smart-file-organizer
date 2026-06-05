from pathlib import Path

from smart_file_organizer.content_planning import (
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
