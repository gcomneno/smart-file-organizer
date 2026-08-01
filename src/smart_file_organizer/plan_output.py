"""Plan preview output formatters."""

import json
from collections.abc import Iterable
from typing import Literal

from smart_file_organizer.models import PlannedMove


OutputFormat = Literal["text", "json"]


def _classification_payload(
    move: PlannedMove,
) -> dict[str, str | None] | None:
    """Return serializable classification evidence."""
    decision = move.classification

    if decision is None:
        return None

    return {
        "folder": str(decision.folder),
        "source": decision.source.value,
        "rule_id": decision.rule_id,
        "match_target": decision.match_target,
        "reason": decision.reason,
    }


def format_planned_move(
    move: PlannedMove,
    *,
    explain: bool = False,
) -> str:
    """Format a planned move as one text line."""
    line = f"{move.source} -> {move.destination}"

    if not explain:
        return line

    decision = move.classification

    if decision is None:
        return f"{line} [classification unavailable]"

    rule_text = decision.rule_id if decision.rule_id is not None else "-"
    target_text = decision.match_target if decision.match_target is not None else "-"

    return (
        f"{line} "
        f"[source={decision.source.value} "
        f"rule={rule_text} "
        f"target={target_text} "
        f"reason={decision.reason}]"
    )


def format_plan_text(
    plan: Iterable[PlannedMove],
    *,
    explain: bool = False,
) -> str:
    """Format a plan preview as plain text lines."""
    lines = [
        format_planned_move(
            move,
            explain=explain,
        )
        for move in plan
    ]

    if not lines:
        return ""

    return "\n".join(lines) + "\n"


def format_plan_json(
    plan: Iterable[PlannedMove],
    *,
    explain: bool = False,
) -> str:
    """Format a plan preview as JSON."""
    payload: list[dict[str, object]] = []

    for move in plan:
        item: dict[str, object] = {
            "source": str(move.source),
            "destination": str(move.destination),
            "category": move.category.value,
        }

        if explain:
            item["classification"] = _classification_payload(move)

        payload.append(item)

    return json.dumps(payload, indent=2) + "\n"


def render_plan_preview(
    plan: Iterable[PlannedMove],
    *,
    output_format: OutputFormat = "text",
    explain: bool = False,
) -> str:
    """Render a plan preview in the requested format."""
    if output_format == "json":
        return format_plan_json(
            plan,
            explain=explain,
        )

    return format_plan_text(
        plan,
        explain=explain,
    )
