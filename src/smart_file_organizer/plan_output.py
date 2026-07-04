"""Plan preview output formatters."""

import json
from collections.abc import Iterable
from typing import Literal

from smart_file_organizer.models import PlannedMove

OutputFormat = Literal["text", "json"]


def format_planned_move(move: PlannedMove) -> str:
    """Format a planned move as a text line."""
    return f"{move.source} -> {move.destination}"


def format_plan_text(plan: Iterable[PlannedMove]) -> str:
    """Format a plan preview as plain text lines."""
    lines = [format_planned_move(move) for move in plan]
    if not lines:
        return ""

    return "\n".join(lines) + "\n"


def format_plan_json(plan: Iterable[PlannedMove]) -> str:
    """Format a plan preview as JSON."""
    payload = [
        {
            "source": str(move.source),
            "destination": str(move.destination),
            "category": move.category.value,
        }
        for move in plan
    ]
    return json.dumps(payload, indent=2) + "\n"


def render_plan_preview(
    plan: Iterable[PlannedMove],
    *,
    output_format: OutputFormat = "text",
) -> str:
    """Render a plan preview in the requested format."""
    if output_format == "json":
        return format_plan_json(plan)

    return format_plan_text(plan)
