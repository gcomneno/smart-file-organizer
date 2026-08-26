"""Pure recovery-plan projection from classified recovery-safety evidence."""

from smart_file_organizer.manifest_models import (
    RecoveryDisposition,
    RecoveryPlan,
    RecoveryPlanItem,
)
from smart_file_organizer.recovery_safety import (
    RecoverySafetyClassification,
    RecoverySafetyDecision,
    RecoverySafetyState,
)


def build_recovery_plan(
    classification: RecoverySafetyClassification,
) -> RecoveryPlan:
    """Project Phase-4 safety decisions into a non-mutating recovery plan."""
    _validate_classification_alignment(classification)
    items = tuple(_item(decision) for decision in classification.decisions)
    return RecoveryPlan(
        classification.verification.manifest,
        classification.verification,
        items,
    )


def plan_recovery(classification: RecoverySafetyClassification) -> RecoveryPlan:
    """Compatibility wrapper for the canonical Phase-5 recovery planner."""
    return build_recovery_plan(classification)


def _validate_classification_alignment(
    classification: RecoverySafetyClassification,
) -> None:
    if (
        tuple(decision.reconciliation for decision in classification.decisions)
        != classification.verification.moves
    ):
        raise ValueError("recovery safety classification is malformed or misaligned")


def _item(decision: RecoverySafetyDecision) -> RecoveryPlanItem:
    reconciliation = decision.reconciliation
    move = reconciliation.move
    if decision.state is RecoverySafetyState.SAFE_TO_RECOVER:
        return RecoveryPlanItem(
            move,
            reconciliation,
            RecoveryDisposition.PROPOSED,
            move.final_path,
            move.original_path,
            decision.reason.value,
            decision,
        )
    return RecoveryPlanItem(
        move,
        reconciliation,
        RecoveryDisposition.REFUSED,
        None,
        None,
        decision.reason.value,
        decision,
    )
