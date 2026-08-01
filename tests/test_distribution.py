import tomllib
from pathlib import Path
from typing import cast

import pytest

from smart_file_organizer import __version__
from smart_file_organizer.cli import main


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_project_metadata() -> dict[str, object]:
    """Return the PEP 621 project table."""
    data = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = data["project"]
    assert isinstance(project, dict)
    return project


def test_package_version_matches_project_metadata() -> None:
    project = load_project_metadata()
    assert project["version"] == "0.4.1"
    assert __version__ == project["version"]


def test_cli_reports_installed_version(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])
    captured = capsys.readouterr()
    assert exc_info.value.code == 0
    assert captured.err == ""
    assert captured.out == "smart-file-organizer 0.4.1\n"


def test_project_metadata_declares_provenance() -> None:
    project = load_project_metadata()
    assert project["license"] == "MIT"
    assert project["license-files"] == ["LICENSE"]
    assert project["requires-python"] == ">=3.11"
    urls = cast(
        dict[str, object],
        project["urls"],
    )
    assert urls["Repository"] == "https://github.com/gcomneno/smart-file-organizer"
    assert urls["Issues"] == "https://github.com/gcomneno/smart-file-organizer/issues"
    assert (
        urls["Releases"] == "https://github.com/gcomneno/smart-file-organizer/releases"
    )


def test_ci_covers_minimum_and_primary_python_versions() -> None:
    workflow = (PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )
    assert '"3.11"' in workflow
    assert '"3.12"' in workflow
    assert "build-release-artifacts.sh" in workflow
    assert "smoke-installed-package.sh" in workflow


def test_release_workflow_publishes_verified_artifacts() -> None:
    workflow = (PROJECT_ROOT / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )
    assert 'tags:\n      - "v*"' in workflow
    assert "Verify tag matches package version" in workflow
    assert "build-release-artifacts.sh" in workflow
    assert "SHA256SUMS" in workflow
    assert "gh release create" in workflow
