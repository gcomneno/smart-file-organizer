"""Headless-testable control flow for the read-only desktop adapter."""

from pathlib import Path

from smart_file_organizer import api
from smart_file_organizer.gui.view_model import (
    DesktopState,
    recovery_assessment_view,
)


def assess_manifest(state: DesktopState) -> DesktopState:
    """Assess the current manifest input through the supported API seam."""
    manifest_input = state.manifest_input.strip()
    if not manifest_input:
        return state.with_diagnostic("Choose or enter a manifest path first.")

    try:
        assessment = api.assess_recovery(Path(manifest_input))
    except api.ManifestError as error:
        return state.with_diagnostic(f"Could not assess manifest: {error}")
    return state.with_assessment(recovery_assessment_view(assessment))
