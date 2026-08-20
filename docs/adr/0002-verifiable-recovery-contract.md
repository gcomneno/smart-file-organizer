# ADR 0002: Verifiable recovery contract and failure model

- Status: Proposed
- Date: 2026-08-20
- Related issues: [#80](https://github.com/gcomneno/smart-file-organizer/issues/80), [#81](https://github.com/gcomneno/smart-file-organizer/issues/81)
- Extends: [ADR 0001](0001-evolution-architecture.md)
- Italian mirror: [versione italiana](0002-verifiable-recovery-contract.it.md)

## Context

ADR 0001 established that manifest history and current filesystem state are
different concerns, that recovery is plan-first and read-only, and that
ambiguous filesystem states must be represented rather than guessed away.

Smart File Organizer now needs a stricter product contract for verifiable
recovery.

The governing product flow is:

```text
Evidence
  -> Plan
    -> Explain
      -> Approve
        -> Apply
          -> Record
            -> Observe
              -> Verify
                -> Recover only if safe
```

The current manifest schema version 1 records durable historical execution
facts, including original and final paths and move execution status. It does
not record hashes, fingerprints, or equivalent payload identity evidence.

A schema-v1 manifest can therefore say that Smart File Organizer recorded a
completed move from one path to another. A later filesystem observation can say
that a regular file currently exists at the recorded destination. Neither fact
proves that the current destination contains the same bytes that were moved
during the historical apply.

This ADR defines the product and architecture semantics required before a future
manifest schema may add identity evidence or any recovery mutation capability.

It does not change manifest schema version 1, add hashing, authorize recovery
execution, or define a user interface.

## Decision

### Verifiable trust is the governing recovery principle

Smart File Organizer must not require the user to trust an optimistic rollback
decision.

Recovery safety must be derived from evidence and current observations. When
the available evidence cannot demonstrate that recovery is safe, abstention is
the correct result.

The normative rule is:

> When Smart File Organizer cannot demonstrate that a recovery action is safe,
> it must not describe that action as safe and must not execute it.

Refusal, abstention, and unverifiable outcomes are successful safety-model
results. They are not degraded substitutes for a guessed recovery.

### Four distinct kinds of information

Recovery reasoning must preserve four separate concepts.

#### Historical fact

A historical fact is data durably recorded about an earlier apply operation.

Examples include:

- the manifest schema version;
- the recorded target root;
- the original source path;
- the final destination path;
- the execution status;
- timestamps and captured execution errors.

Historical facts describe what Smart File Organizer recorded about the past.
They must not be rewritten merely because the filesystem changes later.

A historical fact does not prove the current contents or identity of a path.

#### Current observation

A current observation is a read-only statement about filesystem state observed
at a particular time.

Examples include:

- whether the original path currently exists;
- whether the destination currently exists;
- whether an observed object has a supported filesystem type;
- whether a path currently crosses an unsafe symlink or containment boundary;
- whether observation failed or was indeterminate.

An observation describes the present at the time it was made. It does not
rewrite manifest history and does not by itself establish payload identity.

#### Identity evidence

Identity evidence is evidence capable of supporting a claim that bytes observed
now correspond to bytes recorded at an earlier trusted point in the workflow.

A pathname is not identity evidence.

File existence is not identity evidence.

File size alone is not sufficient identity evidence.

Schema version 1 contains no payload fingerprint and therefore provides no
basis for byte-level identity verification.

A future manifest schema may record identity evidence, but the exact algorithm,
fields, timing, performance policy, and symlink representation are outside this
ADR.

A future fingerprint must be described narrowly: it identifies bytes observed
under the defined fingerprinting procedure. It must not be described as a
permanent philosophical identity of a document or file.

#### Recovery-safety decision

A recovery-safety decision combines supported historical evidence, fresh
current observations, available identity evidence, path-safety checks, and
conflict checks.

It answers whether a reverse operation may be proposed as safe.

It must not infer missing evidence.

It must not treat manifest validity, path existence, or an earlier verification
result as mutation authority.

### Safe recovery

A reverse move may be classified as safe to recover only when all required
preconditions are demonstrably satisfied.

At minimum:

1. the historical manifest is valid under a supported schema;
2. the historical record establishes that the forward move completed;
3. that schema contains sufficient identity evidence for the supported identity
   claim;
4. the current recovery source can be freshly observed;
5. the current recovery source matches the recorded identity evidence;
6. the original source path is currently absent and available for restoration;
7. both recovery paths satisfy the active filesystem-safety and containment
   policy;
8. no path conflict, alias ambiguity, unsupported file type, or contradictory
   state exists;
9. every observation required for the decision succeeded;
10. the decision is based on observations current enough for the operation
    being authorized.

Failure to demonstrate any required precondition means recovery must be
`REFUSED`.

`SAFE_TO_RECOVER` means that a reverse move may be proposed as safe under the
current evidence and observations. It does not authorize filesystem mutation.

No combination of path existence alone is sufficient.

### Verification and recovery safety are separate state models

Current-state verification and recovery authorization represent different
questions and must not be collapsed into one state machine.

Verification asks questions such as:

- what currently exists;
- whether paths are safe to observe;
- whether identity evidence can be evaluated;
- whether current bytes match recorded evidence;
- whether state is missing, changed, conflicting, ambiguous, or unverifiable.

Recovery-safety classification asks:

- given the historical evidence and current verified observations, may a
  reverse move be proposed as safe?

A verification result is input to a recovery-safety decision. It is not itself
mutation authority.

Verification findings and recovery-safety decisions are separate.

Canonical verification semantics must be able to distinguish at least:

| Verification finding | Meaning |
| --- | --- |
| `IDENTITY_MATCH` | Current payload identity matches sufficient recorded evidence. |
| `IDENTITY_MISMATCH` | Current payload identity conflicts with recorded evidence. |
| `SOURCE_OCCUPIED` | The original source path is currently occupied. |
| `DESTINATION_MISSING` | The expected current recovery source is absent. |
| `BOTH_PRESENT` | Original and destination paths are both present. |
| `BOTH_MISSING` | Original and destination paths are both absent. |
| `UNSAFE_PATH` | A required path violates the active filesystem-safety policy. |
| `UNVERIFIABLE` | Required identity evidence or current observations are insufficient. |
| `AMBIGUOUS` | The available evidence supports more than one materially different interpretation. |

These are conceptual verification findings, not a required Python enum.

The recovery-safety decision has only two normative outcomes:

| Decision | Meaning |
| --- | --- |
| `SAFE_TO_RECOVER` | With the current evidence and observations, a reverse move may be proposed as safe. |
| `REFUSED` | Smart File Organizer cannot currently demonstrate that the reverse move is safe. |

`REFUSED` is not an error category. Its stable reason code and supporting
verification findings explain whether the cause is changed content, conflict,
missing state, ambiguity, unverifiability, unsafe paths, unsupported schema, or
another defined safety condition.

Neither outcome is mutation authority. `SAFE_TO_RECOVER` permits a recovery
proposal; any future execution still requires explicit authorization and fresh
safety-critical observations at the mutation boundary.

### Stable reason codes

Every recovery proposal, refusal, or abstention must expose a stable
machine-readable reason code.

Reason codes identify why the decision was reached; they are not free-form
human messages.

The initial normative reason-code vocabulary is:

| Reason code | Meaning |
| --- | --- |
| `recovery_preconditions_verified` | All evidence and current observations required to propose safe recovery are satisfied. |
| `identity_verified` | Current payload identity matches sufficient recorded evidence; this alone does not establish recovery safety. |
| `identity_unverifiable` | The available schema or evidence cannot support the required identity claim. |
| `destination_changed` | Current destination payload conflicts with recorded identity evidence. |
| `destination_missing` | The expected current recovery source is absent. |
| `source_conflict` | The original source path is occupied or otherwise unavailable for restoration. |
| `both_paths_present` | Original and destination paths are both present and the state cannot be safely reduced to one recovery interpretation. |
| `both_paths_missing` | Neither recorded path currently contains the expected object. |
| `unsafe_path` | A required path violates the active filesystem-safety policy. |
| `unsupported_file_type` | A required filesystem object has a type not permitted by the recovery contract. |
| `observation_failed` | A required filesystem observation could not be completed reliably. |
| `manifest_malformed` | The manifest cannot be validated as a supported historical record. |
| `manifest_schema_unsupported` | The manifest schema version has no explicit supported reader and semantics. |
| `historical_state_ambiguous` | Historical execution evidence is insufficient or contradictory for recovery reasoning. |
| `stale_observation` | Earlier observations cannot safely authorize a later mutation because relevant filesystem state may have changed. |

Future work may add reason codes when new supported distinctions are required.
Existing published meanings must not be silently repurposed.

### Human-readable explanations

Every recovery-safety result must also provide a concise human-readable
explanation.

The explanation must:

- state whether recovery is safe to propose or refused;
- explain the decisive reason without requiring the user to decode an enum;
- distinguish recorded historical facts from current observations;
- avoid claiming byte identity unless supported by identity evidence;
- avoid leaking raw inspected document contents.

Machine-readable reason codes and human-readable explanations serve different
purposes and both are required.

### Evidence and observations must remain inspectable

A recovery-safety decision must retain or expose enough structured information
to identify:

- the relevant historical move record;
- which historical fields were used;
- which identity evidence was available;
- which current paths were observed;
- the result of each required observation;
- the resulting reason code and recovery-safety disposition.

Rendering may summarize this information, but adapters must not invent stronger
claims than the underlying decision model supports.

### Manifest schema version 1 compatibility

Manifest schema version 1 remains a supported historical format.

It must remain readable according to its existing strict validation contract.

Version 1 records useful historical execution evidence, but it contains no
payload hash, fingerprint, or equivalent identity evidence. It must never be
retroactively interpreted as if such evidence existed.

Therefore a version-1 manifest cannot, under this ADR, demonstrate byte-level
identity between a historical moved payload and a current destination file.

Existing version-1 verification and recovery-planning behavior remains
historical product behavior. A version-1 manual reverse-move proposal based on
path reconciliation must not be relabeled as proof of `SAFE_TO_RECOVER`.

Future work may continue to expose cautious version-1 inspection or manual
recovery guidance, provided it remains explicit that identity is unverifiable.

### Unknown manifest schemas fail closed

Manifest schemas are independently versioned compatibility surfaces.

A reader must understand a schema version explicitly before using it for
verification or recovery-safety decisions.

An unknown future schema must be rejected as unsupported. Smart File Organizer
must not:

- guess that fields retain version-1 meaning;
- ignore unknown identity semantics;
- silently downgrade the schema;
- infer recovery authority from partially familiar fields.

Unknown schema semantics produce a fail-closed result.

Malformed manifests likewise cannot confer recovery authority.

### Threat and failure model

The recovery model must handle post-apply filesystem changes conservatively.

| Scenario | Required interpretation |
| --- | --- |
| Destination modified in place | If identity evidence no longer matches, classify changed and do not touch it. |
| Destination deleted | Recovery source is missing; do not invent a reverse move. |
| Destination replaced by another file | If replacement identity differs or cannot be established, do not touch it. |
| Original source recreated | Treat the original location as occupied; never overwrite it. |
| Source and destination both present | Treat as conflict or ambiguity unless stronger evidence resolves the state without risking user data. |
| Source and destination both absent | Treat as missing; no recovery mutation may be proposed. |
| Symlink or path topology changed | Treat unsafe or unverifiable according to path-safety policy; never follow a changed trust boundary optimistically. |
| Required observation fails | Treat as unverifiable or unsafe; observation failure is not equivalent to absence. |
| Manifest malformed | Reject it as historical authority. |
| Manifest schema unsupported | Fail closed; do not guess its semantics. |
| Destination contents changed but pathname is unchanged | Path equality does not override failed identity verification. |
| File metadata changed while payload bytes remain equal | Identity judgment depends only on the evidence explicitly defined by the supported schema; do not invent undocumented identity requirements. |
| Filesystem changes after verification | Earlier verification is stale for mutation authorization; required preconditions must be re-observed at the mutation boundary. |

### Verification is time-bound

Filesystem observations are facts about a particular observation event, not
leases on future state.

The filesystem may change after verification and before recovery planning or a
future recovery execution.

Consequently:

- a verification result must not grant durable mutation authority;
- recovery planning must remain non-mutating;
- any future recovery executor must re-check all safety-critical observable
  preconditions immediately before performing each consequential mutation;
- if state changes, the executor must refuse rather than rely on stale
  verification.

This is required even when an earlier verification classified the state as
safe.

### Mutation authority remains explicit and future work

This ADR authorizes no recovery mutation.

A future implementation of recovery execution, if separately approved, must
retain the existing project principles:

- explicit user authorization;
- no silent overwrite;
- fail-closed path safety;
- current precondition checks;
- truthful failure reporting;
- durable evidence;
- no inference of authority from an earlier successful stage.

The ability to verify a payload does not itself authorize moving it.

The ability to plan a recovery does not itself authorize executing it.

### Implications for a future manifest schema

A future manifest schema designed for verifiable recovery must provide
sufficient evidence to support the identity claim required by this ADR.

That future design must decide separately:

- the cryptographic fingerprint representation;
- any accompanying size or identity-related metadata;
- when fingerprinting occurs;
- pre-move and post-move semantics;
- symlink semantics;
- schema-version representation;
- compatibility with version 1;
- fingerprinting cost and performance policy.

Those are design questions for the Manifest v2 issue, not decisions made here.

Whatever representation is selected must preserve the semantic rule that a
fingerprint identifies the bytes observed under its defined procedure and does
not represent permanent document identity.

## Preserved invariants

This ADR does not weaken the invariants accepted by ADR 0001 or the current
repository contract:

- dry run by default;
- explicit apply;
- deterministic behavior and output where specified;
- no silent overwrite;
- target-root containment;
- failure-aware execution;
- durable recovery evidence;
- controlled diagnostics;
- ambiguity and abstention;
- privacy-safe explanations;
- continued readability of manifest schema version 1;
- fail-closed handling of unsupported manifest schemas;
- non-mutating verification and recovery planning.

## Consequences

The principal benefit is that recovery claims become auditable.

Smart File Organizer can distinguish:

1. what it recorded historically;
2. what it observes now;
3. what identity evidence supports;
4. what recovery action is demonstrably safe.

The principal cost is deliberate abstention.

Some historical manifests, especially schema version 1, cannot support a
positive safe-recovery classification because they lack identity evidence.
That limitation is truthful product behavior, not a reason to weaken the
contract.

Future APIs, CLI commands, and user interfaces must project this trust model
rather than invent alternate recovery semantics.

## Non-goals

This ADR does not:

- define Manifest v2 fields;
- select a hash algorithm;
- implement fingerprinting;
- modify manifest serialization;
- change schema-v1 parsing;
- implement recovery execution;
- add automatic rollback;
- add `recover --apply`;
- build or prototype a GUI;
- promise filesystem-wide atomicity;
- authorize overwrite;
- turn version-1 path reconciliation into identity verification.

## Rejected alternatives

### Treat destination existence as identity

Rejected because another payload may occupy the same pathname after the
historical apply.

### Treat schema-v1 recovery proposals as proof of safe recovery

Rejected because schema version 1 contains no identity evidence capable of
proving that the current destination still contains the historical payload.

### Optimistic recovery with warnings

Rejected because a warning does not prevent destructive mutation when identity
or conflict state is uncertain.

### Guess unknown schema semantics

Rejected because schema fields and identity guarantees may change between
versions. Unsupported schemas must fail closed.

### Verification as durable mutation authority

Rejected because filesystem state can change after observation. Safety-critical
state must be re-evaluated at the future mutation boundary.

### Automatic unconditional undo

Rejected because it conflicts with evidence-based recovery, no-overwrite
guarantees, ambiguity handling, and the governance rule in issue #80.

## Governance

Issue #80 establishes the following rule:

> No child issue may introduce an automatic recovery mutation until identity
> verification and recovery-safety classification have survived at least one
> released version.

This ADR preserves that rule.

No implementation derived from this ADR may use verification capability as a
shortcut around it.
