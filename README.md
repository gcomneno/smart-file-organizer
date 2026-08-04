# smart-file-organizer

[![CI](https://github.com/gcomneno/smart-file-organizer/actions/workflows/ci.yml/badge.svg)](https://github.com/gcomneno/smart-file-organizer/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

A safe Python CLI for ordinary users and developers who want to preview and apply deterministic file-organization plans.

The project organizes files by building a safe plan first. By default it only prints what it would do. Files are moved only when `--apply` is explicitly passed.

## Project status

The current released baseline is v0.4.2. Its operational behavior and
limitations are documented in this README. The approved forward architectural
direction is [ADR 0001](docs/adr/0001-evolution-architecture.md), and roadmap
implementation is tracked in [issue #67](https://github.com/gcomneno/smart-file-organizer/issues/67).
The [product readiness assessment](docs/product-readiness-assessment.md) is
retained as the historical v0.3.3 assessment; its verdict does not describe
the current v0.4.2 baseline.

## Current features

- Classifies files by extension and semantic filename/path rules.
- Can inspect supported document content with `--inspect-content`.
- Builds an organization plan.
- Reads explicit source files or direct files from a source directory.
- Prints the plan by default, without moving files.
- Applies the plan only with `--apply`.
- Creates target directories when applying.
- Refuses destination conflicts.
- Refuses to overwrite existing files.
- Reports CLI errors in a readable way.
- Uses project-local tooling with `uv`.
- Uses `ruff` for formatting and linting.
- Uses `ty` for static type checks.
- Uses `pytest` for tests.

## Installation

GitHub Releases is the supported distribution channel. Releases provide a
pure-Python wheel, a source distribution, and SHA-256 checksums.

Requirements:

- Linux;
- Python 3.11 or Python 3.12;
- `uv` for isolated command installation.

Install version `0.4.2` directly from its release wheel:

~~~bash
uv tool install "https://github.com/gcomneno/smart-file-organizer/releases/download/v0.4.2/smart_file_organizer-0.4.2-py3-none-any.whl"
~~~

Verify the installed version and provenance:

~~~bash
smart-file-organizer --version
uv tool list
~~~

Expected output:

~~~text
smart-file-organizer 0.4.2
~~~

Start with a dry run. Create a sample text file, then run:

~~~bash
smart-file-organizer plan \
  --from "$HOME/smart-file-organizer-first-run/source" \
  --target "$HOME/smart-file-organizer-first-run/organized"
~~~

The preview does not move the file. Review it before repeating the command with
`--apply`.

Each release includes `SHA256SUMS`. Verify downloaded package artifacts with:

~~~bash
sha256sum --check SHA256SUMS
~~~

The complete release procedure is documented in
[docs/releasing.md](docs/releasing.md).

## Development setup

Install dependencies and create the local virtual environment:

~~~bash
uv sync
~~~

Run the test suite:

~~~bash
uv run python -m pytest
~~~

## Provisional Python API

The supported Python import path is `smart_file_organizer.api`. This Python API
is provisional before 1.0 and until it has survived at least one release cycle.
The CLI remains the most stable user-facing contract; the Python API is
separately governed. Manifest schema compatibility is independently versioned.

Internals, including `core.py` and implementation modules, may change without
compatibility guarantees. Configure planning with
`PlanOrganizationRequest.config_path`. Always inspect an `OrganizationPlan`
before explicitly calling `apply_organization`.

The normative export set is `smart_file_organizer.api.__all__` and is protected
by contract tests. The installed package includes a `py.typed` marker for its
inline type annotations. Controlled planning and apply errors are exported from
the same API module so callers do not need to import implementation modules.

<!-- python-api-example:start -->
~~~python
from pathlib import Path
from tempfile import TemporaryDirectory

from smart_file_organizer.api import (
    ClassificationOutcome,
    EvidenceSource,
    PlanOrganizationRequest,
    TaxonomyProfileName,
    apply_organization,
    plan_organization,
)


with TemporaryDirectory() as temporary_directory:
    workspace = Path(temporary_directory)
    source = workspace / "fastweb-note.txt"
    target = workspace / "organized"
    source.write_text("A temporary note.", encoding="utf-8")

    request = PlanOrganizationRequest(
        explicit_sources=(source,),
        source_root=None,
        recursive=False,
        target_root=target,
        config_path=None,
        inspect_content=False,
        conflict_strategy="fail",
        profile=TaxonomyProfileName.PERSONAL_IT,
    )
    plan = plan_organization(request)

    move = plan.moves[0]
    assert move.classification is not None
    assert move.classification.outcome is ClassificationOutcome.SELECTED
    assert move.classification.taxonomy_profile is TaxonomyProfileName.PERSONAL_IT
    assert move.classification.selected_candidate is not None
    assert move.classification.candidates == (move.classification.selected_candidate,)
    assert (
        move.classification.selected_candidate.evidence[0].source
        is EvidenceSource.FILENAME
    )
    print(move.source, move.destination, move.classification.folder)

    result = apply_organization(plan)
    assert result.successful
    assert result.manifest_path.is_file()
~~~
<!-- python-api-example:end -->

Run formatting and linting checks:

~~~bash
uv run ruff format --check .
uv run ruff check .
uv run ty check
~~~

Format the project:

~~~bash
uv run ruff format .
~~~

## Usage

### Dry run from explicit files

~~~bash
uv run smart-file-organizer plan --target organized photo.jpg notes.txt script.py
~~~

Example output:

~~~text
photo.jpg -> organized/images/photo.jpg
notes.txt -> organized/documents/inbox/notes.txt
script.py -> organized/code/script.py
~~~

This does not move files.

### Dry run from a directory

~~~bash
uv run smart-file-organizer plan --from /path/to/source --target /path/to/organized
~~~

The command scans only direct files in the source directory by default.

This does not move files.

### Recursive directory scan

Use `--recursive` with `--from` to include files from nested directories:

~~~bash
uv run smart-file-organizer plan --from /path/to/source --recursive --target /path/to/organized
~~~

Only files are included; directories themselves are not moved.

The target must differ from the scanned source directory. With `--recursive`,
the target must also not be nested beneath the source directory.

### Dry run with content inspection

~~~bash
uv run smart-file-organizer plan --inspect-content --from /path/to/source --target /path/to/organized
~~~

This opt-in mode extracts text from supported documents and uses that text when building the plan.

It is disabled by default. Start with a dry run before combining it with `--apply`.

Currently supported document text sources:

- `.txt` files;
- `.pdf` files, using the first pages only.

PDF content inspection works only for PDFs with extractable text. OCR for scanned documents is not implemented yet.

Third-party PDF parser warnings are suppressed by default. Use `--verbose` to show them.

Content-based semantic matching is stricter than filename matching: generic single-word keywords are ignored, and remaining single-word matches require whole-word hits in the extracted text.

Whole-line absolute filesystem filename references, and routing lines that
contain an absolute path start, are excluded from semantic content matching to
avoid incidental report or log matches. Remaining descriptive lines continue
through deterministic matching; filename and parent-path classification are
unaffected.

### Apply the organization plan

~~~bash
uv run smart-file-organizer plan --from /path/to/source --target /path/to/organized --apply
~~~

This moves files into category directories under the target root.

Example target layout:

~~~text
/path/to/organized/
├── code/
│   └── script.py
├── documents/
│   └── notes.txt
└── images/
    └── photo.jpg
~~~

## Command layout

The canonical command form is `smart-file-organizer plan ...`:

~~~bash
uv run smart-file-organizer plan --target organized photo.jpg
~~~

Planning remains safe by default: it prints the move plan without moving files.

Use `--apply` explicitly to execute the plan:

~~~bash
uv run smart-file-organizer plan --from Downloads --target organized --apply
~~~

Direct planning options without the `plan` command remain supported only as
compatibility syntax for existing scripts. New documentation and automation
should use the canonical command form:

~~~bash
uv run smart-file-organizer --target organized photo.jpg
~~~

## Operational boundaries

The main safety and behavior contracts are documented in these owning sections:

- [Safety behavior](#safety-behavior): dry-run default, preflight checks,
  destination containment, and overwrite refusal;
- [Content-inspection limits and failure policy](#content-inspection-limits-and-failure-policy):
  supported formats, three-page PDF limit, no OCR, and warn-and-fallback
  behavior;
- [Symlink and hidden-file policy](#symlink-and-hidden-file-policy): inclusion,
  traversal, and move semantics;
- [Apply results and recovery manifests](#apply-results-and-recovery-manifests):
  durable evidence, partial failure, manual recovery, and the absence of
  filesystem-wide atomicity;
- [Classification audience, precedence, and explanations](#classification-audience-precedence-and-explanations):
  path context, inspected content, built-ins, configured rules, and overrides.

Expected input, configuration, parser, and preflight failures exit with status
`2` and one concise error line. A partial apply or manifest-persistence failure
exits with status `1`. Successful commands exit with status `0`. Expected
failures do not print Python tracebacks.

## Safety behavior

The default mode is a dry run. Files are moved only with `--apply`.

Content inspection is also opt-in. Document text is read only when `--inspect-content` is explicitly passed.

Before applying a plan, the program checks that:

- no two source files would be moved to the same destination;
- every source is a regular file or a symlink to a regular file;
- every resolved destination remains beneath the resolved target root;
- no destination file already exists.

Explicit positional sources are validated before a preview is printed.
Configured destination folders must be normalized relative paths and cannot
contain `..` components. Resolved destination containment is checked both while
planning and again immediately before applying a plan.

If any of these checks fail, the command stops with an error.

Destination conflicts fail by default. With `--conflict-strategy rename`, the
first source in deterministic path order keeps the original filename. Later
sources use a sanitized immediate-parent suffix such as `__folder-b`; repeated
suffixes receive stable numeric extensions such as `__device-2`. The resolver
also reserves every destination already present in the plan, so generated names
cannot silently replace another planned destination.

## Content-inspection limits and failure policy

Content inspection remains opt-in through `--inspect-content`.

The supported inspection formats are:

- UTF-8 text files, read with replacement for invalid byte sequences;
- PDF files, limited to the first three pages.

Other file formats are not opened for content inspection and continue through
filename-based classification.

PDF inspection does not perform OCR. A PDF containing only scanned images, or
pages from which the parser returns no text, therefore produces a concise
warning and falls back to filename classification.

Corrupt, encrypted, unreadable, and otherwise parser-rejected PDFs follow the
same **warn-and-fallback** policy:

- the CLI identifies the affected path;
- the default output suppresses parser warnings and raw tracebacks;
- filename classification continues with empty extracted text;
- `--verbose` adds the parser error class but never logs extracted contents.

The fallback does not silently claim that inspection succeeded. It preserves
the ordinary filename rules while making the degraded outcome visible.

## Symlink and hidden-file policy

Source handling follows one deterministic policy during collection, preview,
and apply:

- regular files are included;
- symlinks to regular files are included and moved as symbolic links;
- file symlinks are not dereferenced and their referent is not moved;
- directory symlinks are never traversed;
- a directory symlink cannot be used as the `--from` scan root;
- broken symlinks are rejected when passed explicitly and ignored during scans;
- hidden files are included in both direct and recursive scans;
- hidden directories are traversed when `--recursive` is enabled.

Recursive traversal explicitly checks symbolic links before considering a path
as a directory. Directory-link cycles therefore cannot cause recursive
traversal or duplicate discovery.

Moving a file symlink preserves the link object and its stored target text.
An absolute link therefore continues to identify the same absolute target.
A relative link can resolve differently after being moved into another
directory and may become broken. The organizer does not silently rewrite,
dereference, or repair relative symlinks.

## Apply results and recovery manifests

Every `--apply` execution creates a JSON manifest beneath the target root:

~~~text
<target>/.smart-file-organizer/manifests/apply-<timestamp>-<id>.json
~~~

A successful apply prints a concise result:

~~~text
Apply result: completed=2 failed=0 unattempted=0
Manifest: /absolute/path/to/organized/.smart-file-organizer/manifests/apply-....json
~~~

The manifest is created before the first move and atomically updated before and
after every attempted filesystem operation. Each record contains the original
path, final path, category, status, timestamp, and any captured error.

The durable statuses mean:

- `completed`: the move returned successfully and the final path was observed;
- `failed`: the attempted move raised an expected filesystem error;
- `unattempted`: execution stopped before this move was attempted;
- `in_progress`: execution or manifest persistence was interrupted while the
  move required investigation.

Execution stops at the first move failure. The CLI reports completed, failed,
and unattempted counts, prints the manifest path, and exits unsuccessfully
without a Python traceback.

The manifest is recovery evidence, not an automatic rollback mechanism. For
manual recovery:

1. inspect both `original_path` and `final_path` for every non-unattempted entry;
2. treat `completed` entries as files expected at `final_path`;
3. treat `failed` and `in_progress` entries as requiring inspection of both
   locations;
4. move completed files back only after confirming that restoring
   `original_path` will not overwrite another file.

Filesystem-wide atomicity is not guaranteed. In particular, `shutil.move` may
perform a copy followed by source removal across filesystems. A process crash,
full disk, permission change, or external filesystem mutation can therefore
leave partial or duplicated state. The manifest records the strongest evidence
available; it does not claim a transaction or automatic undo.

## Destination conflicts

By default, the planner stops when two source files would move to the same destination.

Use `--conflict-strategy rename` to resolve simple filename collisions with deterministic renamed destinations:

~~~bash
uv run smart-file-organizer plan \
  --conflict-strategy rename \
  --target organized \
  folder-a/photo.jpg \
  folder-b/photo.jpg
~~~

Example output:

~~~text
folder-a/photo.jpg -> organized/images/photo.jpg
folder-b/photo.jpg -> organized/images/photo__folder-b.jpg
~~~

The first source in sorted order keeps the original destination name. Additional conflicting files receive a suffix derived from their source path.

## Output format

### Empty scans

A text preview from an empty source directory reports the result explicitly:

~~~text
No files found.
~~~

JSON preview keeps its structured contract and returns an empty array:

~~~json
[]
~~~

An empty `--apply` still creates a recovery manifest and reports
`completed=0 failed=0 unattempted=0`. No source file is moved.

By default, `plan` prints one move per line:

~~~text
photo.jpg -> organized/images/photo.jpg
~~~

Use `--format json` for structured preview output:

~~~bash
uv run smart-file-organizer plan --format json --target organized photo.jpg notes.txt
~~~

Example JSON output:

~~~json
[
  {
    "source": "photo.jpg",
    "destination": "organized/images/photo.jpg",
    "category": "images"
  },
  {
    "source": "notes.txt",
    "destination": "organized/documents/inbox/notes.txt",
    "category": "documents"
  }
]
~~~

JSON preview applies to dry-run output only. `--apply` does not print the plan.

## Configuration

You can pass an optional TOML configuration file with semantic destination rules:

~~~bash
uv run smart-file-organizer plan \
  --config smart-file-organizer.example.toml \
  --target organized \
  synthetic-invoice.pdf
~~~

Example configuration:

~~~toml
[[semantic_rules]]
folder = "documents/demo-utility"
keywords = ["synthetic invoice", "demo utility"]

# Optional regex patterns match normalized path text.
# Separators such as "_", "-", and "." become spaces before matching.
[[semantic_rules]]
folder = "documents/demo-dated-reports"
patterns = ["\\d{8} demo report \\d+"]
~~~

Each rule must define `keywords`, `patterns`, or both. Regex patterns apply to
normalized filename/source-path and inspected-content matching; content regex
matches are supporting evidence rather than a standalone strong selection.

Single-word keywords match as whole tokens in normalized path text, so short acronyms such as `adi` do not match inside unrelated words like `paradiso`. Multi-word phrases still use substring matching because they are already specific enough.

Existing configurations remain compatible: when no new policy fields are present, built-in rules are evaluated before configured rules exactly as in earlier versions.

When a keyword from either built-in or configured rules matches the file path or inspected document text, the matching folder is used as the destination subfolder.

Use `fallback_folder` to send unmatched documents to a dedicated inbox. It defaults to `documents/inbox`:

~~~toml
fallback_folder = "documents/inbox"
~~~

The fallback applies only to documents without a semantic match. Other categories such as images, audio, and `other` keep their default folders.

## Classification audience, precedence, and explanations

The built-in taxonomy is deliberately opinionated. It targets individual
desktop and workstation users organizing mixed local files such as personal
administration, utilities, taxes, health documents, learning material, books,
media, and source code.

It is not intended to be a universal records-management taxonomy, an enterprise
document-management system, or a machine-learning classifier. A preview should
always be reviewed before applying moves to a collection with different naming
conventions.

### Deterministic precedence

Semantic classification gathers every meaningful candidate before selecting a
destination. Evidence has three discrete strengths: `weak`, `supporting`, and
`strong`; it never uses floating-point confidence. Filename and source-path
signals are strong. An exact multi-word content phrase is strong, one content
token is weak, two distinct content indicators for one candidate combine to
strong, and a content regex is supporting. Duplicate or overlapping indicators
are counted once.

Candidates are ranked deterministically by:

1. aggregate evidence strength;
2. configured-versus-built-in precedence tier;
3. presence of descriptive filename/source-path evidence;
4. explicit reviewed taxonomy priority, when the profile supplies one;
5. evidence-source diversity;
6. distinct evidence count;
7. stable rule ID and destination only for deterministic ordering.

Taxonomy priority resolves reviewed `personal-it` built-in overlaps. It is not
generic confidence and does not resolve equal configured candidates. Equal
strong candidates in the same precedence tier and different folders are
`ambiguous`; only weak/supporting semantic candidates are `abstained`. Both
route to the fallback without dropping their candidate graph. Clear semantic
candidates are `selected`; the remaining outcomes are `extension`,
`special_case`, and `fallback`.

Extracted text is never retained in plans, logs, explanations, or manifests.
Routing lines and whole absolute filename references in extracted text are not
descriptive evidence. Explain output can include configured keywords or regex
patterns, but never arbitrary matched document text or excerpts.

The `personal-it` profile is the compatibility default and contains the current
opinionated built-ins. The `minimal` profile contains no personal semantic rules:
it conservatively applies configured rules, extension categories, special cases,
and fallback. Choose a profile with `--profile minimal` or
`--profile personal-it`, `profile = "minimal"` in TOML, or
`PlanOrganizationRequest(profile=TaxonomyProfileName.MINIMAL)`. Explicit
CLI/Python selection wins over configuration, which wins over the default.

Configured rules layer over either profile. Their precedence tier is controlled
by:

```toml
semantic_rule_precedence = "builtins-first"
```

Supported values are:

- `builtins-first`: compatibility default; built-ins win over configured rules;
- `configured-first`: configured rules are evaluated first and can override an
  applicable built-in match.

Parent directories deliberately influence path matching because the normalized
search value contains every component of the supplied source path. For example,
a generic PDF inside a `yocto/` directory can match the Yocto built-in rule even
when the filename itself is generic.

### Configured rule IDs and overrides

Configured rules may define stable IDs:

```toml
semantic_rule_precedence = "configured-first"

[[semantic_rules]]
id = "local:tax-archive"
folder = "private/tax-archive"
keywords = ["cu2026", "certificazione unica"]
```

The `id` field is optional. Rules without one receive deterministic IDs derived
from their normalized definition, so reordering equivalent rules cannot change
an equivalent decision. Explicit configured IDs must be unique and cannot use
the reserved `builtin:` prefix.

### Disabling built-in rules

Applicable built-in rules can be disabled without removing the rest of the
taxonomy:

```toml
disabled_builtin_rules = [
  "builtin:documents/taxes",
  "builtin:documents/vehicle",
]
```

Stable built-in IDs are:

- `builtin:documents/utilities/fastweb`
- `builtin:documents/utilities/water`
- `builtin:documents/inps-sfl`
- `builtin:documents/taxes`
- `builtin:documents/identity`
- `builtin:documents/health`
- `builtin:documents/legal-notifications`
- `builtin:documents/bank-poste`
- `builtin:documents/vehicle`
- `builtin:documents/insurance`
- `builtin:documents/work-admin`
- `builtin:learning/kleis`
- `builtin:learning/yocto`
- `builtin:books/programming`
- `builtin:photos/2026`

Unknown IDs have no effect, allowing a shared configuration to remain usable
across versions in which a built-in rule may not exist.

### Explaining a classification

Default previews remain unchanged. Add `--explain` to include the effective
profile, outcome, selected candidate, competing candidates, and privacy-safe
evidence (source, mechanism, strength, rule ID, and reason):

```bash
uv run smart-file-organizer plan   --config smart-file-organizer.toml   --explain   CU2026_PERSON_A.pdf
```

JSON explanations are available by combining `--explain` with `--format json`.
The additional `classification` object represents ambiguity and abstention as
well as selected semantic, extension, special-case, and fallback outcomes.

`--explain` affects dry-run previews only. Apply summaries and durable recovery
manifests retain their existing format.

Private configuration files should not be committed. Use `smart-file-organizer.example.toml` as a public template and keep local/private rules in `smart-file-organizer.toml` or under ignored paths such as `.local-data/`.

## Logging

The command is quiet by default.

Use `--verbose` to enable high-level application logs:

~~~bash
uv run smart-file-organizer plan --verbose --target organized photo.jpg
~~~

Verbose logs use simple key-value events such as `event=sources_collected count=1`.
Logs should describe application events only. They must not include extracted document text, private document contents, or full inspected content.

## Privacy and local data

The repository must not contain private backup data, real document contents, or real manual-run outputs.

Local experiments should stay in ignored paths such as:

~~~text
.local-data/
.local-output/
manual-runs/
~~~

Synthetic examples are preferred for tests and documentation.

## Supported platform and filesystem-risk coverage

The supported operating-system boundary is **Linux only**. CI exercises the
complete suite on Python 3.11 and Python 3.12 on Linux. Windows and macOS are
not currently claimed or tested.

The regression contract for the supported platform includes:

- a source that disappears after preflight but before its move is recorded as
  `failed`, later moves remain `unattempted`, and the CLI returns the durable
  manifest through its public error output;
- a read-only destination parent produces status `2`, preserves the source,
  creates no recovery manifest, and emits one concise error line without a
  traceback or duplicate log record;
- Linux case-sensitive names such as `Report.txt` and `report.txt` remain
  distinct sources and distinct destinations;
- a bounded synthetic dry run covers 512 direct files through the public CLI,
  expects exactly 512 preview lines, and must not create the target directory.

The 512-file check is a regression smoke test, not a performance benchmark or
latency guarantee. Filesystems with case-insensitive behavior and operating
systems outside Linux remain outside the current support claim.

## Current limitations

- Content inspection is opt-in and currently limited to supported document types.
- Directory scanning is non-recursive by default; use `--recursive` to include nested files.
- Existing destination files are never overwritten.
- Destination conflicts fail by default; use `--conflict-strategy rename` for deterministic renames.
- Configuration currently supports semantic TOML rules only.

These limitations are intentional for now. The project is being built step by step with small, tested changes.

## Project structure

~~~text
src/smart_file_organizer/
├── app_logging.py
├── api.py
├── classification.py
├── cli.py
├── config.py
├── content_planning.py
├── core.py
├── document_text.py
├── evidence.py
├── errors.py
├── models.py
├── plan_output.py
├── planning.py
├── semantic_rules.py
└── taxonomy.py

tests/
├── test_cli.py
├── test_api.py
├── test_config.py
├── test_content_planning.py
├── test_core.py
├── test_document_text.py
└── test_plan_output.py
~~~

`api.py` is the provisional supported Python API. `core.py` retains historical
compatibility exports but is not covered by the API stability promise.

`models.py` contains shared domain models and type aliases.

`plan_output.py` contains plan preview formatters for text and JSON output.

`classification.py` contains extension-based file classification.

`semantic_rules.py` contains semantic destination rule matching.

`planning.py` contains move planning, conflict detection, and safe execution helpers.

`content_planning.py` connects document text extraction to planning helpers.

`document_text.py` contains supported document text extraction utilities.

`cli.py` contains the command-line interface.
