# ADR 0001: Approved evolution architecture

- Status: Accepted
- Date: 2026-08-01
- Related issues: [#66](https://github.com/gcomneno/smart-file-organizer/issues/66), [#67](https://github.com/gcomneno/smart-file-organizer/issues/67), [#68](https://github.com/gcomneno/smart-file-organizer/issues/68), [#69](https://github.com/gcomneno/smart-file-organizer/issues/69), [#70](https://github.com/gcomneno/smart-file-organizer/issues/70), [#71](https://github.com/gcomneno/smart-file-organizer/issues/71), [#72](https://github.com/gcomneno/smart-file-organizer/issues/72)

## Context

Smart File Organizer v0.4.2 is the safe operational baseline. Future evolution preserves its current user-facing and filesystem-safety contracts. This ADR records architectural direction, not implementation details or new production behavior.

The intended dependency direction is:

```text
CLI and future adapters
    -> application services
        -> domain planning, classification, and execution abstractions
            -> filesystem and manifest infrastructure
```

Rendering belongs at an adapter boundary. Taxonomy and profile data supply the classification engine, but do not own generic matching or decision mechanics.

## Decision

### Explainable classification

Classification will evolve from direct ordered keyword selection toward structured evidence. Where supported, evidence may come from a filename, source path, extracted content, extension, or configured metadata. Decisions will support deterministic multiple candidates, ambiguity, and abstention.

Fallback routing is separate from semantic selection. Generic matching-and-decision mechanics are separate from taxonomy profile data. The resulting decisions must remain deterministic and explainable. Raw extracted document content must never appear in plans, logs, explanations, or manifests. Machine learning is not required.

Issue [#66](https://github.com/gcomneno/smart-file-organizer/issues/66) is only the first small reusable precision improvement. Issue [#71](https://github.com/gcomneno/smart-file-organizer/issues/71) owns the complete evidence-engine and profile evolution.

### Application orchestration

The CLI will become a thin adapter rather than the workflow owner. Application services will coordinate source collection, content inspection, classification, planning, conflict handling, validation, and execution.

`OrganizationPlan` is approved as a first-class immutable, in-memory application value. This ADR neither defines nor promises a serialized plan schema. Domain algorithms and rendering must not accumulate in the orchestrator. Issue [#69](https://github.com/gcomneno/smart-file-organizer/issues/69) owns this implementation.

During migration, current CLI syntax, output, diagnostics, exit statuses, and safety behavior remain compatible.

### Public API governance

Compatibility is governed across four distinct surfaces:

1. CLI contract.
2. Supported Python API.
3. Independently versioned manifest schema.
4. Internal modules and helpers.

Future public exports must be explicit, minimal, documented, and contract-tested. Underscore-prefixed helpers and built-in rule tables are not intended as the future supported public API. `core.py` remains a transitional compatibility surface until [#70](https://github.com/gcomneno/smart-file-organizer/issues/70) defines and migrates the supported API.

This ADR removes or deprecates nothing and does not expand package-root exports. Before 1.0, stability promises must be stated honestly.

### Manifest read side and recovery

The current durable manifest writer and its truthful partial-failure evidence are retained. Future work adds loading, schema validation, deterministic listing, and filesystem reconciliation. Manifest schema compatibility remains independently versioned; this ADR alone authorizes no manifest schema changes.

Recovery must be plan-first and dry-run-first. Ambiguous filesystem states must be represented rather than guessed away. No unconditional automatic undo or rollback is promised. Issue [#72](https://github.com/gcomneno/smart-file-organizer/issues/72) owns manifest reading, verification, and recovery planning.

## Preserved invariants

The following are non-negotiable:

- Dry run by default.
- Explicit apply.
- Deterministic ordering and output.
- No silent overwrite.
- Destination containment beneath the resolved target.
- Consistent source and symlink policy.
- Truthful completed, failed, unattempted, and interrupted states.
- Durable recovery evidence.
- Concise expected-error diagnostics without tracebacks.
- No extracted-content leakage.
- Linux support boundary unless separately expanded.
- Python 3.11 and 3.12.
- Installed-wheel behavior and reproducible releases.

## Delivery policy

Delivery proceeds through vertical, reviewable increments, not a big-bang rewrite. Each increment preserves behavior while responsibilities move. No speculative framework or dependency-injection container will be introduced. Compatibility changes require explicit documentation and tests, and each issue must remain within its approved scope.

The roadmap is:

- [#66](https://github.com/gcomneno/smart-file-organizer/issues/66) — Reduce false positives from incidental content keyword matches.
- [#67](https://github.com/gcomneno/smart-file-organizer/issues/67) — Evolve Smart File Organizer into a safe, explainable application platform.
- [#68](https://github.com/gcomneno/smart-file-organizer/issues/68) — Document the approved evolution architecture in an ADR.
- [#69](https://github.com/gcomneno/smart-file-organizer/issues/69) — Introduce first-class organization plans and application orchestration.
- [#70](https://github.com/gcomneno/smart-file-organizer/issues/70) — Define and contract-test the public Python API surface.
- [#71](https://github.com/gcomneno/smart-file-organizer/issues/71) — Build an explainable evidence engine with ambiguity and taxonomy profiles.
- [#72](https://github.com/gcomneno/smart-file-organizer/issues/72) — Add manifest reading, verification, and recovery planning.

## Consequences

Positive consequences include thinner adapters, a reusable application boundary, safer semantic evolution, controlled compatibility, inspectable recovery, and support for both opinionated and conservative taxonomy profiles.

The costs are more explicit models and boundaries, migration work across multiple releases, and temporary compatibility layers. Ambiguity and abstention need richer output and tests. Schema and API compatibility need deliberate governance.

## Rejected alternatives

The project rejects or defers:

- Machine-learning-first classification.
- Continuing to grow `cli.main()` as the application service.
- Treating private helpers and rule tables as stable API.
- Automatic unconditional rollback.
- A broad repository-wide rewrite.
- Microservices, a database, a plugin framework, or generic dependency-injection machinery without demonstrated need.
