# Changelog

All notable changes to this project are documented in this file.

## [Unreleased]

### Changed

- use `smart-file-organizer plan ...` as the canonical onboarding syntax;
- report empty text scans explicitly while preserving `[]` for JSON previews;
- emit concise expected-error messages without an argparse usage dump;
- document exit statuses and the owning operational-boundary sections.

## [0.4.0] - 2026-08-01

### Added

- supported installation from GitHub Release wheel artifacts;
- installed-package smoke tests for Python 3.11 and Python 3.12;
- reproducible wheel and source-distribution verification;
- SHA-256 checksum generation and verification;
- `smart-file-organizer --version`;
- explicit MIT license expression and public project URLs;
- automated tag-driven GitHub Release publication;
- installation, first-run, release, and artifact-verification documentation.

### Changed

- Ruff now targets the minimum supported Python version, Python 3.11;
- CI separates quality, compatibility, and installed-package checks.

[0.4.0]: https://github.com/gcomneno/smart-file-organizer/releases/tag/v0.4.0
