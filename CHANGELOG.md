# Changelog

All notable changes to this project are documented in this file.

## [Unreleased]

### Added

- expose `assess_recovery()` and `RecoveryAssessment` through the supported
  Python API as the canonical verifiable-recovery aggregate;
- expose recovery-safety state, reason, decision, and classification models
  through the supported Python API;
- add versioned `recover plan --json` recovery-assessment output with
  reconciliation, identity, safety, and plan layers.

### Changed

- make `recover plan` render the application recovery assessment and preserve
  refusal as a successful read-only safety result;
- normalize public recovery-safety reasons before freezing the API vocabulary.

## [0.5.0] - 2026-08-05

### Added

- public application services and a supported Python API for planning,
  application, manifest inspection, verification, and recovery planning;
- deterministic explainable classification evidence with selected, ambiguous,
  abstained, extension, and fallback outcomes;
- built-in `personal-it` and conservative `minimal` taxonomy profiles;
- privacy-safe `--explain` output in text and JSON planning formats;
- schema-v1 manifest loading, strict validation, deterministic listing, and
  reconciliation with current filesystem state;
- non-mutating `recover plan` operations with explicit proposals, refusals,
  already-restored, no-action, and unsafe dispositions;
- `manifest show`, `manifest list`, `manifest verify`, and `recover plan`
  command-line operations;
- an architecture decision record for the evolution into a reusable,
  explainable application platform.

### Changed

- command-line orchestration now delegates to reusable application services;
- manifest serialization and validation share one schema-v1 contract while
  preserving the established atomic writer and partial-failure evidence;
- semantic classification now uses deterministic candidate aggregation,
  precedence, tie handling, and conservative abstention;
- installed-package smoke coverage exercises the public API and manifest
  commands on Python 3.11 and Python 3.12.

### Security

- reject duplicate JSON keys, embedded-NUL paths, contradictory manifest
  states, unsafe containment, and unsupported schema data;
- resolve only the designated target-root alias while rejecting symlinks
  inside the manifest store;
- keep verification and recovery planning read-only and refuse ambiguous or
  unsafe reverse operations.


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

[Unreleased]: https://github.com/gcomneno/smart-file-organizer/compare/v0.5.0...HEAD
[0.5.0]: https://github.com/gcomneno/smart-file-organizer/compare/v0.4.2...v0.5.0
[0.4.2]: https://github.com/gcomneno/smart-file-organizer/compare/v0.4.1...v0.4.2
[0.4.1]: https://github.com/gcomneno/smart-file-organizer/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/gcomneno/smart-file-organizer/releases/tag/v0.4.0
