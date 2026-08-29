#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 1 ]; then
    printf 'usage: smoke-installed-package.sh WHEEL\n' >&2
    false
fi

WHEEL_PATH="$(realpath "$1")"
PYTHON_SELECTOR="${UV_PYTHON:-3.12}"
test -f "$WHEEL_PATH"

TEMP_DIRECTORY="$(mktemp -d)"
trap 'rm -rf "$TEMP_DIRECTORY"' EXIT
VENV="$TEMP_DIRECTORY/venv"
WORK_DIRECTORY="$TEMP_DIRECTORY/work"
SOURCE_DIRECTORY="$WORK_DIRECTORY/sources"
TARGET_DIRECTORY="$WORK_DIRECTORY/organized"
mkdir -p "$SOURCE_DIRECTORY"

export UV_NO_PROGRESS=1
unset PYTHONPATH
export PYTHONNOUSERSITE=1

uv python install "$PYTHON_SELECTOR"
uv venv --python "$PYTHON_SELECTOR" "$VENV"
uv pip install --python "$VENV/bin/python" "$WHEEL_PATH"

CLI="$VENV/bin/smart-file-organizer"
test -x "$CLI"
cd "$WORK_DIRECTORY"

EXPECTED_VERSION="$(
    "$VENV/bin/python" -c \
        'from importlib.metadata import version; print(version("smart-file-organizer"))'
)"
VERSION_OUTPUT="$("$CLI" --version)"
test "$VERSION_OUTPUT" = "smart-file-organizer $EXPECTED_VERSION"

"$CLI" --help >/dev/null
"$CLI" plan --help >/dev/null
"$CLI" manifest --help >/dev/null
"$CLI" recover --help >/dev/null

SOURCE="$SOURCE_DIRECTORY/ordinary-user-note.txt"
DESTINATION="$TARGET_DIRECTORY/documents/inbox/ordinary-user-note.txt"
printf 'Synthetic installed-package smoke test.\n' > "$SOURCE"

DRY_RUN_OUTPUT="$("$CLI" plan --target "$TARGET_DIRECTORY" "$SOURCE")"
test "$DRY_RUN_OUTPUT" = "$SOURCE -> $DESTINATION"
test -f "$SOURCE"
test ! -e "$DESTINATION"

"$CLI" plan --profile minimal --explain --format json \
    --target "$TARGET_DIRECTORY" "$SOURCE" | "$VENV/bin/python" -c '
import json
import sys

payload = json.load(sys.stdin)
classification = payload[0]["classification"]
assert classification["taxonomy_profile"] == "minimal"
assert classification["outcome"] == "fallback"
'

"$CLI" plan --apply --target "$TARGET_DIRECTORY" "$SOURCE" >/dev/null
test ! -e "$SOURCE"
test -f "$DESTINATION"

MANIFEST="$(
    find "$TARGET_DIRECTORY/.smart-file-organizer/manifests" \
        -maxdepth 1 -type f -name '*.json' -print -quit
)"
test -n "$MANIFEST"

"$CLI" manifest show "$MANIFEST" --json | "$VENV/bin/python" -c '
import json
import sys
assert json.load(sys.stdin)["schema_version"] == 2
'
"$CLI" manifest list --target "$TARGET_DIRECTORY" --json | "$VENV/bin/python" -c '
import json
import sys
assert json.load(sys.stdin)[0]["status"] == "valid"
'
"$CLI" manifest verify "$MANIFEST" --json | "$VENV/bin/python" -c '
import json
import sys
assert json.load(sys.stdin)["summary"]["consistent"] == 1
'
"$CLI" recover plan "$MANIFEST" --json | "$VENV/bin/python" -c '
import json
import sys
payload = json.load(sys.stdin)
assert payload["recovery_assessment_schema_version"] == 1
item = payload["items"][0]
assert item["safety"]["state"] == "safe_to_recover"
assert item["safety"]["reason"] == "recovery_preconditions_verified"
assert item["plan"]["disposition"] == "proposed"
assert "recovery_source" in item["plan"]
assert "digest" not in json.dumps(payload)
assert "size_bytes" not in json.dumps(payload)
'

"$VENV/bin/python" - <<'PY'
from importlib import metadata, resources
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

import smart_file_organizer
import smart_file_organizer.api as api
from smart_file_organizer.api import *  # noqa: F403

api_path = Path(api.__file__).resolve()
virtual_environment = Path(sys.prefix).resolve()
assert api_path.is_relative_to(virtual_environment), (
    api_path,
    virtual_environment,
)

distribution = metadata.distribution("smart-file-organizer")
package_metadata = distribution.metadata
assert package_metadata["Requires-Python"] == ">=3.11"
assert package_metadata["License-Expression"] == "MIT"
project_urls = package_metadata.get_all("Project-URL") or []
for required_name in ("Homepage", "Repository", "Issues", "Changelog", "Releases"):
    assert any(value.startswith(f"{required_name},") for value in project_urls)

