import logging
from pathlib import Path

import pytest
from pypdf import PdfWriter

import smart_file_organizer.content_planning as content_planning
import smart_file_organizer.document_text as document_text
from smart_file_organizer.cli import main
from smart_file_organizer.document_text import (
    DocumentInspectionResult,
    DocumentInspectionStatus,
    inspect_document_text,
)


def write_blank_pdf(path: Path, *, encrypted: bool = False) -> None:
    """Write a valid text-free PDF for inspection tests."""
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)

    if encrypted:
        writer.encrypt("synthetic-password")

    with path.open("wb") as stream:
        writer.write(stream)


def test_inspection_contains_corrupt_pdf_failure(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    document = tmp_path / "corrupt.pdf"
    document.write_bytes(b"%PDF-1.7\nsynthetic corrupt bytes")

    result = inspect_document_text(document)

    captured = capsys.readouterr()

    assert result.path == document
    assert result.status == DocumentInspectionStatus.FAILED
    assert result.text == ""
    assert result.error_type
    assert captured.err == ""


def test_inspection_contains_encrypted_pdf_failure(
    tmp_path: Path,
) -> None:
    document = tmp_path / "encrypted.pdf"
    write_blank_pdf(document, encrypted=True)

    result = inspect_document_text(document)

    assert result.status == DocumentInspectionStatus.FAILED
    assert result.text == ""
    assert result.error_type


def test_inspection_contains_unreadable_pdf_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = tmp_path / "unreadable.pdf"
    document.write_bytes(b"synthetic")

    class UnreadablePdfReader:
        def __init__(self, path: Path) -> None:
            raise PermissionError(f"synthetic unreadable path: {path}")

    monkeypatch.setattr(
        document_text,
        "PdfReader",
        UnreadablePdfReader,
    )

    result = inspect_document_text(document)

    assert result.status == DocumentInspectionStatus.FAILED
    assert result.error_type == "PermissionError"
    assert not hasattr(result, "error_message")


def test_inspection_marks_image_only_pdf_as_no_text(
    tmp_path: Path,
) -> None:
    document = tmp_path / "image-only.pdf"
    write_blank_pdf(document)

    result = inspect_document_text(document)

    assert result.status == DocumentInspectionStatus.NO_TEXT
    assert result.text == ""
    assert result.error_type is None


def test_inspection_marks_unsupported_content_without_opening_it(
    tmp_path: Path,
) -> None:
    document = tmp_path / "archive.zip"
    document.write_bytes(b"synthetic")

    result = inspect_document_text(document)

    assert result.status == DocumentInspectionStatus.UNSUPPORTED
    assert result.text == ""
    assert result.error_type is None


@pytest.mark.parametrize(
    "error_type",
    [
        "PdfReadError",
        "FileNotDecryptedError",
        "PermissionError",
    ],
)
def test_cli_warns_and_uses_filename_fallback_for_reader_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    error_type: str,
) -> None:
    document = tmp_path / "CU2026_PERSON_A.pdf"
    target_root = tmp_path / "organized"
    document.write_bytes(b"synthetic")

    def failed_inspection(
        path: Path,
        *,
        max_pages: int = 3,
        verbose: bool = False,
    ) -> DocumentInspectionResult:
        del max_pages, verbose
        return DocumentInspectionResult(
            path=path,
            status=DocumentInspectionStatus.FAILED,
            error_type=error_type,
        )

    monkeypatch.setattr(
        content_planning,
        "inspect_document_text",
        failed_inspection,
    )

    main(
        [
            "--inspect-content",
            "--target",
            str(target_root),
            str(document),
        ]
    )

    captured = capsys.readouterr()

    assert captured.out == (
        f"{document} -> {target_root / 'documents' / 'taxes' / document.name}\n"
    )
    assert str(document) in captured.err
    assert "using filename fallback" in captured.err
    assert "Traceback" not in captured.err
    assert "TOP SECRET" not in captured.err


def test_cli_warns_and_falls_back_for_image_only_pdf(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    document = tmp_path / "verbale-definitivo-2026.pdf"
    target_root = tmp_path / "organized"
    write_blank_pdf(document)

    main(
        [
            "--inspect-content",
            "--target",
            str(target_root),
            str(document),
        ]
    )

    captured = capsys.readouterr()

    assert captured.out == (
        f"{document} -> {target_root / 'documents' / 'inbox' / document.name}\n"
    )
    assert str(document) in captured.err
    assert "found no text" in captured.err
    assert "Traceback" not in captured.err


def test_verbose_failure_logs_error_class_but_not_contents(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    document = tmp_path / "generic.pdf"
    document.write_bytes(b"synthetic")

    def failed_inspection(
        path: Path,
        *,
        max_pages: int = 3,
        verbose: bool = False,
    ) -> DocumentInspectionResult:
        del max_pages, verbose
        return DocumentInspectionResult(
            path=path,
            status=DocumentInspectionStatus.FAILED,
            error_type="SyntheticPdfError",
        )

    monkeypatch.setattr(
        content_planning,
        "inspect_document_text",
        failed_inspection,
    )

    with caplog.at_level(logging.INFO):
        content_planning.build_organization_plan_inspecting_content(
            [document],
            tmp_path / "organized",
            verbose=True,
        )

    assert str(document) in caplog.text
    assert "SyntheticPdfError" in caplog.text
    assert "TOP SECRET" not in caplog.text


def test_cli_help_documents_inspection_boundary(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["plan", "--help"])

    captured = capsys.readouterr()
    normalized_help = " ".join(captured.out.split())

    assert exc_info.value.code == 0
    assert "first three PDF pages" in normalized_help
    assert "fall back to filename classification" in normalized_help
    assert "OCR is not performed" in normalized_help
