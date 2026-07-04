# smart-file-organizer

[![CI](https://github.com/gcomneno/smart-file-organizer/actions/workflows/ci.yml/badge.svg)](https://github.com/gcomneno/smart-file-organizer/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

A small Python CLI project used as a clean-coding laboratory.

The project organizes files by building a safe plan first. By default it only prints what it would do. Files are moved only when `--apply` is explicitly passed.

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

## Development setup

Install dependencies and create the local virtual environment:

~~~bash
uv sync
~~~

Run the test suite:

~~~bash
uv run python -m pytest
~~~

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
uv run smart-file-organizer --target organized photo.jpg notes.txt script.py
~~~

Example output:

~~~text
photo.jpg -> organized/images/photo.jpg
notes.txt -> organized/documents/notes.txt
script.py -> organized/code/script.py
~~~

This does not move files.

### Dry run from a directory

~~~bash
uv run smart-file-organizer --from /path/to/source --target /path/to/organized
~~~

The command scans only direct files in the source directory by default.

This does not move files.

### Recursive directory scan

Use `--recursive` with `--from` to include files from nested directories:

~~~bash
uv run smart-file-organizer --from /path/to/source --recursive --target /path/to/organized
~~~

Only files are included; directories themselves are not moved.

### Dry run with content inspection

~~~bash
uv run smart-file-organizer --inspect-content --from /path/to/source --target /path/to/organized
~~~

This opt-in mode extracts text from supported documents and uses that text when building the plan.

It is disabled by default. Start with a dry run before combining it with `--apply`.

Currently supported document text sources:

- `.txt` files;
- `.pdf` files, using the first pages only.

PDF content inspection works only for PDFs with extractable text. OCR for scanned documents is not implemented yet.

### Apply the organization plan

~~~bash
uv run smart-file-organizer --from /path/to/source --target /path/to/organized --apply
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

The CLI supports command groups. The primary command is currently `plan`:

~~~bash
uv run smart-file-organizer plan --target organized photo.jpg
~~~

Planning remains safe by default: it prints the move plan without moving files.

Use `--apply` explicitly to execute the plan:

~~~bash
uv run smart-file-organizer plan --from Downloads --target organized --apply
~~~

The original direct planning style is still supported as a compatibility path:

~~~bash
uv run smart-file-organizer --target organized photo.jpg
~~~

## Safety behavior

The default mode is a dry run. Files are moved only with `--apply`.

Content inspection is also opt-in. Document text is read only when `--inspect-content` is explicitly passed.

Before applying a plan, the program checks that:

- no two source files would be moved to the same destination;
- every source file exists;
- no destination file already exists.

If any of these checks fail, the command stops with an error.

## Configuration

You can pass an optional TOML configuration file with semantic destination rules:

~~~bash
uv run smart-file-organizer \
  --config smart-file-organizer.example.toml \
  --target organized \
  synthetic-invoice.pdf
~~~

Example configuration:

~~~toml
[[semantic_rules]]
folder = "documents/demo-utility"
keywords = ["synthetic invoice", "demo utility"]
~~~

Configured rules **extend** the built-in semantic rules; they do not replace them. Built-in rules are evaluated first, then rules from the TOML file, so default categories such as taxes, utilities, and insurance keep working while you add local keywords.

When a keyword from either built-in or configured rules matches the file path or inspected document text, the matching folder is used as the destination subfolder.

Private configuration files should not be committed. Use `smart-file-organizer.example.toml` as a public template and keep local/private rules in `smart-file-organizer.toml` or under ignored paths such as `.local-data/`.

## Logging

The command is quiet by default.

Use `--verbose` to enable high-level application logs:

~~~bash
uv run smart-file-organizer --verbose --target organized photo.jpg
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

## Current limitations

- Content inspection is opt-in and currently limited to supported document types.
- Directory scanning is non-recursive by default; use `--recursive` to include nested files.
- Existing destination files are never overwritten.
- There is no rename strategy for conflicts yet.
- Configuration currently supports semantic TOML rules only.

These limitations are intentional for now. The project is being built step by step with small, tested changes.

## Project structure

~~~text
src/smart_file_organizer/
├── app_logging.py
├── classification.py
├── cli.py
├── config.py
├── content_planning.py
├── core.py
├── document_text.py
├── errors.py
├── models.py
├── planning.py
└── semantic_rules.py

tests/
├── test_cli.py
├── test_config.py
├── test_content_planning.py
├── test_core.py
└── test_document_text.py
~~~

`core.py` keeps compatibility exports for the original public core imports.

`models.py` contains shared domain models and type aliases.

`classification.py` contains extension-based file classification.

`semantic_rules.py` contains semantic destination rule matching.

`planning.py` contains move planning, conflict detection, and safe execution helpers.

`content_planning.py` connects document text extraction to planning helpers.

`document_text.py` contains supported document text extraction utilities.

`cli.py` contains the command-line interface.
