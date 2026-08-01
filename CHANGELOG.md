# Changelog

All notable changes to this project are documented in this file.

## [Unreleased]

## [0.4.2] - 2026-08-01

### Fixed

- resolve rename-strategy conflicts when different sources share the same
  immediate parent-directory name;
- reserve existing and generated plan destinations while assigning deterministic
  numeric rename suffixes;
- keep expected destination-conflict diagnostics free of default logging
  prefixes while retaining structured events in verbose mode.

## [0.4.1] - 2026-08-01

### Changed

- use `smart-file-organizer plan ...` as the canonical onboarding syntax;
- report empty text scans explicitly while preserving `[]` for JSON previews;
- emit concise expected-error messages without an argparse usage dump;
- document exit statuses and the owning operational-boundary sections;
- keep handled apply failures quiet in the default logger so CLI diagnostics
  are not duplicated;
- define Linux case-collision behavior and the current Linux-only support
  boundary;
- add bounded 512-file smoke coverage and cross-cutting source-disappearance
  and permission regressions.

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

[Unreleased]: https://github.com/gcomneno/smart-file-organizer/compare/v0.4.2...HEAD
[0.4.2]: https://github.com/gcomneno/smart-file-organizer/compare/v0.4.1...v0.4.2
[0.4.1]: https://github.com/gcomneno/smart-file-organizer/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/gcomneno/smart-file-organizer/releases/tag/v0.4.0
