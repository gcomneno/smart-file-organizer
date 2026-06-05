from pathlib import Path

import sys

from pypdf import PdfWriter

import smart_file_organizer.document_text as document_text
from smart_file_organizer.document_text import extract_document_text


def test_extract_document_text_reads_txt_file(tmp_path: Path) -> None:
    document = tmp_path / "demo-note.txt"
    document.write_text(
        "Demo Utility Provider\nInvoice number 0001\n", encoding="utf-8"
    )

    assert extract_document_text(document) == (
        "Demo Utility Provider\nInvoice number 0001\n"
    )


def test_extract_document_text_returns_empty_for_unsupported_file(
    tmp_path: Path,
) -> None:
    document = tmp_path / "demo.bin"
    document.write_bytes(b"not a supported document")

    assert extract_document_text(document) == ""


def test_extract_document_text_handles_pdf_without_page_text(tmp_path: Path) -> None:
    document = tmp_path / "empty-demo.pdf"

    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)

    with document.open("wb") as stream:
        writer.write(stream)

    assert extract_document_text(document) == ""


def test_extract_document_text_silences_pdf_parser_stderr(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    document = tmp_path / "noisy-demo.pdf"
    document.write_bytes(b"fake pdf bytes")

    class FakePage:
        def extract_text(self) -> str:
            return "Demo PDF text"

    class FakePdfReader:
        def __init__(self, path: Path) -> None:
            print("Ignoring wrong pointing object 1 65536 (offset 0)", file=sys.stderr)
            self.pages = [FakePage()]

    monkeypatch.setattr(document_text, "PdfReader", FakePdfReader)

    assert extract_document_text(document) == "Demo PDF text"
    captured = capsys.readouterr()
    assert captured.err == ""
