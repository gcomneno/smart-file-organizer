# Changelog

All notable changes to this project are documented in this file.

## [Unreleased]

## [0.6.0] - 2026-09-18

### Added

- add Manifest v2 historical identity evidence with complete SHA-256 digests
  and byte counts observed before and after every successfully completed move;
- add fresh current identity observation and verification, kept distinct from
  historical evidence, path reconciliation, and recovery-safety classification;
- add safety-aware, non-mutating recovery planning and classification through
  `RecoveryAssessment`, `assess_recovery()`, and supported public recovery
  state, reason, decision, identity, reconciliation, and plan API models;
- add independently versioned recovery-assessment JSON with historical,
  reconciliation, identity, safety, and plan layers;
- include an optional read-only Tk desktop recovery-assessment prototype,
  launched with `python -m smart_file_organizer.gui` without making Tk a core
  dependency;
- add ADRs 0002, 0003, and 0004 for verifiable recovery, Manifest v2 identity,
  and desktop adapter authority and packaging.

### Changed

- make `recover plan` text and JSON render the full recovery assessment;
  refused recovery is a successful read-only safety result, and refused JSON
  items omit reverse paths;
- keep Manifest v1 strictly readable while conservatively classifying recovery
  as unverifiable and refused, with no proposed reverse path, because v1 lacks
  historical payload identity evidence;
- require two-sided matching identity evidence for a Manifest v2 move to be
  recorded as completed, while preserving truthful failed, unattempted, and
  interrupted evidence when apply cannot satisfy the completion contract;
- normalize the supported public recovery-safety reason vocabulary;
- retain recovery as assessment and planning only: v0.6.0 has no recovery
  executor, automatic rollback, overwrite authority, or `recover --apply`.

### Security

- fail closed at the supported regular-file boundary: Manifest v2 apply refuses
  file symlinks before moving them, and recovery refuses unsupported filesystem
  objects and unsafe symlink topologies;
- treat SHA-256 and byte counts only as payload identity evidence, not manifest
  authenticity or proof that bytes remain unchanged after observation;
- harden CI and release workflows with least-privilege permissions and external
  actions pinned to immutable commit SHAs;
- add explicit release-artifact build provenance and validate the exact draft
  asset filename set before GitHub Release publication.

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

[Unreleased]: https://github.com/gcomneno/smart-file-organizer/compare/v0.6.0...HEAD
[0.6.0]: https://github.com/gcomneno/smart-file-organizer/releases/tag/v0.6.0
[0.5.0]: https://github.com/gcomneno/smart-file-organizer/compare/v0.4.2...v0.5.0
[0.4.2]: https://github.com/gcomneno/smart-file-organizer/compare/v0.4.1...v0.4.2
[0.4.1]: https://github.com/gcomneno/smart-file-organizer/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/gcomneno/smart-file-organizer/releases/tag/v0.4.0
