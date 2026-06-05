from pathlib import Path

from pypdf import PdfWriter

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
