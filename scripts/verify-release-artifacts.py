#!/usr/bin/env python3
"""Verify release filenames, checksums, contents, and metadata."""

from __future__ import annotations

import hashlib
import sys
import tarfile
import tomllib
import zipfile
from email import message_from_bytes
from pathlib import Path
from typing import Never


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def fail(message: str) -> Never:
    """Raise one concise verification failure."""
    raise RuntimeError(message)


def sha256(path: Path) -> str:
    """Return a file's SHA-256 digest."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def project_version() -> str:
    """Return the declared project version."""
    data = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = data.get("project")
    if not isinstance(project, dict):
        fail("pyproject.toml has no [project] table")
    version = project.get("version")
    if not isinstance(version, str) or not version:
        fail("project version is missing")
    return version


def parse_checksums(path: Path) -> dict[str, str]:
    """Parse GNU sha256sum-compatible lines."""
    checksums: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip():
            continue
        parts = raw_line.split(maxsplit=1)
        if len(parts) != 2:
            fail(f"invalid checksum line: {raw_line!r}")
        digest, filename = parts
        filename = filename.lstrip("*")
        if filename in checksums:
            fail(f"duplicate checksum entry: {filename}")
        checksums[filename] = digest
    return checksums


def verify_wheel(wheel: Path, version: str) -> None:
    """Verify wheel metadata and package data."""
    metadata_name = f"smart_file_organizer-{version}.dist-info/METADATA"
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        if metadata_name not in names:
            fail(f"wheel metadata missing: {metadata_name}")
        metadata = message_from_bytes(archive.read(metadata_name))
        if "smart_file_organizer/py.typed" not in names:
            fail("wheel does not contain py.typed")
        if not any("/licenses/LICENSE" in name for name in names):
            fail("wheel does not contain the MIT license file")

    if metadata.get("Name") != "smart-file-organizer":
        fail("wheel contains an unexpected project name")
    if metadata.get("Version") != version:
        fail("wheel version does not match pyproject.toml")
    if metadata.get("Requires-Python") != ">=3.11":
        fail("wheel does not declare Python >=3.11")
    if metadata.get("License-Expression") != "MIT":
        fail("wheel does not declare the MIT license expression")

    required = {"Homepage", "Repository", "Issues", "Changelog", "Releases"}
    actual = {
        value.split(",", maxsplit=1)[0].strip()
        for value in metadata.get_all("Project-URL") or []
        if "," in value
    }
    missing = required - actual
    if missing:
        fail("wheel metadata is missing project URLs: " + ", ".join(sorted(missing)))


def verify_sdist(sdist: Path, version: str) -> None:
    """Verify required source-distribution files."""
    root = f"smart_file_organizer-{version}"
    required = {
        f"{root}/LICENSE",
        f"{root}/README.md",
        f"{root}/pyproject.toml",
        f"{root}/src/smart_file_organizer/py.typed",
    }
    with tarfile.open(sdist, "r:gz") as archive:
        names = set(archive.getnames())
    missing = required - names
    if missing:
        fail("sdist is missing required files: " + ", ".join(sorted(missing)))


def main(argv: list[str]) -> None:
    """Verify one release output directory."""
    if len(argv) != 2:
        fail("usage: verify-release-artifacts.py RELEASE_DIRECTORY")

    release_directory = Path(argv[1]).resolve()
    if not release_directory.is_dir():
        fail(f"release directory does not exist: {release_directory}")

    version = project_version()
    wheel = release_directory / f"smart_file_organizer-{version}-py3-none-any.whl"
    sdist = release_directory / f"smart_file_organizer-{version}.tar.gz"
    checksum_file = release_directory / "SHA256SUMS"

    for path in (wheel, sdist, checksum_file):
        if not path.is_file():
            fail(f"release artifact is missing: {path.name}")

    artifact_names = {
        path.name for path in release_directory.iterdir() if path.is_file()
    }
    expected_names = {wheel.name, sdist.name, checksum_file.name}
    if artifact_names != expected_names:
        fail(
            "unexpected release directory contents: "
            + ", ".join(sorted(artifact_names))
        )

    checksums = parse_checksums(checksum_file)
    if set(checksums) != {wheel.name, sdist.name}:
        fail("SHA256SUMS does not identify exactly wheel and sdist")

    for artifact in (wheel, sdist):
        if checksums[artifact.name] != sha256(artifact):
            fail(f"checksum mismatch for {artifact.name}")

    verify_wheel(wheel, version)
    verify_sdist(sdist, version)
    print(f"Verified release artifacts: {wheel.name}, {sdist.name}, SHA256SUMS")


if __name__ == "__main__":
    main(sys.argv)
