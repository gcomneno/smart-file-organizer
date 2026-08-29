"""Deterministic private CLI renderers for manifest operations."""

import json
from typing import TYPE_CHECKING

from smart_file_organizer.manifest_models import (
    ApplyManifest,
    ManifestReference,
    ManifestVerification,
    MoveIdentityVerification,
    ReconciliationState,
    RecoveryDisposition,
    RecoveryPlan,
    RecoveryPlanItem,
)
from smart_file_organizer.recovery_safety import (
    RecoverySafetyDecision,
    RecoverySafetyState,
)

if TYPE_CHECKING:
    from smart_file_organizer.application import RecoveryAssessment

RECOVERY_ASSESSMENT_SCHEMA_VERSION = 1


def render_manifest(manifest: ApplyManifest, *, json_output: bool) -> str:
    """Render a validated historical manifest without raw JSON exposure."""
    data = _manifest_data(manifest)
    if json_output:
        return _json(data)
    lines = [
        f"Schema version: {manifest.schema_version}",
        f"State: {manifest.state}",
        f"Target root: {manifest.target_root}",
        f"Started: {manifest.started_at.isoformat()}",
        f"Updated: {manifest.updated_at.isoformat()}",
        f"Finished: {manifest.finished_at.isoformat() if manifest.finished_at else '-'}",
        "Counts: "
        + " ".join(
            f"{name}={getattr(manifest.counts, name)}"
            for name in ("completed", "failed", "in_progress", "unattempted")
        ),
    ]
    for move in manifest.moves:
        line = (
            f"- {move.status}: {move.original_path} -> {move.final_path} "
            f"[{move.category}]"
        )
        if move.error_type is not None:
            line += f" ({move.error_type}: {move.error_message})"
        lines.append(line)
    return "\n".join(lines) + "\n"


def render_references(
    references: tuple[ManifestReference, ...], *, json_output: bool
) -> str:
    """Render valid and invalid direct manifest candidates."""
    data = [
        {
            "path": str(reference.path),
            "status": reference.status.value,
            "error_code": reference.error_code,
            "state": reference.manifest.state if reference.manifest else None,
        }
        for reference in references
    ]
    if json_output:
        return _json(data)
    if not data:
        return "No manifest candidates.\n"
    return (
        "\n".join(
            f"{entry['status']}: {entry['path']}"
            + (f" ({entry['state']})" if entry["state"] else "")
            + (f" [{entry['error_code']}]" if entry["error_code"] else "")
            for entry in data
        )
        + "\n"
    )


def render_verification(
    verification: ManifestVerification, *, json_output: bool
) -> str:
    """Render every reconciliation observation and a complete summary."""
    data = {
        "manifest": str(verification.manifest.path),
        "moves": [
            {
                "original_path": str(result.move.original_path),
                "final_path": str(result.move.final_path),
                "status": result.move.status.value,
                "state": result.state.value,
                "source_exists": result.source_exists,
                "destination_exists": result.destination_exists,
                "identity": _identity_data(result.identity),
            }
            for result in verification.moves
        ],
        "summary": {
            state.value: verification.count(state) for state in verification.summary
        },
    }
    if json_output:
        return _json(data)
    lines = [
        f"- {result.state}: {result.move.original_path} -> {result.move.final_path} "
        f"[identity={result.identity.state.value} "
        f"reason={result.identity.reason.value} "
        f"current={result.identity.current.status.value}]"
        for result in verification.moves
    ]
    lines.append(
        "Summary: "
        + " ".join(f"{name}={count}" for name, count in data["summary"].items())
    )
    return "\n".join(lines) + "\n"


def render_recovery_plan(plan: RecoveryPlan, *, json_output: bool) -> str:
    """Render proposed manual reversals and explicit non-actions/refusals."""
    data = {
        "manifest": str(plan.manifest.path),
        "items": [
            {
                "disposition": item.disposition.value,
                "source": str(item.recovery_source) if item.recovery_source else None,
                "destination": str(item.recovery_destination)
                if item.recovery_destination
                else None,
                "reason": item.reason,
                "reconciliation": item.reconciliation.state.value,
            }
            for item in plan.items
        ],
    }
    if json_output:
        return _json(data)
    return "\n".join(
        f"{item.disposition}: "
        + (
            f"{item.recovery_source} -> {item.recovery_destination}"
            if item.recovery_source
            else item.move.original_path.as_posix()
        )
        + f" ({item.reason})"
        for item in plan.items
    ) + ("\n" if plan.items else "No recovery records.\n")


