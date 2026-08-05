"""Non-mutating manual recovery planning from verified historical evidence."""

import os
import stat
from pathlib import Path

from smart_file_organizer.manifest_models import (
    ManifestVerification,
    MoveReconciliation,
    RecoveryDisposition,
    RecoveryPlan,
    RecoveryPlanItem,
    ReconciliationState,
)
from smart_file_organizer.models import MoveStatus


def plan_recovery(verification: ManifestVerification) -> RecoveryPlan:
    """Propose only unambiguous safe reverse moves; never reserve or mutate."""
    items: list[RecoveryPlanItem] = []
    destinations = [result.move.original_path for result in verification.moves]
    sources = [result.move.final_path for result in verification.moves]
    for result in verification.moves:
        move = result.move
        if result.state is ReconciliationState.UNSAFE_PATH:
            items.append(
                _item(
                    result,
                    RecoveryDisposition.UNSAFE,
                    "path has an unsafe filesystem hazard",
                )
            )
            continue
        if move.status is MoveStatus.IN_PROGRESS:
            items.append(
                _item(
                    result,
                    RecoveryDisposition.REFUSED,
                    "in-progress record is ambiguous",
                )
            )
            continue
        if move.status is not MoveStatus.COMPLETED:
            if result.state is ReconciliationState.CONSISTENT:
                items.append(
                    _item(
                        result,
                        RecoveryDisposition.NO_ACTION,
                        "record was not completed",
                    )
                )
            else:
                items.append(
                    _item(
                        result,
                        RecoveryDisposition.REFUSED,
                        _refusal_reason(result.state),
                    )
                )
            continue
        if result.state is ReconciliationState.SOURCE_RESTORED:
            items.append(
                _item(
                    result,
                    RecoveryDisposition.ALREADY_RESTORED,
                    "original source is already present",
                )
            )
            continue
        if result.state is not ReconciliationState.CONSISTENT:
            items.append(
                _item(
                    result, RecoveryDisposition.REFUSED, _refusal_reason(result.state)
                )
            )
            continue
        if (
            destinations.count(move.original_path) != 1
            or sources.count(move.final_path) != 1
        ):
            items.append(
                _item(result, RecoveryDisposition.REFUSED, "manifest paths conflict")
            )
            continue
        reason = _recovery_safety_failure(move.final_path, move.original_path)
        if reason is not None:
            disposition = (
                RecoveryDisposition.UNSAFE
                if "unsafe" in reason
                else RecoveryDisposition.REFUSED
            )
            items.append(_item(result, disposition, reason))
            continue
        items.append(
            RecoveryPlanItem(
                move,
                result,
                RecoveryDisposition.PROPOSED,
                move.final_path,
                move.original_path,
                "reverse completed move requires manual execution",
            )
        )
    return RecoveryPlan(verification.manifest, verification, tuple(items))


def _item(
    result: MoveReconciliation,
    disposition: RecoveryDisposition,
    reason: str,
) -> RecoveryPlanItem:
    return RecoveryPlanItem(result.move, result, disposition, None, None, reason)


def _refusal_reason(state: ReconciliationState) -> str:
    return {
        ReconciliationState.BOTH_PRESENT: "source and destination are both present",
        ReconciliationState.BOTH_MISSING: "source and destination are both missing",
        ReconciliationState.DESTINATION_MISSING: "destination is missing after a failed record",
        ReconciliationState.UNEXPECTED_DESTINATION: "destination is unexpected for this record",
        ReconciliationState.INDETERMINATE: "current filesystem state is indeterminate",
    }.get(state, "current filesystem state cannot be recovered safely")


def _recovery_safety_failure(source: Path, destination: Path) -> str | None:
    if _invalid_path(source) or _invalid_path(destination):
        return "recovery path is unsafe"
    if _unsafe_parent(source.parent):
        return "recovery source parent is unsafe"
    try:
        source_info = source.lstat()
    except (OSError, ValueError):
        return "recovery source is inaccessible"
    if not stat.S_ISREG(source_info.st_mode):
        return "recovery source has an unsafe file type"
    if _unsafe_parent(destination.parent):
        return "recovery destination parent is unsafe"
    if _lexists(destination):
        return "recovery destination already exists"
    return None


def _lexists(path: Path) -> bool:
    try:
        return os.path.lexists(path)
    except ValueError:
        return True


def _invalid_path(path: Path) -> bool:
    try:
        return "\x00" in os.fspath(path)
    except (TypeError, ValueError):
        return True


def _unsafe_parent(path: Path) -> bool:
    current = path
    while current != current.parent:
        try:
            info = current.lstat()
        except FileNotFoundError:
            return True
        except (OSError, ValueError):
            return True
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            return True
        current = current.parent
    return False
