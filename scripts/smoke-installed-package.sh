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

"$CLI" plan --apply --target "$TARGET_DIRECTORY" "$SOURCE" >/dev/null
test ! -e "$SOURCE"
test -f "$DESTINATION"

MANIFEST="$(
    find "$TARGET_DIRECTORY/.smart-file-organizer/manifests" \
        -maxdepth 1 -type f -name '*.json' -print -quit
)"
test -n "$MANIFEST"

"$VENV/bin/python" - <<'PY'
from importlib import metadata

distribution = metadata.distribution("smart-file-organizer")
package_metadata = distribution.metadata
assert package_metadata["Requires-Python"] == ">=3.11"
assert package_metadata["License-Expression"] == "MIT"
project_urls = package_metadata.get_all("Project-URL") or []
for required_name in ("Homepage", "Repository", "Issues", "Changelog", "Releases"):
    assert any(value.startswith(f"{required_name},") for value in project_urls)
PY

printf 'Installed smoke test passed: Python %s, package %s\n' \
    "$PYTHON_SELECTOR" "$EXPECTED_VERSION"