expected_exports = [
    "ApplyManifest",
    "BrokenSourceSymlinkError",
    "ClassificationCandidate",
    "ClassificationDecision",
    "ClassificationEvidence",
    "ClassificationOutcome",
    "ClassificationSource",
    "ConfigError",
    "ConflictStrategy",
    "CurrentIdentityObservation",
    "DestinationConflictError",
    "DestinationExistsError",
    "DestinationParentError",
    "ExecutionResult",
    "EvidenceSource",
    "EvidenceStrength",
    "FileCategory",
    "IdentityObservationStatus",
    "IdentityVerificationReason",
    "IdentityVerificationState",
    "InvalidSourceError",
    "ManifestAccessError",
    "ManifestCounts",
    "ManifestError",
    "ManifestFormatError",
    "ManifestMove",
    "ManifestPathError",
    "ManifestReference",
    "ManifestReferenceStatus",
    "ManifestVerification",
    "ManifestWriteError",
    "MatchMechanism",
    "MoveExecutionRecord",
    "MoveIdentityVerification",
    "MoveReconciliation",
    "MoveStatus",
    "OrganizationPlan",
    "OrganizationPlanConflictError",
    "PlanOrganizationRequest",
    "PlannedMove",
    "ReconciliationState",
    "RecoveryAssessment",
    "RecoveryDisposition",
    "RecoveryPlan",
    "RecoveryPlanItem",
    "RecoverySafetyClassification",
    "RecoverySafetyDecision",
    "RecoverySafetyReason",
    "RecoverySafetyState",
    "SourceMissingError",
    "SourceSelectionError",
    "TaxonomyProfileName",
    "UnsafePathError",
    "UnsupportedSourceSymlinkError",
    "apply_organization",
    "assess_recovery",
    "list_manifests",
    "load_manifest",
    "plan_recovery",
    "plan_organization",
    "verify_manifest",
]
assert api.__all__ == expected_exports
for name in api.__all__:
    getattr(api, name)
    assert name in globals()
assert "smart_file_organizer.cli" not in sys.modules
assert smart_file_organizer.__all__ == ["__version__", "get_version"]
assert resources.files("smart_file_organizer").joinpath("py.typed").is_file()

with TemporaryDirectory() as temporary_directory:
    workspace = Path(temporary_directory)
    semantic_source = workspace / "fastweb.txt"
    source = workspace / "source.txt"
    target = workspace / "target"
    semantic_source.write_text("installed wheel semantic smoke", encoding="utf-8")
    source.write_text("installed wheel API smoke", encoding="utf-8")
    semantic_plan = api.plan_organization(
        api.PlanOrganizationRequest(
            explicit_sources=(semantic_source,),
            source_root=None,
            recursive=False,
            target_root=target,
            config_path=None,
            inspect_content=False,
            conflict_strategy="fail",
        )
    )
    semantic_decision = semantic_plan.moves[0].classification
    assert semantic_decision is not None
    assert semantic_decision.outcome is api.ClassificationOutcome.SELECTED
    assert semantic_decision.selected_candidate is not None
    assert semantic_decision.selected_candidate.evidence[0].source is api.EvidenceSource.FILENAME
    request = api.PlanOrganizationRequest(
        explicit_sources=(source,),
        source_root=None,
        recursive=False,
        target_root=target,
        config_path=None,
        inspect_content=False,
        conflict_strategy="fail",
        profile=api.TaxonomyProfileName.MINIMAL,
    )
    plan = api.plan_organization(request)
    assert plan.moves[0].source == source
    assert plan.moves[0].classification is not None
    assert plan.moves[0].classification.taxonomy_profile is api.TaxonomyProfileName.MINIMAL
    assert plan.moves[0].classification.outcome is api.ClassificationOutcome.FALLBACK
    result = api.apply_organization(plan)
    assert result.successful
    assert result.manifest_path.is_file()
    assert (target / "documents/inbox/source.txt").is_file()
    assert not source.exists()
    assessment = api.assess_recovery(result.manifest_path)
    recovery_plan = api.plan_recovery(result.manifest_path)
    assert recovery_plan.items[0].disposition is api.RecoveryDisposition.PROPOSED
    assert assessment.safety_classification.decisions[0].state is api.RecoverySafetyState.SAFE_TO_RECOVER
    assert assessment.safety_classification.decisions[0].reason is api.RecoverySafetyReason.RECOVERY_PRECONDITIONS_VERIFIED
PY

printf 'Installed smoke test passed: Python %s, package %s\n' \
    "$PYTHON_SELECTOR" "$EXPECTED_VERSION"
