#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

REQUESTED_OUTPUT="${1:-dist}"
case "$REQUESTED_OUTPUT" in
    /*) OUTPUT_DIRECTORY="$REQUESTED_OUTPUT" ;;
    *) OUTPUT_DIRECTORY="$PROJECT_ROOT/$REQUESTED_OUTPUT" ;;
esac

case "$OUTPUT_DIRECTORY" in
    "$PROJECT_ROOT"/*) ;;
    *) printf 'error: output directory must be inside the repository\n' >&2; false ;;
esac

test "$OUTPUT_DIRECTORY" != "$PROJECT_ROOT"

TEMP_DIRECTORY="$(mktemp -d)"
trap 'rm -rf "$TEMP_DIRECTORY"' EXIT
FIRST_BUILD="$TEMP_DIRECTORY/first"
SECOND_BUILD="$TEMP_DIRECTORY/second"
mkdir -p "$FIRST_BUILD" "$SECOND_BUILD"

export SOURCE_DATE_EPOCH="$(git log -1 --format=%ct)"
export TZ=UTC
export LC_ALL=C
export UV_NO_PROGRESS=1

printf 'SOURCE_DATE_EPOCH=%s\n' "$SOURCE_DATE_EPOCH"
uv build --out-dir "$FIRST_BUILD"
uv build --out-dir "$SECOND_BUILD"

mapfile -t ARTIFACT_NAMES < <(
    find "$FIRST_BUILD" -maxdepth 1 -type f \
        \( -name '*.whl' -o -name '*.tar.gz' \) \
        -printf '%f\n' | sort
)

test "${#ARTIFACT_NAMES[@]}" -eq 2

for artifact_name in "${ARTIFACT_NAMES[@]}"; do
    test -f "$SECOND_BUILD/$artifact_name"
    cmp "$FIRST_BUILD/$artifact_name" "$SECOND_BUILD/$artifact_name"
    printf 'Reproducible: %s\n' "$artifact_name"
done

rm -rf "$OUTPUT_DIRECTORY"
mkdir -p "$OUTPUT_DIRECTORY"
for artifact_name in "${ARTIFACT_NAMES[@]}"; do
    cp "$FIRST_BUILD/$artifact_name" "$OUTPUT_DIRECTORY/$artifact_name"
done

(
    cd "$OUTPUT_DIRECTORY"
    sha256sum ./*.tar.gz ./*.whl | sed 's|  \./|  |' | sort -k2 > SHA256SUMS
    sha256sum --check SHA256SUMS
)

python3 scripts/verify-release-artifacts.py "$OUTPUT_DIRECTORY"
printf 'Release artifacts ready in %s\n' "$OUTPUT_DIRECTORY"
