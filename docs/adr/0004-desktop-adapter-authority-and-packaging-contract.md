# ADR 0004: Desktop adapter authority and packaging contract

- Status: Accepted
- Date: 2026-08-29
- Related issues: [#80](https://github.com/gcomneno/smart-file-organizer/issues/80), [#99](https://github.com/gcomneno/smart-file-organizer/issues/99)
- Extends: [ADR 0001](0001-evolution-architecture.md), [ADR 0002](0002-verifiable-recovery-contract.md)
- Depends on: [ADR 0003](0003-manifest-v2-identity-schema.md)

## Context

ADR 0001 establishes Smart File Organizer as a safe application platform with
thin adapters over application services. ADR 0002 defines verifiable recovery as
a separation between historical facts, current observations, identity evidence,
recovery-safety decisions, and non-mutating recovery proposals. ADR 0003 defines
Manifest v2 identity evidence without adding recovery execution or a GUI.

Phase 7 introduces a desktop adapter. The adapter must make the existing trust
model easier to inspect without creating a second application layer, weakening
dry-run and apply boundaries, or enlarging the package dependency footprint
before there is evidence that doing so is necessary.

The current supported Python API is `smart_file_organizer.api`. Its normative
export set is `smart_file_organizer.api.__all__`, protected by contract tests.
The package supports Linux with Python 3.11 and Python 3.12. It currently ships
one console entry point and one mandatory third-party runtime dependency for PDF
text extraction.

## Decision

### Desktop depends on the supported API

The desktop adapter must depend on the supported API boundary:

```text
desktop adapter
    -> smart_file_organizer.api
        -> application/domain/infrastructure
```

Desktop code must not import internal modules to recreate domain behavior.

Widget code, callbacks, commands, and event handlers must not implement or
independently reinterpret:

- classification;
- destination conflict semantics;
- path validation;
- manifest parsing or validation;
- identity verification;
- recovery-safety classification;
- recovery-plan construction;
- overwrite decisions;
- filesystem mutation mechanics.

Those semantics remain owned by the existing application, domain, manifest,
verification, recovery, execution, and path-validation layers. The desktop
adapter may render API results, gather user inputs, hold transient presentation
state, and invoke supported API operations.

If the adapter needs information that is not available through
`smart_file_organizer.api`, the correct response is a separate smallest-possible
API issue with contract tests. GUI code must not bypass the API by importing
internal manifest, verification, recovery, planning, or execution modules.

### Authority remains staged and explicit

The desktop adapter must preserve the existing organization authority model:

```text
evidence
  != proposed organization plan
  != explicit approval
  != filesystem mutation
```

Planning and review never mutate files. A visible plan does not authorize
apply. User approval applies only to the currently reviewed plan. Changing
organization inputs, target, profile, configuration, content-inspection setting,
recursive selection, conflict strategy, or any other planning input invalidates
prior plan approval and apply readiness.

Filesystem mutation may occur only through the existing explicit organization
apply application/API operation over the reviewed `OrganizationPlan`.

The desktop adapter must also preserve the recovery authority model:

```text
historical manifest evidence
  != current observation
  != identity verification
  != recovery safety
  != recovery proposal
  != mutation authority
```

A `RecoveryAssessment` is a point-in-time, non-mutating aggregate. A
`RecoveryPlan` item with `PROPOSED` disposition remains a proposal only.
`SAFE_TO_RECOVER` and `PROPOSED` must not be rendered or treated as permanent
permission to mutate the filesystem.

Phase 7 does not introduce recovery execution, automatic rollback,
`recover --apply`, or overwrite authority.

### The first prototype uses tkinter

The first Phase 7 desktop prototype uses Python stdlib `tkinter`.

This decision is intentionally conservative:

- no new PyPI runtime dependency is required;
- the current distribution remains lightweight;
- Python 3.11 and Python 3.12 include the tkinter module when the Python and
  system installation provide Tk support;
- forms, tables, status summaries, and detail inspection are sufficient for the
  first trust-projection workflow;
- presentation mapping can remain testable outside widget code;
- Phase 7 optimizes clarity of authority and evidence, not visual richness.

This is not a broad claim that the GUI is available everywhere the core package
or CLI is available. Tk availability can depend on the Python build and system
packages installed on the supported Linux environment. A missing Tk runtime must
not break CLI or library imports and should be reported as GUI unavailability,
not as core package failure.

This ADR does not expand the repository's supported platform claim beyond the
current Linux and Python 3.11/3.12 boundary.

### The GUI stays in the existing distribution for now

The smallest coherent packaging architecture is:

- desktop adapter code lives in the existing distribution as a separate GUI
  module;
- default CLI and library paths do not import GUI modules;
- importing `smart_file_organizer.api` does not import GUI modules;
- no mandatory third-party GUI dependency is added;
- a GUI entry point may be introduced by a later implementation issue.

This ADR decides the packaging boundary for the first Phase 7 prototype. It
does not choose the eventual executable name, widget structure, layout, icon
assets, installer format, or release packaging beyond the constraints above.

If a future issue selects a non-stdlib GUI toolkit, packaging must be
reconsidered explicitly. The likely choices are an optional extra or a separate
application/package. A future toolkit decision must not silently enlarge core
runtime dependencies or make CLI/library availability depend on GUI packages.

### Presentation mapping is pure and adapter-owned

Presentation and view-model mapping are the correct places for:

- labels;
- grouping;
- display ordering;
- path elision and truncation;
- badges and state presentation;
- controlled confirmation text;
- privacy-safe summaries of API results.

These mappings should be pure, deterministic functions over supported API
values where practical. They must not become a second application or domain
layer. They may decide how to display `REFUSED`, `PROPOSED`,
`SAFE_TO_RECOVER`, identity states, reconciliation states, and plan counts, but
they must not decide those states.

### Stale desktop state fails closed

Desktop state is transient and can become stale.

Changing organization inputs invalidates the prior plan and any approval tied
to it. Apply requires the currently reviewed `OrganizationPlan`, not an earlier
preview or a reconstructed list of displayed moves.

Manifest verification and `RecoveryAssessment` values are point-in-time
observations. The GUI must not imply that an earlier `SAFE_TO_RECOVER` or
`PROPOSED` result remains valid after time passes, after the manifest is
reloaded, or after the filesystem changes. Recovery assessment must not become
durable mutation authority.

Because Phase 7 does not introduce recovery execution, this ADR defines no
recovery mutation freshness protocol.

### Privacy and security boundaries remain unchanged

The desktop adapter must preserve current privacy and security boundaries:

- never render raw extracted document content;
- do not broaden content inspection;
- treat selected, file-picker, pasted, and dropped paths as untrusted inputs;
- use supported API validation rather than GUI-side trust;
- render controlled diagnostics rather than arbitrary tracebacks or internal
  structures;
- do not add GUI-side hashing or filesystem inspection to reconstruct trust;
- do not use network or cloud services for classification, inspection,
  manifests, identity verification, or recovery assessment.

Content inspection remains opt-in. The GUI may expose that option in a future
planning workflow, but enabling it must call the supported planning API and must
not leak extracted text through presentation state, logs, dialogs, or errors.

### Public API gap for current path observations

The current public API exports `MoveReconciliation`, and each reconciliation
contains `source_observation` and `destination_observation` fields. Those fields
are instances of `CurrentPathObservation`, whose `status` is a
`PathObservationStatus`.

Reconnaissance found that `CurrentPathObservation` and `PathObservationStatus`
are not currently supported exports from `smart_file_organizer.api`.

The first read-only recovery-assessment prototype needs to display historical
evidence, reconciliation/current observation, identity, safety, and plan as
visibly distinct layers. The existing supported aggregate is sufficient to
display reconciliation state, source and destination existence, identity
verification state and reason, safety state and reason, explanations, and plan
disposition. It is also sufficient to show `REFUSED` and to avoid mutation.

However, if that prototype intends to display the structured current path
observation fields or type-check presentation code against those types, this is
a supported-API gap. The gap must be handled as a separate smallest-possible
prerequisite issue after this ADR is accepted. Issue #99 does not change
`api.py`, and GUI code must not import internal manifest modules to get those
types.

Structured privacy-safe content-inspection degradation notices may become a
later API concern for a full planning GUI. They are not required for the first
read-only recovery-assessment prototype because that slice does not inspect
document content.

### First implementation slice

The recommended first post-ADR implementation slice is a read-only desktop
recovery assessment:

1. the user chooses a manifest path;
2. the desktop adapter calls supported `assess_recovery(path)`;
3. the UI renders historical manifest evidence, reconciliation/current
   observation, identity verification, recovery safety, and recovery plan as
   visibly distinct layers;
4. `REFUSED` is presented as a valid safety result;
5. no files, directories, manifests, or package metadata are mutated;
6. no recovery execution is introduced.

If the implementation requires direct display or public typing of
`CurrentPathObservation` or `PathObservationStatus`, the API export issue must
precede this slice. Otherwise, the slice can proceed using the already supported
`RecoveryAssessment` aggregate and exported recovery, reconciliation, identity,
and safety models.

### Testing contract for future implementation

Future desktop implementation must include tests proportional to the risk and
kept outside toolkit mechanics where possible:

- pure view-model tests for labels, grouping, ordering, path elision, badges,
  confirmation text, and stale-state transitions;
- adapter/API boundary tests proving desktop code calls supported
  `smart_file_organizer.api` operations rather than internal modules;
- semantic parity checks with supported API or CLI output where applicable;
- zero-mutation tests for manifest loading, verification, recovery assessment,
  and any inspection-only GUI workflows;
- explicit organization apply-boundary tests showing apply is available only
  for the currently reviewed plan after approval;
- minimal GUI smoke or headless tests only where toolkit behavior genuinely
  needs coverage;
- import tests proving GUI absence does not break core CLI or library imports.

Core CLI and library tests must not depend on Tk availability.

## Preserved invariants

This ADR preserves:

- dry run by default;
- explicit apply;
- planning/execution separation;
- no silent overwrite;
- target-root containment;
- deterministic classification and explainability;
- ambiguity and abstention;
- controlled diagnostics without traceback leakage for expected errors;
- no extracted-content leakage;
- manifest history/current observation separation;
- identity verification as evidence, not mutation authority;
- recovery planning as non-mutating;
- no automatic rollback or recovery execution;
- Linux support boundary and Python 3.11/3.12 support;
- lightweight core CLI/library imports.

## Consequences

The desktop adapter can make the trust model easier to understand without
changing the trust model.

Using tkinter lets the first prototype focus on workflow clarity and packaging
discipline. The cost is a visually modest toolkit and possible GUI
unavailability on Linux installations that lack Tk support. That cost is
acceptable for the first prototype because CLI and library behavior remain
available and unchanged.

The supported API boundary may need one small follow-up before a richer
recovery UI can display every current path observation field as a supported
contract. Recording that gap is preferable to letting GUI code depend on
internal manifest models.

## Non-goals

This ADR does not:

- implement GUI code;
- define widget layout or visual design;
- add dependencies;
- change the public Python API;
- add a GUI entry point;
- replace the CLI;
- implement recovery execution;
- add automatic rollback;
- add `recover --apply`;
- authorize overwrite;
- add GUI-specific domain semantics;
- edit or repair manifests;
- add manifest authenticity, signing, MACs, or trust anchors;
- add OCR;
- add machine-learning classification;
- add cloud or network integration;
- upgrade unrelated dependencies.

## Rejected alternatives

### GUI imports internal modules for richer details

Rejected because it treats implementation modules as an accidental API and
risks duplicating or weakening domain semantics in widget code.

### GUI-side safety and recovery logic

Rejected because recovery safety is already a governed application/domain
contract. A desktop-specific classifier would create conflicting authority
models and make safety depend on presentation code.

### Recovery execution in Phase 7

Rejected because ADR 0002 and ADR 0003 do not authorize recovery mutation.
Phase 7 may project recovery trust more clearly, but it must not introduce
automatic rollback, `recover --apply`, or overwrite authority.

### Third-party GUI toolkit for the first prototype

Rejected for the first Phase 7 prototype because forms, tables, summaries, and
detail inspection do not yet justify a mandatory runtime dependency or a
separate packaging surface.

### Separate desktop package immediately

Rejected for the first prototype because stdlib tkinter permits a smaller
coherent increment inside the existing distribution while keeping CLI and API
imports independent from GUI modules.

## Follow-up

After this ADR is accepted, the next focused issue should implement the
read-only desktop recovery assessment slice. If that implementation requires
supported access to `CurrentPathObservation` or `PathObservationStatus`, a
minimal API export issue with contract tests must land first.
