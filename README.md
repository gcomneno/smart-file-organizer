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
- Uses `pytest` for tests.

## Development setup

Install dependencies and create the local virtual environment:

~~~bash
uv sync
~~~

Run the test suite:

~~~bash
uv run pytest
~~~

Run formatting and linting checks:

~~~bash
uv run ruff format --check .
uv run ruff check .
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

The command scans only direct files in the source directory. It does not scan nested directories yet.

This does not move files.

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

When a configured keyword matches the file path or inspected document text, the configured folder is used as the destination subfolder.

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
- Directory scanning is not recursive.
- Existing destination files are never overwritten.
- There is no rename strategy for conflicts yet.
- There is no configuration file yet.

These limitations are intentional for now. The project is being built step by step with small, tested changes.

## Project structure

~~~text
src/smart_file_organizer/
├── cli.py
├── content_planning.py
├── core.py
└── document_text.py

tests/
├── test_cli.py
├── test_content_planning.py
├── test_core.py
└── test_document_text.py
~~~

`core.py` contains the main domain logic.

`content_planning.py` connects document text extraction to planning helpers.

`document_text.py` contains supported document text extraction utilities.

`cli.py` contains the command-line interface.
