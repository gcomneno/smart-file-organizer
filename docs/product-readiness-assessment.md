# Product readiness assessment

## Document purpose

This document records the canonical product-readiness assessment for Smart File
Organizer at version `v0.3.3`. It evaluates whether the project is complete for
ordinary users, a developer-oriented minimum viable product, or an incomplete
laboratory project requiring further work. It also provides an evidence-based,
ordered roadmap without authorizing or implementing any proposed change.

| Field | Value |
| --- | --- |
| Assessment date | 2026-07-21 |
| Assessed version | `v0.3.3` |
| Assessed main commit | `ca421bb8ccf7f700ca2d77c49fa1514868dc4ac1` |
| Related issue | [#43](https://github.com/gcomneno/smart-file-organizer/issues/43) |

> [!IMPORTANT]
> All end-to-end and failure-mode checks used synthetic fixtures under `/tmp`.
> No private files or real document contents were inspected.

## Status legend

- **Blocker:** prevents safe product use or invalidates a central safety promise.
- **Important:** materially affects usability, reliability, supportability, or
  maintainability and should be addressed before a general-user release.
- **Useful:** a demonstrated improvement that is valuable but does not prevent
  the current limited workflow.
- **Optional:** reasonable only after higher-priority evidence-based work is
  complete.

## Executive verdict

**Verdict: incomplete laboratory project requiring additional work.**

Smart File Organizer has a credible and well-tested developer-oriented MVP at
its core, but it is not safe enough for ordinary users to apply to real file
collections. Three demonstrated blockers determine this verdict:

1. A configured destination such as `../../escaped` can move a file outside
   `--target`.
2. An explicitly supplied directory is accepted and moved recursively even
   though positional sources are documented as files.
3. An apply-time failure can occur after earlier moves have completed, leaving
   a partial result without a durable journal, recovery record, or undo
   information.

Until these blockers are resolved, the appropriate operational boundary is
synthetic or backed-up data, review of every dry run, and treatment of `--apply`
as experimental.

## Assessment scope and method

The assessment covered the complete tracked repository, including the README,
package metadata and lockfile, CI workflow, source modules, tests, example
configuration, Git history and tags, GitHub issue and release state, public CLI
help and diagnostics, package building and installation, and synthetic
end-to-end filesystem workflows.

Findings below use these labels:

- **Observed fact:** directly established by source inspection, repository or
  GitHub state, an automated check, or a synthetic execution.
- **Inference:** a conclusion supported by observed facts but not directly
  asserted by the software.
- **Recommendation:** a proposed change tied to a demonstrated product,
  operational, user, or maintenance problem.

## Intended audience and supported workflows

### Observed facts

- The README describes the project as a small Python CLI and a
  "clean-coding laboratory."
- The substantive public workflow is to build a move plan, optionally inspect
  supported document content, and optionally execute the plan with `--apply`.
- Dry run is the default, and content inspection is independently opt-in.
- Sources can be explicit positional paths or files collected from one source
  directory. Directory scanning is direct by default and recursive only with
  `--recursive`.
- Classification combines extension categories, semantic filename/path rules,
  and optional extracted document text.
- Built-in semantic destinations cover opinionated subjects such as Fastweb,
  Italian public benefits and tax documents, health, banking, vehicles, Kleis,
  Yocto, and `photos/2026`.
- User semantic rules extend built-ins and are evaluated after them; they do
  not override a built-in rule that already matches.

### Inference

The current product is best suited to a developer or technical owner adapting
an opinionated personal workflow. Its built-in taxonomy and development-checkout
installation path do not yet support a general ordinary-user audience.

## Confirmed strengths

- Dry run and content inspection are both opt-in.
- Existing destination files are not silently overwritten.
- Duplicate planned destinations fail by default.
- The optional rename strategy is deterministic and checks whether conflicts
  remain after renaming.
- Directory scans are sorted, making plan order reproducible.
- Text output is concise, and JSON preview provides source, destination, and
  category fields.
- Expected source-selection, configuration, and destination-conflict errors
  generally use readable `argparse` diagnostics.
- Classification, semantic rules, planning, configuration, content extraction,
  preview formatting, logging, and CLI orchestration have recognizable module
  boundaries.
- Runtime dependencies are limited to `pypdf`.
- The test suite is fast and extensive relative to the repository size.
- Synthetic TXT content inspection correctly influenced semantic routing.
- The package built as both an sdist and wheel, and the installed wheel exposed
  the public CLI outside the development checkout.
- Privacy defaults are conservative: inspection is local and opt-in, extracted
  content is not logged, and private/local experiment patterns are ignored.

## Functionality gaps

### Blocker: explicit directories are accepted and moved

**Observed fact:** Explicit sources are returned by CLI collection without a
file-type check. Apply validates `source.exists()` but not `source.is_file()` or
an explicit symlink policy.

**Evidence:** Applying a plan whose positional source was the synthetic
directory `/tmp/sfo-fixtures/explicit-dir/payload` moved the complete directory,
including its child file, to `target/other/payload`.

**Impact:** A typo or misunderstanding can move an entire directory tree,
contradicting the CLI description "Files to include in the organization plan."

**Recommendation:** Reject unsupported source types during planning and repeat
the invariant check immediately before apply. Define regular-file and symlink
behavior explicitly.

### Important: dry runs accept nonexistent explicit files

**Observed fact:** Source existence is checked during apply, not while building
a dry-run plan for explicit sources.

**Evidence:** A nonexistent synthetic path produced a plausible plan ending in
`documents/inbox/does-not-exist.txt`; apply would necessarily fail.

**Impact:** Preview output can appear executable when it is not.

**Recommendation:** Validate all explicit sources during planning and report
every invalid path clearly.

### Important: built-in classification is opinionated and non-overridable

**Observed fact:** Built-in rules contain locale- and collection-specific
destinations. Rules are first-match-wins, path matching includes parent path
components, and configured rules are appended after built-ins.

**Inference:** An unrelated parent directory can influence classification, and
a user cannot correct an applicable built-in classification with configuration.

**Recommendation:** Define the supported audience explicitly and allow an
applicable built-in rule to be overridden or disabled. Preview output should
identify which rule produced the destination.

### Useful: empty scans are silent

**Observed fact:** An empty source directory exits successfully without output.

**Recommendation:** Report that zero files were found so an empty successful
scan is distinguishable from an unintended source selection.

## Hardening and filesystem safety gaps

### Blocker: configured destinations can escape `--target`

**Observed fact:** Planning joins `target_root` and a configured `Path` without
validating that the configured folder is relative and contained beneath the
target. Absolute paths also discard the preceding target when joined by
`pathlib`.

**Evidence:** With `fallback_folder = "../../escaped"`, applying a synthetic
file under `/tmp/sfo-fixtures/escape/work/source` moved it to
`/tmp/sfo-fixtures/escape/escaped/plain.txt`, outside the requested
`/tmp/sfo-fixtures/escape/work/target`.

**Impact:** A malformed or untrusted configuration defeats the central
target-root safety boundary.

**Recommendation:** Require normalized relative destination folders, reject
absolute paths and `..`, resolve final destinations, and prove containment
beneath the resolved target before preview and apply.

### Blocker: partial apply has no durable recovery information

**Observed fact:** After limited preflight, moves run sequentially with
`shutil.move`. Destination directory creation and move operations have no
transaction, journal, rollback, or per-move result. The CLI returns nothing on
successful apply and does not translate all filesystem exceptions.

**Evidence:** A synthetic plan contained `a.jpg` followed by `b.txt`, with
`target/documents/inbox` pre-created as a file. `a.jpg` moved successfully to
`target/images/a.jpg`; creation of the second destination parent then raised a
raw `FileExistsError`; `b.txt` remained at its source; no durable record
described the partial state.

**Impact:** A collection can be split between source and target without an
authoritative recovery record.

**Recommendation:** Detect predictable parent/path failures during preflight,
record every completed move durably, and report completed, failed, and
unattempted operations with actionable recovery information. Filesystem-wide
atomicity should not be claimed.

### Important: successful apply has no manifest or audit record

**Observed fact:** A normal apply is silent unless verbose logging is enabled.
No persisted source-to-destination mapping is produced.

**Impact:** Successful moves, including conflict renames and flattened source
paths, cannot be reliably reconstructed or reversed.

**Recommendation:** Persist an apply manifest with source, final destination,
status, timestamp, and error state. An automated undo command can be considered
later; the manifest is the minimum recovery primitive.

### Important: a recursive source can contain its target

**Evidence:** After applying to `source/organized`, the next recursive dry run
included the already-organized file and planned a move whose source and
destination were identical.

**Impact:** Repeated runs can ingest their own output and produce confusing or
guaranteed-failure plans.

**Recommendation:** Reject target-equals-source and either reject or safely
exclude a target nested beneath a recursive source.

### Important: malformed PDFs produce raw tracebacks

**Evidence:** Inspecting a synthetic invalid PDF raised an uncaught
`pypdf.errors.PdfStreamError` and printed a full traceback.

**Impact:** One malformed document aborts the plan without an ordinary-user
diagnostic or a documented per-file fallback.

**Recommendation:** Adopt a documented fail-cleanly or warn-and-fallback policy.
Cover corrupt, encrypted, unreadable, and image-only PDFs.

### Important: symlink behavior is implicit

**Evidence:** A symlinked file was collected and the link itself was moved; its
referent remained in place. Directory symlinks, broken links, and cycles are
undocumented and untested.

**Recommendation:** Define, document, enforce, and test a consistent symlink
policy.

### Important: permission and cross-filesystem failures are not covered

**Observed fact:** `shutil.move` may copy and then remove a source when crossing
filesystems. The project has no tests or recovery state for permission failure,
source disappearance, full disks, interrupted copies, or source-removal failure.

**Inference:** Such failures can create partial or duplicate state that the
current `None`-returning executor cannot describe.

**Recommendation:** Add failure-oriented tests and ensure the execution result
and manifest represent each outcome truthfully.

### Useful: hidden files are included without explicit documentation

**Evidence:** A direct scan included `.hidden.pdf`.

**Recommendation:** Keep or change this behavior deliberately and document it.

### Useful: large scans and content inspection are eager

**Observed fact:** Recursive scans return a complete list, extracted text is
stored for every source, TXT files are read completely, and PDF extraction is
limited to the first three pages.

**Inference:** Memory and latency are unbounded for large trees and large text
files, although this assessment did not demonstrate an unacceptable threshold.

**Recommendation:** Establish practical benchmark limits before optimizing;
stream work only where measured evidence warrants it.

### Useful: portability is unverified beyond Linux

**Observed fact:** The implementation uses generally portable `pathlib` and
`shutil` APIs, but CI runs only Ubuntu with Python 3.12 while package metadata
declares Python 3.11 or newer.

**Inference:** Windows path rules, case-insensitive collisions, locked files,
and cross-volume behavior are not demonstrated.

**Recommendation:** Test the minimum supported Python version. Add operating
systems to CI only when they are claimed as supported.

## User experience gaps

### Important: ordinary-user installation and first run are absent

**Observed fact:** The README starts with `uv sync` and invokes the CLI through
`uv run`, requiring a checkout and development toolchain. The wheel installs
successfully, but no end-user acquisition or installation path is documented.

**Recommendation:** Provide one supported installed-user workflow, including a
clean-environment smoke test.

### Important: apply gives no success result

**Observed fact:** Without `--verbose`, successful apply produces no completion
summary. `--format json` applies only to dry runs.

**Recommendation:** Print a concise result containing move counts and the
durable manifest location.

### Important: failure presentation is inconsistent

**Observed fact:** Known application errors are readable, while malformed PDFs
and destination-parent failures produce Python tracebacks.

**Recommendation:** Translate expected extraction and filesystem failures into
consistent user-facing diagnostics, retaining technical detail under
`--verbose` when useful.

### Useful: two command styles dilute onboarding

**Observed fact:** Both `smart-file-organizer plan ...` and a legacy direct
planning form are supported and documented.

**Recommendation:** Use one canonical form in onboarding and label the other as
compatibility syntax.

### Useful: previews do not explain classification

**Observed fact:** Previews show paths and, in JSON, the broad category, but not
the matching semantic rule or fallback reason.

**Recommendation:** Add a classification reason to previews so users can review
opinionated first-match decisions safely.

## Packaging and distribution gaps

### Important: releases do not deliver installable artifacts

**Observed fact:** GitHub contains releases from `v0.1.0` through `v0.3.3`, but
the `v0.3.3` release has no attached assets. A standards-based local build did
successfully produce an sdist and wheel.

**Recommendation:** Select one supported distribution channel, automate artifact
building and clean-environment installation tests, and publish appropriate
checksums or provenance.

### Important: public package metadata is incomplete

**Observed fact:** Metadata includes the name, version, description, author,
Python requirement, dependency, README, and console entry point. It lacks
project URLs, an explicit metadata license expression, classifiers, and a
documented release procedure.

**Recommendation:** Complete provenance and discovery metadata as part of the
distribution work.

### Important: the declared Python range is not fully exercised

**Observed fact:** CI uses Ubuntu and Python 3.12 only; the package declares
Python `>=3.11`.

**Recommendation:** Add Python 3.11 to CI and retain a current development
version. Test other platforms only when support is claimed.

### Useful: development dependencies are not a pip extra

**Evidence:** `pip install -e '.[dev]'` warned that no `dev` extra exists because
development tools are defined in a dependency group.

**Recommendation:** Keep the current `uv` workflow if intentional, but do not
imply that a generic pip `dev` extra exists. Add one only if generic pip-based
development is deliberately supported.

## Documentation gaps

### Blocker: documented safety claims exceed demonstrated behavior

**Observed fact:** The README emphasizes safe execution and says every source is
checked before apply. It does not disclose directory-source moves, destination
escape, partial apply, or absence of durable recovery information. Dry run also
accepts nonexistent explicit sources.

**Recommendation:** After correcting the blockers, describe the exact preflight,
partial-failure, and recovery guarantees. Until then, avoid language implying
transactionality or comprehensive validation.

### Important: intended audience is ambiguous

**Observed fact:** The project is described both as a clean-coding laboratory
and as a safe organizer, while its rules reflect an opinionated personal and
Italian document taxonomy.

**Recommendation:** State whether the supported audience is the maintainer's
workflow, technical users adapting TOML, or general end users. Current evidence
supports only a developer-oriented audience after the blockers are fixed.

### Important: operational boundaries are undocumented

**Recommendation:** Document hidden-file behavior, symlink policy,
target-inside-source restrictions, malformed/encrypted/image-only PDF behavior,
the three-page PDF limit, unsupported formats, rule precedence, cross-filesystem
non-atomicity, and recovery expectations.

### Useful: release and installation verification are undocumented

**Recommendation:** Document an installed-command smoke test and a way to check
the installed version and package provenance.

## Architecture and refactoring assessment

### Important: execution needs a first-class result and journal boundary

**Observed fact:** `execute_plan(plan) -> None` cannot return per-move outcomes.
This limitation is directly exposed by silent success and partial failure.

**Recommendation:** Introduce an execution result containing completed, failed,
and unattempted moves, backed by a durable manifest. This is a demonstrated
responsibility correction, not a speculative abstraction.

### Important: path-safety policy needs a central boundary

**Observed fact:** Source selection is in the CLI, destination construction is
in planning, and limited validation is in execution. Required source-type and
destination-containment invariants are absent.

**Recommendation:** Centralize apply-time invariants in a validation component
used immediately before execution, with shared validation during preview where
appropriate.

### Useful: CLI orchestration is accumulating responsibilities

**Observed fact:** `cli.py` handles compatibility normalization, parsing, source
discovery, configuration conversion, planning selection, conflict resolution,
rendering, execution, and error translation.

**Recommendation:** Place new validation, execution-result, and recovery logic
in application services rather than continuing to expand `main`.

### Useful: the compatibility module exports private internals

**Observed fact:** `core.py` re-exports underscore-prefixed rule helpers and the
extension table.

**Recommendation:** Preserve required compatibility while defining a smaller,
documented public API before external consumers rely on internals.

### Optional: externalize built-in rules

Moving built-ins to data files might eventually ease maintenance, but rule
volume alone does not demonstrate a present problem. Defer this until audience,
override, and disable semantics are settled.

## Test quality and missing coverage

### Demonstrated quality

The 135-test suite covers:

- extension categories and representative semantic rules;
- path/content precedence and false-positive controls;
- configuration types, fallback folders, and invalid regular expressions;
- direct and recursive scans;
- duplicate destinations and deterministic renaming;
- dry-run behavior and successful apply;
- existing destinations and missing sources at execution;
- text and JSON previews;
- basic PDF extraction and parser-warning handling;
- CLI translation of known application exceptions.

### Important missing behavioral coverage

The missing tests correspond directly to demonstrated or credible filesystem
risks:

- rejection of explicit directories;
- destination traversal and absolute configured folders;
- target nested beneath source;
- partial apply after a later operation fails;
- durable apply manifest and recovery state;
- malformed, encrypted, unreadable, and image-only PDFs through the CLI;
- file symlinks, directory symlinks, broken links, and cycles;
- hidden files and documented inclusion policy;
- permission and destination-parent failures;
- case-insensitive destination collisions;
- sources changing between preview and apply;
- practical large-tree behavior;
- installed-wheel smoke testing;
- Python 3.11 and any claimed non-Linux platform.

The extensive semantic-rule examples do not replace failure-oriented filesystem
coverage, which is now the dominant product risk.

## Privacy and security assessment

### Observed strengths

- Content inspection is local and disabled by default.
- Logging records high-level events, not extracted contents.
- The repository ignores named local/private data paths and private PDF
  patterns.
- Tests and this assessment use synthetic inputs.

### Material risks

- **Blocker:** configuration path traversal can write outside the user's stated
  target boundary.
- **Blocker:** accepting directories can move more data than the interface
  claims.
- **Blocker:** partial execution without a durable record impairs safe recovery.
- **Important:** semantic built-ins reveal an opinionated personal-domain
  taxonomy. This is not private document content, but it should be consciously
  treated as public product behavior.
- **Important:** verbose tracebacks can reveal full local paths, although the
  implementation does not log extracted contents.

## Ordered roadmap

Each work unit is intended to remain independently reviewable. No roadmap issue
should be created until separately approved.

### 1. Enforce source and destination path invariants — blocker

Acceptance criteria:

- Positional directory sources are rejected before a plan is printed.
- Missing explicit sources fail during dry run.
- Configured destination folders reject absolute paths and `..`.
- Every resolved destination is proven to be beneath the resolved target root.
- Target-equals-source and recursive target-inside-source cases are rejected or
  safely excluded.
- Tests cover regular files, directories, missing paths, relative escapes,
  absolute folders, and the chosen symlink policy.

### 2. Make apply failure-aware and recoverable — blocker

Acceptance criteria:

- Preflight detects destination-parent components that are files or unusable.
- Every attempted move receives a recorded status.
- Partial failure reports completed, failed, and unattempted counts without a
  raw traceback.
- A durable JSON manifest records original and final paths.
- A synthetic failure after one successful move proves that the manifest is
  sufficient for manual recovery.
- Documentation explicitly avoids claiming filesystem-wide atomicity.

### 3. Define and enforce symlink and hidden-file policy — important

Acceptance criteria:

- The policy states whether file links are moved as links, dereferenced, or
  rejected.
- Directory symlinks, broken links, and cycles behave deterministically.
- Hidden-file inclusion is documented.
- Direct and recursive scan tests cover the selected behavior.

### 4. Harden content-inspection failures — important

Acceptance criteria:

- Corrupt, encrypted, unreadable, and image-only PDFs have documented outcomes.
- An extraction failure cannot emit an unhandled traceback.
- Diagnostics identify the synthetic path without logging document contents.
- Tests cover the selected fail-fast or warn-and-fallback behavior.
- Documentation states the three-page and no-OCR limitations accurately.

### 5. Clarify classification audience and override semantics — important

Acceptance criteria:

- Documentation identifies the intended audience and explains that defaults are
  opinionated.
- Users can override or disable an applicable built-in rule, or the product is
  explicitly limited to its built-in precedence.
- Preview output identifies the matched rule or fallback reason.
- Tests cover built-in/configured precedence and parent-directory influence.

### 6. Provide an ordinary-user install and first-run path — important

Acceptance criteria:

- One supported installation command works outside a source checkout.
- A clean-environment smoke test installs the built artifact and runs help, a
  dry run, and a synthetic apply.
- CI includes the minimum supported Python version.
- Release artifacts are reproducibly generated and attached or published
  through the documented channel.

### 7. Align CLI output and documentation with actual behavior — important

Acceptance criteria:

- Successful apply reports a concise result and manifest path.
- Empty scans report zero files.
- Expected parser and filesystem failures use consistent user-facing messages.
- Safety documentation matches actual preflight, partial-failure, and recovery
  semantics.
- One canonical command form is used in onboarding.

### 8. Add filesystem-risk regression coverage — important

Acceptance criteria:

- Tests cover parent-path failure, source disappearance, portable permission
  failures, target-inside-source, symlinks, hidden files, and case-collision
  policy.
- At least one test proves partial-failure reporting.
- CI runs the minimum Python version and the primary development version.
- Every claimed non-Linux platform is exercised in CI.

## Rejected or deferred items

- **OCR — deferred:** it is explicitly unsupported, and no evidence establishes
  it as necessary for the current MVP.
- **Additional document formats — deferred:** unsupported formats already fall
  back to filename classification; add formats only for demonstrated audience
  needs.
- **Machine-learning classification — rejected for now:** it would not resolve
  the demonstrated safety, recovery, or precedence defects.
- **GUI — rejected:** the evidenced blockers concern filesystem correctness,
  recovery, and installation rather than interface modality.
- **Cloud sync or remote classification — rejected:** this would expand privacy
  and operational risk without addressing current goals.
- **Filesystem-wide atomic transactions — rejected:** this is not a realistic
  cross-filesystem guarantee. Durable journaling and truthful recovery are the
  appropriate requirements.
- **Performance rewrite — deferred:** eager behavior is a risk, but no measured
  unacceptable threshold was demonstrated.
- **Broad architectural rewrite — rejected:** existing boundaries are serviceable;
  refactoring should be driven by validation, execution results, and recovery.
- **Auto-overwrite or deletion modes — rejected:** these would weaken the
  project's appropriate conservative defaults.
- **Automatic configuration discovery — deferred:** explicit `--config` remains
  clearer and safer while containment is unresolved.

## Commands and checks executed

### Repository and GitHub inspection

- `git status --short --branch`: clean `main` tracking `origin/main`.
- `git remote -v`: repository resolved to
  `gcomneno/smart-file-organizer`.
- `gh issue view 43 --json ...`: issue open with no labels or comments at the
  time of assessment.
- `git log`, `git tag --list`, `git ls-files`, and `git show`: history, tracked
  files, and tags through `v0.3.3` inspected.
- `gh release list`: six releases found from `v0.1.0` through `v0.3.3`.
- `gh release view v0.3.3 --json ...`: latest release present with no attached
  assets.
- `gh run list --workflow ci.yml --json ...`: the current `main` run completed
  successfully on 2026-07-21.
- README, configuration example, package metadata, lockfile, CI workflow,
  source modules, tests, ignore rules, and relevant Git history were inspected.

### Local quality, build, and installation checks

The documented `uv` commands were attempted first. The host's Snap-installed
`uv` refused to run because `snapd.apparmor` was unavailable. This was an
assessment-environment limitation, not a project check failure. Equivalent
checks then ran in isolated virtual environments under `/tmp`:

- `ruff format --check .`: `19 files already formatted`.
- `ruff check .`: all checks passed.
- `ty check --python /tmp/sfo-assessment-venv`: all checks passed.
- `python -m pytest -q`: `135 passed in 0.72s`.
- `python -m build --outdir /tmp/sfo-dist`: sdist and wheel built successfully.
- The wheel installed in a second clean virtual environment as version `0.3.3`.
- `smart-file-organizer --help` and `smart-file-organizer plan --help` succeeded
  from the installed wheel.

An initial `ty check` without the explicit isolated interpreter reported
unresolved third-party imports because it searched the system environment.
Pointing `ty` to the environment containing the declared dependencies produced
the passing result above.

### Synthetic CLI checks

All fixtures remained under `/tmp/sfo-fixtures`:

- Direct dry run classified uppercase `.JPG`, TXT, and a hidden PDF and excluded
  a nested file without `--recursive`.
- Recursive JSON dry run included the nested file and emitted structured output.
- TXT content inspection used synthetic Fastweb text to select a semantic
  destination.
- Malformed PDF inspection raised an uncaught `PdfStreamError` traceback.
- A nonexistent explicit source produced a dry-run plan instead of failing.
- An empty directory scan exited silently.
- Applying an explicit directory moved the complete directory tree.
- A `../../escaped` fallback moved a file outside `--target`.
- A two-file apply moved the first file, failed on the second destination parent,
  and produced no durable recovery record.
- Applying a symlink moved the link and left its referent in place.
- A recursive target beneath its source was included by the next scan and
  produced a same-source/same-destination plan.
- Final `git diff --check` and `git status` confirmed the assessed checkout was
  unchanged.

## Final product boundary

### Observed fact

The repository demonstrates a functional planning and classification core,
strong routine unit coverage, conservative overwrite defaults, and valid Python
package artifacts.

### Inference

Those strengths establish a developer-oriented MVP, but the three demonstrated
safety blockers prevent classification as a complete product for ordinary
users.

### Recommendation

Resolve roadmap units 1 and 2 before encouraging real-data use. Complete the
important hardening, UX, distribution, and documentation units before changing
the verdict to a general-user-ready product.
