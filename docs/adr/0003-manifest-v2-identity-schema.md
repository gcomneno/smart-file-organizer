# ADR 0003: Manifest v2 identity and fingerprint schema

- Status: Accepted
- Date: 2026-08-23
- Related issues: [#80](https://github.com/gcomneno/smart-file-organizer/issues/80), [#85](https://github.com/gcomneno/smart-file-organizer/issues/85)
- Depends on: [ADR 0002](0002-verifiable-recovery-contract.md)
- Italian mirror: [versione italiana](0003-manifest-v2-identity-schema.it.md)

## Context

ADR 0002 defines the normative recovery contract for Smart File Organizer.
Historical facts, current filesystem observations, payload identity evidence, and
recovery-safety decisions are separate concepts. A recovery action may be
classified `SAFE_TO_RECOVER` only when sufficient identity evidence and fresh
filesystem observations demonstrate the required safety preconditions.

Manifest schema version 1 records durable execution history but does not record
payload identity evidence. It therefore remains useful for historical inspection
and path reconciliation, but it cannot prove that bytes currently present at a
recorded destination are the bytes moved by the historical apply.

Issue #85 requires a persisted identity-evidence contract that can support later
current-state verification without changing apply behavior in this issue.

The existing executor uses `shutil.move()`. On the same filesystem this will
normally reduce to a rename, while across filesystem boundaries it may perform a
copy followed by source removal. A fingerprint captured only before the move
would therefore prove which source bytes were observed, but would not by itself
prove which bytes were present at the final destination after the move.

This ADR defines Manifest v2 at sufficient precision for a later writer issue.
It does not implement hashing, serialization, current-state verification,
recovery-safety classification, recovery execution, or a GUI.

## Decision

### Manifest v2 is an independently versioned persisted contract

Manifest v2 uses the existing top-level `schema_version` field with the integer
value `2`.

Package versions and manifest schema versions remain independent compatibility
surfaces. A package release may continue to read more than one manifest schema.
A package version change does not imply a manifest schema change, and a manifest
schema change must not be inferred from the package version.

Readers must dispatch explicitly by `schema_version`.

- `schema_version == 1` is interpreted only under the existing strict v1 contract.
- `schema_version == 2` is interpreted only under the v2 contract defined here.
- any other version is unsupported unless a reader for that exact version is
  deliberately implemented.

Unsupported versions fail closed with the established
`manifest_schema_unsupported` semantics. Readers must not guess that familiar
fields retain the same meaning in an unknown schema.

Within v2, the schema is strict. Unknown top-level fields, unknown move fields,
unknown identity-evidence fields, duplicate JSON keys, missing required fields,
and contradictory field combinations are validation failures. Extensibility is
provided by a later explicit schema version, not by silently accepting data with
unknown semantics.

### v2 preserves the v1 execution-history shape and adds identity evidence

Manifest v2 preserves the established top-level execution-history fields:

```text
schema_version
state
target_root
started_at
updated_at
finished_at
counts
moves
```

Each move preserves the established historical fields:

```text
original_path
final_path
category
status
timestamp
error
```

and adds exactly one new field:

```text
identity
```

`identity` is either `null` or a structured object containing sufficient
payload evidence for the historical completed move.

The initial v2 identity object is:

```json
{
  "algorithm": "sha256",
  "digest": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  "size_bytes": 12345,
  "source_observed_at": "2026-08-23T07:30:00+00:00",
  "destination_observed_at": "2026-08-23T07:30:01+00:00"
}
```

The identity object describes a successful two-sided payload observation. It
means that:

1. the source regular-file bytes were observed before the move;
2. those bytes produced the recorded SHA-256 digest and byte count;
3. after the move operation returned and the existing move postconditions were
   checked, the destination regular-file bytes were observed;
4. the destination produced the same SHA-256 digest and byte count;
5. the source and destination observations therefore support the historical
   claim that the completed move transferred the observed payload bytes.

The identity object does **not** mean that the destination will keep those bytes
forever. It is historical evidence captured during apply. Any later identity
claim requires a new current observation and comparison.

### SHA-256 is the initial fingerprint algorithm

The v2 algorithm identifier is the stable lowercase ASCII string:

```text
sha256
```

The digest is encoded as exactly 64 lowercase hexadecimal characters.

The algorithm is recorded per identity object even though schema v2 initially
permits only `sha256`. Recording it avoids hidden algorithm semantics and gives
future schemas an explicit migration boundary.

A v2 reader must reject an identity object whose `algorithm` is not `sha256`.
It must not attempt a best-effort interpretation, alias resolution, algorithm
substitution, or downgrade.

SHA-256 is selected because it is a standard cryptographic hash, is available
through Python's standard library, requires no network service or additional
runtime dependency, and provides a sufficiently strong byte-level fingerprint
for this product contract.

The fingerprint is not a digital signature and does not authenticate who
created the manifest.

### Identity evidence requires both pre-move and post-move observations

A successful v2 identity record requires two complete observations.

#### Source observation

Immediately before the consequential move for one item, the writer must observe
the source as a supported regular file and compute:

- SHA-256 over the complete byte stream;
- exact `size_bytes` over the same observed byte stream;
- `source_observed_at` after the observation completes successfully.

The timestamp represents completion of that observation. It is not a filesystem
mtime and must not be derived from file metadata.

#### Destination observation

After the move operation returns and the existing minimum postconditions have
succeeded, the writer must observe the final destination as a supported regular
file and compute the same values:

- SHA-256 over the complete destination byte stream;
- exact byte count over that same stream;
- `destination_observed_at` after the observation completes successfully.

The destination digest and size must equal the source digest and size before the
move can be recorded as `COMPLETED` with non-null identity evidence.

This two-sided rule is required because cross-filesystem moves may involve copy
and deletion rather than an atomic rename. The post-move observation verifies
the bytes that actually reached the final destination under the supported apply
procedure.

### A v2 `COMPLETED` move must carry complete identity evidence

For schema v2, a move with status `completed` must have a non-null, valid
`identity` object.

A move must not be recorded as `completed` under v2 merely because the pathname
transition succeeded. Completion under the v2 writer contract includes
successful payload evidence capture and equality of the source and destination
fingerprints.

For statuses `in_progress`, `failed`, and `unattempted`, `identity` must be
`null`.

This deliberately keeps the first v2 persisted contract binary and auditable:
identity evidence is either complete enough to support later byte-level
verification, or it is absent. v2 does not publish partial identity objects with
ambiguous evidentiary strength.

An implementation may hold temporary pre-move fingerprint data in memory while
an item is in progress, but it must not serialize that temporary observation as
completed identity evidence.

### Fingerprinting failure is an apply failure for that move

If the required source observation fails, the move must not be attempted. The
item becomes `failed` under the existing failure-aware execution model and
`identity` remains `null`.

If the filesystem object is no longer a supported regular file at the required
observation boundary, the move must fail closed.

If the move operation itself fails, the item remains `failed` and `identity`
remains `null`, regardless of any temporary source fingerprint previously
computed.

If the destination observation fails after the pathname mutation occurred, the
item must be recorded as `failed` with `identity: null`. The failure record must
truthfully report that the v2 completion contract was not established. The
existing manifest and filesystem reconciliation mechanisms remain responsible
for representing the resulting partial state; the writer must not relabel it as
completed merely because a destination path exists.

If the source and destination digests or sizes differ, the item must likewise be
recorded as `failed` with `identity: null`. A mismatch is a safety failure, not a
successful move with a warning.

Subsequent planned moves remain unattempted under the existing stop-at-first-
failure execution contract.

### v2 does not claim to eliminate all TOCTOU windows

The two-sided observation materially strengthens the historical claim, but it
does not make the filesystem transactional.

A file may change while being read for fingerprinting or between observations
because Smart File Organizer does not exclusively lock arbitrary user files.
The v2 contract therefore states only what was observed under the defined
procedure.

The writer must not claim that the source was immutable throughout the whole
operation.

At minimum, the implementation issue must ensure that each digest and size are
computed from the same open file stream and represent the bytes consumed by that
observation. If the operating system reports a read error or another condition
that prevents a complete observation, the observation fails.

The later verifier must still make a fresh observation of the current
recovery-source payload. A historical v2 identity object never becomes durable
mutation authority.

Any future recovery executor must re-observe all safety-critical filesystem
preconditions at the mutation boundary as required by ADR 0002.

### Identity evidence and convenience metadata remain distinct

Only the following v2 identity fields participate in payload-identity matching:

- `algorithm`;
- `digest`;
- `size_bytes`.

`source_observed_at` and `destination_observed_at` are historical observation
metadata. They establish when evidence was captured but do not strengthen or
weaken byte equality.

Paths, filenames, category, timestamps, filesystem mtime, inode number, device
number, ownership, permissions, and path existence are not payload identity
evidence under v2.

In particular:

- equal pathnames do not establish identity;
- equal file sizes without a matching digest do not establish identity;
- equal mtimes do not establish identity;
- equal inode/device metadata is not required for identity and must not be
  persisted as an identity requirement;
- changed metadata with unchanged bytes does not by itself imply an identity
  mismatch.

### Regular-file boundary

The initial v2 identity contract applies only to supported regular-file payloads.

A symlink is not fingerprinted by dereferencing it as if its target bytes were
the symlink payload. Directory payloads, device nodes, FIFOs, sockets, and other
special filesystem objects are outside the v2 identity contract.

Existing source/path-safety policy remains authoritative. If a required path
resolves to an unsupported object or violates the active safety boundary, the
writer must fail closed rather than manufacture identity evidence.

This ADR does not expand the set of filesystem object types that Smart File
Organizer may move.

### Canonical v2 field contract

The top-level v2 fields have the same meanings and validation constraints as v1
unless this ADR says otherwise.

The move-level contract is:

| Field | v2 contract |
| --- | --- |
| `original_path` | Canonical absolute historical source path under the existing path contract. |
| `final_path` | Canonical absolute destination path; must satisfy the existing target-root relationship. |
| `category` | Existing stable file-category value. |
| `status` | Existing execution status. |
| `timestamp` | Existing move-status timestamp semantics. |
| `error` | Existing error object semantics; required only for `failed`. |
| `identity` | Complete identity object only for `completed`; `null` otherwise. |

The identity-level contract is:

| Field | v2 contract |
| --- | --- |
| `algorithm` | Exactly `sha256`. |
| `digest` | Exactly 64 lowercase hexadecimal characters. |
| `size_bytes` | Non-negative JSON integer; booleans are invalid. |
| `source_observed_at` | Timezone-aware ISO-8601 timestamp within the manifest execution interval. |
| `destination_observed_at` | Timezone-aware ISO-8601 timestamp not earlier than `source_observed_at` and within the execution interval. |

For a completed move, its existing `timestamp` represents completion of the
move's full v2 execution contract and therefore must not be earlier than
`destination_observed_at`.

### Manifest-level consistency rules

A v2 manifest is malformed if any of the following are true:

- its field set is not exactly the supported v2 field set;
- its `schema_version` is not exactly `2`;
- its existing v1 state/count/timestamp/path invariants fail;
- a `completed` move has `identity: null`;
- a non-completed move has non-null identity data;
- an identity object has unknown or missing fields;
- `algorithm` is not `sha256`;
- `digest` is not exactly canonical lowercase SHA-256 hex;
- `size_bytes` is negative, non-integer, or boolean;
- either observation timestamp is missing, naive, outside the manifest execution
  interval, or ordered incorrectly;
- the move completion timestamp precedes the destination observation;
- the destination path violates the existing target-root safety relationship;
- error/status combinations contradict the existing execution model.

The reader validates persisted structure and historical consistency. It does not
recompute historical hashes while parsing the manifest.

### Representative v2 manifest

The following is explanatory and illustrates the normative field contract:

```json
{
  "schema_version": 2,
  "state": "completed",
  "target_root": "/home/example/organized",
  "started_at": "2026-08-23T07:30:00+00:00",
  "updated_at": "2026-08-23T07:30:01+00:00",
  "finished_at": "2026-08-23T07:30:01+00:00",
  "counts": {
    "completed": 1,
    "failed": 0,
    "in_progress": 0,
    "unattempted": 0
  },
  "moves": [
    {
      "original_path": "/home/example/inbox/report.pdf",
      "final_path": "/home/example/organized/documents/report.pdf",
      "category": "documents",
      "status": "completed",
      "timestamp": "2026-08-23T07:30:01+00:00",
      "error": null,
      "identity": {
        "algorithm": "sha256",
        "digest": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        "size_bytes": 12345,
        "source_observed_at": "2026-08-23T07:30:00+00:00",
        "destination_observed_at": "2026-08-23T07:30:01+00:00"
      }
    }
  ]
}
```

### v1 compatibility is preserved without retroactive evidence

Manifest v1 remains readable by the v1 reader under its existing exact schema
and validation rules.

A v1 move never gains an `identity` object by inference.

A reader, migration command, verifier, or recovery planner must not hash a
current v1 destination and present that result as identity evidence captured by
the historical apply. Such a hash would be a current observation, not a
historical fact.

When later identity verification requires historical payload evidence, a v1
record produces the ADR 0002 `identity_unverifiable` semantics rather than a
guessed positive identity result.

There is no in-place v1-to-v2 historical upgrade procedure under this ADR.

### Manifest authenticity is outside v2

Manifest v2 does not add a manifest checksum, MAC, or digital signature.

The manifest is treated as locally persisted historical evidence under the same
storage trust boundary as v1. The identity hash answers whether observed payload
bytes match recorded payload bytes; it does not prove that the manifest itself
was authored by Smart File Organizer or has not been edited by an actor with
write access to the manifest.

Adding manifest authenticity would require a separate threat model, key or
trust-anchor design, rotation/recovery policy, and user-facing verification
contract. It is intentionally outside the current product requirement and must
not be implied by the word "verifiable".

A malformed or internally contradictory manifest still fails closed.

### Privacy implications

v2 stores no file contents and no extracted document text.

SHA-256 digests are one-way fingerprints rather than plaintext, but they are not
privacy-neutral. A party that already possesses or can guess candidate content
may hash that content and compare the result. Therefore manifests remain
potentially sensitive metadata and should be protected with the same care as the
historical paths they already contain.

No network service is required or permitted for v2 fingerprinting.

### Performance implications

A completed v2 move requires reading the complete payload twice: once at the
source and once at the destination.

This is deliberate. The product chooses a stronger historical transfer claim
over a cheaper but incomplete pre-move-only fingerprint.

The implementation issue may use bounded-memory streaming and an appropriate
chunk size, but it must not weaken the contract by sampling only part of a file,
skipping the post-move observation, or silently disabling hashing above a size
threshold.

If complete fingerprinting cannot be performed, the move cannot satisfy v2
completion semantics.

Performance optimization based on measured evidence may be proposed separately,
provided it preserves equivalent identity guarantees.

## Failure and threat model

| Scenario | Required v2 interpretation |
| --- | --- |
| Source unreadable before move | Fail the move; do not mutate; `identity: null`. |
| Source changes while being fingerprinted | The hash represents bytes read by that observation; read failure aborts. The contract does not claim exclusive immutability. |
| Source changes after pre-move observation but before move | Post-move mismatch causes failure; no completed identity evidence is published. |
| Same-filesystem rename | Post-move fingerprint still required for the v2 completion contract. |
| Cross-filesystem copy/delete move | Post-move fingerprint required; source and destination fingerprint/size must match. |
| Move operation fails | Record existing failure semantics; `identity: null`. |
| Destination unreadable after move | Record failed v2 completion; `identity: null`; preserve truthful partial-state evidence. |
| Destination hash differs | Record failed v2 completion; never downgrade to warning. |
| Destination later modified or replaced | Historical v2 identity remains unchanged; later verifier returns mismatch when current evidence differs. |
| Destination later deleted | Historical v2 identity remains unchanged; current observation reports missing state. |
| Original source recreated | Historical identity does not authorize overwrite; later recovery safety must refuse the conflict. |
| Unsupported algorithm in purported v2 data | Manifest malformed/unsupported for identity use; fail closed. |
| Malformed digest or contradictory identity fields | Manifest malformed; fail closed. |
| Symlink or special file at observation boundary | Unsupported/unsafe; fail closed. |
| Very large payload | Full streaming fingerprint still required; no silent sampling or size-based bypass. |
| Manifest edited after apply | v2 provides no authenticity guarantee; internal validation may detect contradictions but a valid-looking edit is outside this threat contract. |

## Consequences

The primary benefit is that a completed v2 move carries enough historical
identity evidence for a later verifier to compare current destination bytes with
the bytes observed during the original apply.

The two-sided observation also gives the historical record a stronger meaning
across both rename-style and copy/delete-style moves.

The cost is additional I/O and a stricter definition of successful apply. A move
whose pathname mutation succeeded but whose post-move fingerprint cannot be
established is a failed v2 apply item, because the product cannot truthfully
claim verifiable completion.

This stricter behavior is intentional and is compatible with the governing
principle from ADR 0002: missing evidence must not be upgraded into trust.

## Implementation constraints for the next issue

The Manifest v2 writer issue must preserve the following boundaries:

- no change to the meaning or readability of existing v1 manifests;
- no hashing during dry-run planning;
- fingerprint only as part of explicit apply;
- complete streaming SHA-256 and byte counting;
- source observation immediately before each consequential move;
- destination observation after move postconditions;
- equality required before `COMPLETED` is persisted;
- `identity: null` for every non-completed record;
- atomic durable manifest updates remain in place;
- stop-at-first-failure behavior remains in place;
- no current-state verifier or recovery-safety classifier hidden in the writer;
- no `recover --apply` or automatic rollback.

The implementation may refine private types and helper names, but it must not
change these persisted semantics without a new architecture decision.

## Preserved invariants

This ADR preserves:

- dry run by default;
- explicit apply;
- deterministic persisted representation;
- no silent overwrite;
- target-root containment;
- failure-aware execution;
- durable recovery evidence;
- controlled diagnostics;
- privacy-safe explanations;
- strict v1 readability;
- fail-closed handling of unknown schemas;
- abstention when evidence is insufficient;
- no recovery mutation authority from historical evidence alone.

## Non-goals

This ADR does not:

- implement the Manifest v2 writer;
- compute hashes in production code;
- change current apply behavior;
- change v1 serialization or validation;
- define current-state identity verification implementation;
- implement recovery-safety classification;
- change recovery planning;
- define recovery execution;
- add automatic rollback;
- add `recover --apply`;
- add a GUI;
- add manifest signing or authenticity guarantees;
- add remote storage, network services, or external hashing services.

## Rejected alternatives

### Pre-move fingerprint only

Rejected because it proves which source bytes were observed but does not prove
which bytes reached the final destination, especially when a move crosses
filesystems and becomes copy/delete.

### Post-move fingerprint only

Rejected because it records the destination bytes after the operation but does
not independently bind them to the bytes observed at the source immediately
before the move.

### File size plus metadata instead of a cryptographic hash

Rejected because size, mtime, inode, device number, and path metadata do not
provide the required byte-level identity evidence.

### Optional hashing only for small files

Rejected because the same `COMPLETED` state would then carry different identity
guarantees depending on file size. v2 requires one auditable semantic contract.

### Partial/sampled hashing

Rejected because sampling weakens the identity claim and creates unnecessary
algorithmic ambiguity for the initial schema.

### Persist partial pre-move evidence on failed records

Rejected for v2 because it would introduce multiple evidence-strength states
before the verifier and recovery classifier exist. The first v2 contract keeps
published identity evidence complete or absent.

### Treat SHA-256 as manifest authenticity

Rejected because a payload digest does not authenticate the manifest or its
author. Authenticity requires a separate threat and key-management model.

## Follow-up

After this ADR is accepted, the next focused issue should implement Manifest v2
writing during explicit apply, preserving v1 readability and the existing
failure-aware execution model.
