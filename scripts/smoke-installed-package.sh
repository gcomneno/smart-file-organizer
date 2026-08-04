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
    "BrokenSourceSymlinkError",
    "ClassificationCandidate",
    "ClassificationDecision",
    "ClassificationEvidence",
    "ClassificationOutcome",
    "ClassificationSource",
    "ConfigError",
    "ConflictStrategy",
    "DestinationConflictError",
    "DestinationExistsError",
    "DestinationParentError",
    "ExecutionResult",
    "EvidenceSource",
    "EvidenceStrength",
    "FileCategory",
    "InvalidSourceError",
    "ManifestWriteError",
    "MatchMechanism",
    "MoveExecutionRecord",
    "MoveStatus",
    "OrganizationPlan",
    "OrganizationPlanConflictError",
    "PlanOrganizationRequest",
    "PlannedMove",
    "SourceMissingError",
    "SourceSelectionError",
    "TaxonomyProfileName",
    "UnsafePathError",
    "UnsupportedSourceSymlinkError",
    "apply_organization",
    "plan_organization",
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
PY

printf 'Installed smoke test passed: Python %s, package %s\n' \
    "$PYTHON_SELECTOR" "$EXPECTED_VERSION"
