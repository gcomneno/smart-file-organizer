import tomllib
from pathlib import Path
from typing import cast

import pytest

from smart_file_organizer import __version__
from smart_file_organizer.cli import main


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ATTEST_ACTION_PIN = "actions/attest@508db95dd578ae2727ebd6217d5ba78e4fbda05d"


def load_project_metadata() -> dict[str, object]:
    """Return the PEP 621 project table."""
    data = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = data["project"]
    assert isinstance(project, dict)
    return project


def load_workflow(name: str) -> str:
    return (PROJECT_ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")


def assert_contains_in_order(text: str, snippets: list[str]) -> None:
    position = -1
    for snippet in snippets:
        next_position = text.find(snippet, position + 1)
        assert next_position > position, snippet
        position = next_position


def text_between(text: str, start: str, end: str) -> str:
    start_position = text.index(start)
    end_position = text.index(end, start_position)
    return text[start_position:end_position]


def test_package_version_matches_project_metadata() -> None:
    project = load_project_metadata()
    version = project["version"]
    assert isinstance(version, str)
    assert __version__ == version


def test_cli_reports_installed_version(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])
    captured = capsys.readouterr()
    assert exc_info.value.code == 0
    assert captured.err == ""
    project = load_project_metadata()
    version = project["version"]
    assert isinstance(version, str)
    assert captured.out == f"smart-file-organizer {version}\n"


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
    workflow = load_workflow("ci.yml")
    assert '"3.11"' in workflow
    assert '"3.12"' in workflow
    assert "build-release-artifacts.sh" in workflow
    assert "smoke-installed-package.sh" in workflow


def test_release_workflow_publishes_verified_artifacts() -> None:
    workflow = load_workflow("release.yml")
    assert 'tags:\n      - "v*"' in workflow
    assert "\npermissions:\n  contents: read\n\nconcurrency:" in workflow
    assert "Verify tag matches package version" in workflow
    assert "build-release-artifacts.sh" in workflow
    assert "SHA256SUMS" in workflow
    assert "scripts/verify-release-artifacts.py" in Path(
        PROJECT_ROOT / "scripts" / "build-release-artifacts.sh"
    ).read_text(encoding="utf-8")
    assert "smoke-installed-package.sh dist/*.whl" in workflow
    assert '"3.11"' in workflow
    assert '"3.12"' in workflow


def test_release_workflow_permissions_are_least_privilege_for_provenance() -> None:
    workflow = load_workflow("release.yml")
    assert_contains_in_order(
        workflow,
        [
            "permissions:\n  contents: read",
            "permissions:\n      contents: write\n      attestations: write\n"
            "      id-token: write",
        ],
    )
    assert "packages:" not in workflow
    assert "actions:" not in workflow
    assert "checks:" not in workflow


def test_release_workflow_uses_pinned_actions_and_safe_checkout() -> None:
    workflow = load_workflow("release.yml")
    assert "actions/checkout@fbc6f3992d24b796d5a048ff273f7fcc4a7b6c09" in workflow
    assert "astral-sh/setup-uv@08807647e7069bb48b6ef5acd8ec9567f424441b" in workflow
    assert "persist-credentials: false" in workflow
    assert f"uses: {ATTEST_ACTION_PIN} # v4.2.1" in workflow
    assert "actions/attest@v4" not in workflow


def test_release_workflow_attests_exact_release_artifact_subjects() -> None:
    workflow = load_workflow("release.yml")
    assert_contains_in_order(
        workflow,
        [
            "Smoke test installed wheel on Python 3.12",
            "Attest release artifacts",
            f"uses: {ATTEST_ACTION_PIN} # v4.2.1",
            "subject-path: |\n            dist/*.whl\n            dist/*.tar.gz\n"
            "            dist/SHA256SUMS",
            "Create draft GitHub Release",
        ],
    )


def test_release_workflow_validates_draft_assets_before_publication() -> None:
    workflow = load_workflow("release.yml")
    assert_contains_in_order(
        workflow,
        [
            'gh release create "$GITHUB_REF_NAME"',
            "--draft",
            "--verify-tag",
            'gh release upload "$GITHUB_REF_NAME"',
            "Validate draft release assets",
            '"gh", "release", "view", tag, "--json", "isDraft,assets"',
            "actual_assets != expected_assets",
            'gh release edit "$GITHUB_REF_NAME" --draft=false --verify-tag',
        ],
    )

    upload_step = text_between(
        workflow,
        'gh release upload "$GITHUB_REF_NAME"',
        "Validate draft release assets",
    )
    assert "dist/*.whl" in upload_step
    assert "dist/*.tar.gz" in upload_step
    assert "dist/SHA256SUMS" in upload_step
    assert "--clobber" not in upload_step
