"""Pure presentation mapping for read-only recovery assessments."""

from dataclasses import dataclass

from smart_file_organizer import api

TRUST_LAYER_KEYS = (
    "historical",
    "reconciliation",
    "identity",
    "safety",
    "proposal",
)

AUTHORITY_NOTICE = (
    "This assessment is read-only. Historical evidence, current observations, "
    "identity verification, safety classification, and a recovery proposal are "
    "distinct. SAFE TO RECOVER and PROPOSED do not authorize filesystem changes."
)


@dataclass(frozen=True, slots=True)
class DisplayField:
    """One deterministic label/value pair."""

    label: str
    value: str


@dataclass(frozen=True, slots=True)
class TrustLayerView:
    """One visibly distinct layer in the recovery trust chain."""

    key: str
    title: str
    state: str
    fields: tuple[DisplayField, ...]


@dataclass(frozen=True, slots=True)
class RecoveryItemView:
    """Presentation of one historical move and its recovery assessment layers."""

    index: int
    layers: tuple[TrustLayerView, ...]


@dataclass(frozen=True, slots=True)
class RecoverySummaryView:
    """Assessment-wide counts projected from the supported recovery plan."""

    total_move_records: int
    proposed_count: int
    refused_count: int

    @property
    def fields(self) -> tuple[DisplayField, ...]:
        """Return the deterministic label/value representation used by the GUI."""
        return (
            DisplayField("Total move records", str(self.total_move_records)),
            DisplayField("Proposed", str(self.proposed_count)),
            DisplayField("Refused", str(self.refused_count)),
        )


@dataclass(frozen=True, slots=True)
class RecoveryAssessmentView:
    """Immutable read-only presentation of a supported API assessment."""

    manifest_path: str
    manifest_fields: tuple[DisplayField, ...]
    summary: RecoverySummaryView
    items: tuple[RecoveryItemView, ...]
    authority_notice: str = AUTHORITY_NOTICE


@dataclass(frozen=True, slots=True)
class DiagnosticView:
    """Controlled user-facing diagnostic for an expected input failure."""

    message: str


@dataclass(frozen=True, slots=True)
class DesktopState:
    """Immutable transient state for the manifest assessment workflow."""

    manifest_input: str = ""
    assessment: RecoveryAssessmentView | None = None
    diagnostic: DiagnosticView | None = None

    def with_manifest_input(self, value: str) -> "DesktopState":
        """Change input and invalidate any result derived from an older path."""
        if value == self.manifest_input:
            return self
        return DesktopState(manifest_input=value)

    def with_manifest_input_write(self, value: str) -> "DesktopState":
        """Record an input write and always invalidate point-in-time results."""
        return DesktopState(manifest_input=value)

    def with_assessment(self, assessment: RecoveryAssessmentView) -> "DesktopState":
        """Attach a fresh assessment to the current manifest input."""
        return DesktopState(
            manifest_input=self.manifest_input,
            assessment=assessment,
        )

    def with_diagnostic(self, message: str) -> "DesktopState":
        """Attach a controlled diagnostic and leave no stale assessment visible."""
        return DesktopState(
            manifest_input=self.manifest_input,
            diagnostic=DiagnosticView(message),
        )


def recovery_assessment_view(
    assessment: api.RecoveryAssessment,
) -> RecoveryAssessmentView:
    """Map the canonical API aggregate without reinterpreting its semantics."""
    manifest = assessment.manifest
    plan_items = assessment.plan.items
    items = tuple(
        _recovery_item_view(index, reconciliation, decision, plan_item)
        for index, (reconciliation, decision, plan_item) in enumerate(
            zip(
                assessment.verification.moves,
                assessment.safety_classification.decisions,
                assessment.plan.items,
                strict=True,
            ),
            start=1,
        )
    )
    return RecoveryAssessmentView(
        manifest_path=str(manifest.path),
        manifest_fields=(
            DisplayField("Schema version", str(manifest.schema_version)),
            DisplayField("Historical execution state", _display(manifest.state)),
            DisplayField("Target root", str(manifest.target_root)),
            DisplayField("Started", manifest.started_at.isoformat()),
            DisplayField("Updated", manifest.updated_at.isoformat()),
            DisplayField(
                "Finished",
                manifest.finished_at.isoformat()
                if manifest.finished_at is not None
                else "Not recorded",
            ),
            DisplayField("Historical move records", str(manifest.counts.total)),
        ),
        summary=RecoverySummaryView(
            total_move_records=len(plan_items),
            proposed_count=sum(
                item.disposition is api.RecoveryDisposition.PROPOSED
                for item in plan_items
            ),
            refused_count=sum(
                item.disposition is api.RecoveryDisposition.REFUSED
                for item in plan_items
            ),
        ),
        items=items,
    )


def _recovery_item_view(
    index: int,
    reconciliation: api.MoveReconciliation,
    decision: api.RecoverySafetyDecision,
    plan_item: api.RecoveryPlanItem,
) -> RecoveryItemView:
    move = reconciliation.move
    identity = reconciliation.identity
    proposal_fields = (
        (
            DisplayField("Proposed recovery source", str(plan_item.recovery_source)),
            DisplayField(
                "Proposed recovery destination",
                str(plan_item.recovery_destination),
            ),
        )
        if plan_item.recovery_source is not None
        and plan_item.recovery_destination is not None
        else (DisplayField("Guidance", "No recovery operation is proposed"),)
    )
    return RecoveryItemView(
        index=index,
        layers=(
            TrustLayerView(
                key="historical",
                title="1. Historical manifest evidence",
                state=_display(move.status.value),
                fields=(
                    DisplayField("Original path", str(move.original_path)),
                    DisplayField("Recorded final path", str(move.final_path)),
                    DisplayField("Category", _display(move.category.value)),
                    DisplayField("Recorded status", _display(move.status.value)),
                    DisplayField("Recorded timestamp", move.timestamp.isoformat()),
                    DisplayField(
                        "Payload identity evidence",
                        "Recorded" if move.identity is not None else "Not recorded",
                    ),
                ),
            ),
            TrustLayerView(
                key="reconciliation",
                title="2. Current reconciliation",
                state=_display(reconciliation.state.value),
                fields=(
                    DisplayField(
                        "Original path exists now",
                        _existence(reconciliation.source_exists),
                    ),
                    DisplayField(
                        "Recorded final path exists now",
                        _existence(reconciliation.destination_exists),
                    ),
                ),
            ),
            TrustLayerView(
                key="identity",
                title="3. Identity verification",
                state=_display(identity.state.value),
                fields=(DisplayField("Reason", _display(identity.reason.value)),),
            ),
            TrustLayerView(
                key="safety",
                title="4. Recovery safety",
                state=_display(decision.state.value),
                fields=(
                    DisplayField("Reason", _display(decision.reason.value)),
                    DisplayField("Explanation", decision.explanation),
                ),
            ),
            TrustLayerView(
                key="proposal",
                title="5. Recovery proposal / refusal",
                state=_display(plan_item.disposition.value),
                fields=proposal_fields,
            ),
        ),
    )


def _display(value: str) -> str:
    return value.replace("_", " ").capitalize()


def _existence(value: bool | None) -> str:
    if value is True:
        return "Yes"
    if value is False:
        return "No"
    return "Unknown"
