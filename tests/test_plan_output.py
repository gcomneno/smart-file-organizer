import json
from pathlib import Path

from smart_file_organizer.core import FileCategory, PlannedMove
from smart_file_organizer.plan_output import (
    format_plan_json,
    format_plan_text,
    format_planned_move,
    render_plan_preview,
)


def test_format_planned_move() -> None:
    move = PlannedMove(
        source=Path("photo.jpg"),
        destination=Path("organized/images/photo.jpg"),
        category=FileCategory.IMAGES,
    )

    assert format_planned_move(move) == "photo.jpg -> organized/images/photo.jpg"


def test_format_plan_text_joins_moves_with_trailing_newline() -> None:
    plan = [
        PlannedMove(
            source=Path("photo.jpg"),
            destination=Path("organized/images/photo.jpg"),
            category=FileCategory.IMAGES,
        ),
        PlannedMove(
            source=Path("notes.txt"),
            destination=Path("organized/documents/notes.txt"),
            category=FileCategory.DOCUMENTS,
        ),
    ]

    assert format_plan_text(plan) == (
        "photo.jpg -> organized/images/photo.jpg\n"
        "notes.txt -> organized/documents/notes.txt\n"
    )


def test_format_plan_text_returns_empty_string_for_empty_plan() -> None:
    assert format_plan_text([]) == ""


def test_format_plan_json_includes_source_destination_and_category() -> None:
    plan = [
        PlannedMove(
            source=Path("photo.jpg"),
            destination=Path("organized/images/photo.jpg"),
            category=FileCategory.IMAGES,
        ),
        PlannedMove(
            source=Path("notes.txt"),
            destination=Path("organized/documents/notes.txt"),
            category=FileCategory.DOCUMENTS,
        ),
    ]

    assert json.loads(format_plan_json(plan)) == [
        {
            "source": "photo.jpg",
            "destination": "organized/images/photo.jpg",
            "category": "images",
        },
        {
            "source": "notes.txt",
            "destination": "organized/documents/notes.txt",
            "category": "documents",
        },
    ]


def test_render_plan_preview_uses_requested_format() -> None:
    plan = [
        PlannedMove(
            source=Path("photo.jpg"),
            destination=Path("organized/images/photo.jpg"),
            category=FileCategory.IMAGES,
        ),
    ]

    assert render_plan_preview(plan, output_format="text") == (
        "photo.jpg -> organized/images/photo.jpg\n"
    )
    assert json.loads(render_plan_preview(plan, output_format="json")) == [
        {
            "source": "photo.jpg",
            "destination": "organized/images/photo.jpg",
            "category": "images",
        },
    ]