def render_recovery_assessment(
    assessment: "RecoveryAssessment", *, json_output: bool
) -> str:
    """Render the public non-mutating recovery assessment contract."""
    data = _recovery_assessment_data(assessment)
    if json_output:
        return _json(data)
    if not assessment.plan.items:
        return "No recovery records.\n"
    lines: list[str] = []
    for item, decision in zip(
        assessment.plan.items,
        assessment.safety_classification.decisions,
        strict=True,
    ):
        reconciliation = item.reconciliation
        identity = reconciliation.identity
        lines.extend(
            [
                f"- {item.move.original_path} -> {item.move.final_path}",
                f"  reconciliation: {reconciliation.state.value}",
                (f"  identity: {identity.state.value} ({identity.reason.value})"),
                (
                    f"  safety: {decision.state.value} "
                    f"({decision.reason.value}) - {decision.explanation}"
                ),
                f"  plan: {_plan_text(item)}",
            ]
        )
    return "\n".join(lines) + "\n"


def _manifest_data(manifest: ApplyManifest) -> dict[str, object]:
    return {
        "schema_version": manifest.schema_version,
        "state": manifest.state,
        "target_root": str(manifest.target_root),
        "started_at": manifest.started_at.isoformat(),
        "updated_at": manifest.updated_at.isoformat(),
        "finished_at": manifest.finished_at.isoformat()
        if manifest.finished_at
        else None,
        "counts": {
            name: getattr(manifest.counts, name)
            for name in ("completed", "failed", "in_progress", "unattempted")
        },
        "moves": [
            {
                "original_path": str(move.original_path),
                "final_path": str(move.final_path),
                "category": move.category.value,
                "status": move.status.value,
                "timestamp": move.timestamp.isoformat(),
                "error_type": move.error_type,
                "error_message": move.error_message,
            }
            for move in manifest.moves
        ],
    }


def _identity_data(identity: MoveIdentityVerification) -> dict[str, object]:
    return {
        "state": identity.state.value,
        "reason": identity.reason.value,
        "current": {
            "status": identity.current.status.value,
            "algorithm": identity.current.algorithm,
            "digest": identity.current.digest,
            "size_bytes": identity.current.size_bytes,
            "observed_at": identity.current.observed_at.isoformat()
            if identity.current.observed_at
            else None,
        },
    }


def _recovery_assessment_data(assessment: "RecoveryAssessment") -> dict[str, object]:
    return {
        "recovery_assessment_schema_version": RECOVERY_ASSESSMENT_SCHEMA_VERSION,
        "manifest": {
            "path": str(assessment.manifest.path),
            "schema_version": assessment.manifest.schema_version,
            "state": assessment.manifest.state,
        },
        "summary": _recovery_summary(assessment),
        "items": [
            _recovery_assessment_item(index, item, decision)
            for index, (item, decision) in enumerate(
                zip(
                    assessment.plan.items,
                    assessment.safety_classification.decisions,
                    strict=True,
                )
            )
        ],
    }


def _recovery_summary(assessment: "RecoveryAssessment") -> dict[str, object]:
    proposed = assessment.plan.proposed_count
    total = len(assessment.plan.items)
    return {
        "total": total,
        "proposed": proposed,
        "refused": total - proposed,
        "reconciliation": {
            state.value: assessment.verification.count(state)
            for state in ReconciliationState
            if assessment.verification.count(state)
        },
        "safety": {
            state.value: sum(
                decision.state is state
                for decision in assessment.safety_classification.decisions
            )
            for state in RecoverySafetyState
        },
    }


def _recovery_assessment_item(
    index: int, item: RecoveryPlanItem, decision: RecoverySafetyDecision
) -> dict[str, object]:
    reconciliation = item.reconciliation
    move = item.move
    data: dict[str, object] = {
        "index": index,
        "historical": {
            "original_path": str(move.original_path),
            "final_path": str(move.final_path),
            "category": move.category.value,
            "status": move.status.value,
        },
        "reconciliation": {
            "state": reconciliation.state.value,
            "source_exists": reconciliation.source_exists,
            "destination_exists": reconciliation.destination_exists,
        },
        "identity": {
            "state": reconciliation.identity.state.value,
            "reason": reconciliation.identity.reason.value,
        },
        "safety": {
            "state": decision.state.value,
            "reason": decision.reason.value,
            "explanation": decision.explanation,
        },
        "plan": {
            "disposition": item.disposition.value,
        },
    }
    if item.disposition is RecoveryDisposition.PROPOSED:
        data["plan"] = {
            "disposition": item.disposition.value,
            "recovery_source": str(item.recovery_source),
            "recovery_destination": str(item.recovery_destination),
        }
    return data


def _plan_text(item: RecoveryPlanItem) -> str:
    if item.disposition is RecoveryDisposition.PROPOSED:
        return f"proposed {item.recovery_source} -> {item.recovery_destination}"
    return "refused"


def _json(value: object) -> str:
    return json.dumps(value, indent=2, sort_keys=True) + "\n"
