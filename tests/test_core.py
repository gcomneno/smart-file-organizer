from pathlib import Path

import pytest

from smart_file_organizer.core import (
    FileCategory,
    PlannedMove,
    build_organization_plan,
    build_organization_plan_with_document_texts,
    classify_path,
    execute_plan,
    find_destination_conflicts,
    infer_destination_folder,
    list_source_files,
    plan_file,
    plan_file_with_document_text,
)
from smart_file_organizer.errors import (
    DestinationConflictError,
    DestinationExistsError,
    SourceMissingError,
)


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("photo.jpg", FileCategory.IMAGES),
        ("photo.JPEG", FileCategory.IMAGES),
        ("song.mp3", FileCategory.AUDIO),
        ("movie.mp4", FileCategory.VIDEOS),
        ("archive.zip", FileCategory.ARCHIVES),
        ("notes.txt", FileCategory.DOCUMENTS),
        ("script.py", FileCategory.CODE),
        ("unknown-file", FileCategory.OTHER),
        ("unknown.xyz", FileCategory.OTHER),
    ],
)
def test_classify_path_by_extension(filename: str, expected: FileCategory) -> None:
    assert classify_path(Path(filename)) == expected


def test_plan_file_builds_destination_from_category() -> None:
    plan = plan_file(Path("photo.jpg"), Path("organized"))

    assert plan == PlannedMove(
        source=Path("photo.jpg"),
        destination=Path("organized/images/photo.jpg"),
        category=FileCategory.IMAGES,
    )


def test_plan_file_uses_other_category_for_unknown_extension() -> None:
    plan = plan_file(Path("mystery.xyz"), Path("organized"))

    assert plan.destination == Path("organized/other/mystery.xyz")
    assert plan.category == FileCategory.OTHER


def test_build_organization_plan_with_document_texts_uses_content() -> None:
    plan = build_organization_plan_with_document_texts(
        [
            Path("generic.pdf"),
            Path("photo.jpg"),
        ],
        Path("organized"),
        {
            Path("generic.pdf"): "Demo Fiscal Agency\nCertificazione Unica\n",
        },
    )

    assert plan == [
        PlannedMove(
            source=Path("generic.pdf"),
            destination=Path("organized/documents/taxes/generic.pdf"),
            category=FileCategory.DOCUMENTS,
        ),
        PlannedMove(
            source=Path("photo.jpg"),
            destination=Path("organized/images/photo.jpg"),
            category=FileCategory.IMAGES,
        ),
    ]


def test_build_organization_plan_builds_multiple_moves() -> None:
    plan = build_organization_plan(
        [
            Path("photo.jpg"),
            Path("notes.txt"),
            Path("script.py"),
        ],
        Path("organized"),
    )

    assert plan == [
        PlannedMove(
            source=Path("photo.jpg"),
            destination=Path("organized/images/photo.jpg"),
            category=FileCategory.IMAGES,
        ),
        PlannedMove(
            source=Path("notes.txt"),
            destination=Path("organized/documents/notes.txt"),
            category=FileCategory.DOCUMENTS,
        ),
        PlannedMove(
            source=Path("script.py"),
            destination=Path("organized/code/script.py"),
            category=FileCategory.CODE,
        ),
    ]


def test_list_source_files_returns_only_direct_files(tmp_path: Path) -> None:
    image = tmp_path / "photo.jpg"
    notes = tmp_path / "notes.txt"
    nested_dir = tmp_path / "nested"

    image.write_text("fake image")
    notes.write_text("hello")
    nested_dir.mkdir()
    (nested_dir / "ignored.txt").write_text("ignore me")

    assert list_source_files(tmp_path) == [
        notes,
        image,
    ]


def test_find_destination_conflicts_returns_empty_for_unique_destinations() -> None:
    plan = [
        PlannedMove(
            source=Path("photo.jpg"),
            destination=Path("organized/images/photo.jpg"),
            category=FileCategory.IMAGES,
        ),
        PlannedMove(
            source=Path("notes.txt"),
            destination=Path("organized/documents/notes.txt"),
            category=FileCategory.DOCUMENTS,
        ),
    ]

    assert find_destination_conflicts(plan) == {}


def test_find_destination_conflicts_groups_moves_by_duplicate_destination() -> None:
    destination = Path("organized/images/photo.jpg")
    first_move = PlannedMove(
        source=Path("folder-a/photo.jpg"),
        destination=destination,
        category=FileCategory.IMAGES,
    )
    second_move = PlannedMove(
        source=Path("folder-b/photo.jpg"),
        destination=destination,
        category=FileCategory.IMAGES,
    )
    safe_move = PlannedMove(
        source=Path("notes.txt"),
        destination=Path("organized/documents/notes.txt"),
        category=FileCategory.DOCUMENTS,
    )

    assert find_destination_conflicts([first_move, second_move, safe_move]) == {
        destination: [first_move, second_move],
    }


def test_execute_plan_moves_files_and_creates_destination_directories(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "source"
    target_root = tmp_path / "organized"
    source_root.mkdir()

    photo = source_root / "photo.jpg"
    notes = source_root / "notes.txt"

    photo.write_text("fake image")
    notes.write_text("hello")

    plan = build_organization_plan(
        list_source_files(source_root),
        target_root,
    )

    execute_plan(plan)

    assert not photo.exists()
    assert not notes.exists()
    assert (target_root / "images" / "photo.jpg").read_text() == "fake image"
    assert (target_root / "documents" / "notes.txt").read_text() == "hello"


def test_execute_plan_rejects_existing_destination(tmp_path: Path) -> None:
    source = tmp_path / "source" / "photo.jpg"
    destination = tmp_path / "organized" / "images" / "photo.jpg"

    source.parent.mkdir()
    destination.parent.mkdir(parents=True)

    source.write_text("new image")
    destination.write_text("existing image")

    plan = [
        PlannedMove(
            source=source,
            destination=destination,
            category=FileCategory.IMAGES,
        ),
    ]

    with pytest.raises(FileExistsError, match="destination already exists"):
        execute_plan(plan)

    assert source.read_text() == "new image"
    assert destination.read_text() == "existing image"


def test_execute_plan_rejects_missing_source(tmp_path: Path) -> None:
    source = tmp_path / "missing.jpg"
    destination = tmp_path / "organized" / "images" / "missing.jpg"

    plan = [
        PlannedMove(
            source=source,
            destination=destination,
            category=FileCategory.IMAGES,
        ),
    ]

    with pytest.raises(FileNotFoundError, match="source file does not exist"):
        execute_plan(plan)

    assert not destination.exists()


def test_execute_plan_rejects_destination_conflicts(tmp_path: Path) -> None:
    first_source = tmp_path / "folder-a" / "photo.jpg"
    second_source = tmp_path / "folder-b" / "photo.jpg"
    destination = tmp_path / "organized" / "images" / "photo.jpg"

    first_source.parent.mkdir()
    second_source.parent.mkdir()

    first_source.write_text("first")
    second_source.write_text("second")

    plan = [
        PlannedMove(
            source=first_source,
            destination=destination,
            category=FileCategory.IMAGES,
        ),
        PlannedMove(
            source=second_source,
            destination=destination,
            category=FileCategory.IMAGES,
        ),
    ]

    with pytest.raises(ValueError, match="plan contains destination conflicts"):
        execute_plan(plan)

    assert first_source.read_text() == "first"
    assert second_source.read_text() == "second"
    assert not destination.exists()


@pytest.mark.parametrize(
    ("filename", "expected_folder"),
    [
        (
            "Conto-FASTWEB-M000000000-20260501.pdf",
            Path("documents/utilities/fastweb"),
        ),
        (
            "acque-spa-2026.pdf",
            Path("documents/utilities/water"),
        ),
        (
            "SFL_domanda_INPS-SFL-2026-0000000_2026-05-15.pdf",
            Path("documents/inps-sfl"),
        ),
        (
            "20260331182348_ModelloAttestazioneDsu.pdf",
            Path("documents/inps-sfl"),
        ),
        (
            "CU2026_PERSON_A.pdf",
            Path("documents/taxes"),
        ),
        (
            "ADE 2024 - Verbale definitivo.pdf",
            Path("documents/taxes"),
        ),
        (
            "ci-fronte-small.jpg",
            Path("documents/identity"),
        ),
        (
            "ci-retro-small.jpg",
            Path("documents/identity"),
        ),
        (
            "Health.Urologia/20260420_patient_urinocoltura.pdf",
            Path("documents/health"),
        ),
        (
            "PN_LEGAL_FACTS-648db301539a44a9a34efc15c83ad6b9.pdf",
            Path("documents/legal-notifications"),
        ),
        (
            "DocumentoPostawebRapporto_00000000_00000000.pdf",
            Path("documents/bank-poste"),
        ),
        (
            "Assicurazione_generica_zurich_26.pdf",
            Path("documents/insurance"),
        ),
        (
            "POL 00000000- PERSON - MAZDA AA000AA- SCAD.19-04-2026.pdf",
            Path("documents/vehicle"),
        ),
        (
            "Ricevuta_AA000AA_18-05-2026.pdf",
            Path("documents/vehicle"),
        ),
        (
            "Pre assunzione Person Demo.pdf",
            Path("documents/work-admin"),
        ),
        (
            "Kleis Corso/c sharp - lezione 2/c sharp - lezione 2.pptx",
            Path("learning/kleis"),
        ),
        (
            "yocto-slides.pdf",
            Path("learning/yocto"),
        ),
        (
            "Mastering_Modern_CPP_C++11-C++23.pdf",
            Path("books/programming"),
        ),
        (
            "Hacking Secret Ciphers with Python.pdf",
            Path("books/programming"),
        ),
        (
            "Alicia Gimenez-Bartlet - Il Caso del Lituano (sellerio - 2005).epub",
            Path("books/fiction"),
        ),
        (
            "Fitzek_-Sebastian-La-Terapia.azw3",
            Path("books/fiction"),
        ),
        (
            "Foto2026/20260303_182803.jpg",
            Path("photos/2026"),
        ),
        (
            "unknown-file.xyz",
            Path("other"),
        ),
    ],
)
def test_infer_destination_folder_from_realistic_backup_names(
    filename: str,
    expected_folder: Path,
) -> None:
    assert infer_destination_folder(Path(filename)) == expected_folder


def test_infer_destination_folder_keeps_book_signal_over_text() -> None:
    assert infer_destination_folder(
        Path("Hacking Secret Ciphers with Python.pdf"),
        document_text="INPS SFL ISEE DSU prestazioni a sostegno",
    ) == Path("books/programming")


def test_infer_destination_folder_keeps_learning_signal_over_document_text() -> None:
    assert infer_destination_folder(
        Path("Kleis Corso/c sharp - lezione 2/c sharp - lezione 2.pptx"),
        document_text="INPS SFL ISEE DSU prestazioni a sostegno",
    ) == Path("learning/kleis")


def test_plan_file_with_document_text_uses_content_for_destination() -> None:
    plan = plan_file_with_document_text(
        Path("generic.pdf"),
        Path("organized"),
        "Demo Fiscal Agency\nCertificazione Unica\n",
    )

    assert plan == PlannedMove(
        source=Path("generic.pdf"),
        destination=Path("organized/documents/taxes/generic.pdf"),
        category=FileCategory.DOCUMENTS,
    )


def test_plan_file_uses_semantic_destination_folder() -> None:
    plan = plan_file(
        Path("Conto-FASTWEB-M000000000-20260501.pdf"),
        Path("organized"),
    )

    assert plan == PlannedMove(
        source=Path("Conto-FASTWEB-M000000000-20260501.pdf"),
        destination=Path(
            "organized/documents/utilities/fastweb/"
            "Conto-FASTWEB-M000000000-20260501.pdf"
        ),
        category=FileCategory.DOCUMENTS,
    )


def test_infer_destination_folder_uses_document_text_for_generic_filename() -> None:
    assert infer_destination_folder(
        Path("2612883212.pdf"),
        document_text="Demo Fiscal Agency\nCertificazione Unica\n",
    ) == Path("documents/taxes")


def test_infer_destination_folder_uses_filename_when_text_is_empty() -> None:
    assert infer_destination_folder(
        Path("Conto-FASTWEB-M000000000-20260501.pdf"),
        document_text="",
    ) == Path("documents/utilities/fastweb")


def test_infer_destination_folder_uses_configured_semantic_rules() -> None:
    rules = (
        (
            "documents/demo-utility",
            ("demo utility", "synthetic invoice"),
        ),
    )

    assert infer_destination_folder(
        Path("synthetic-invoice.pdf"),
        semantic_rules=rules,
    ) == Path("documents/demo-utility")


def test_plan_file_uses_configured_semantic_rules() -> None:
    rules = (
        (
            "documents/demo-utility",
            ("synthetic invoice",),
        ),
    )

    move = plan_file(
        Path("synthetic-invoice.pdf"),
        Path("organized"),
        semantic_rules=rules,
    )

    assert move.destination == Path(
        "organized/documents/demo-utility/synthetic-invoice.pdf"
    )


def test_build_organization_plan_with_document_texts_uses_configured_rules() -> None:
    source = Path("notes.txt")
    rules = (
        (
            "learning/demo-course",
            ("demo course",),
        ),
    )

    plan = build_organization_plan_with_document_texts(
        [source],
        Path("organized"),
        {source: "Notes from a demo course about safe file organization."},
        semantic_rules=rules,
    )

    assert plan[0].destination == Path("organized/learning/demo-course/notes.txt")


def test_execute_plan_raises_destination_conflict_error() -> None:
    destination = Path("organized/images/photo.jpg")
    plan = [
        PlannedMove(
            source=Path("folder-a/photo.jpg"),
            destination=destination,
            category=FileCategory.IMAGES,
        ),
        PlannedMove(
            source=Path("folder-b/photo.jpg"),
            destination=destination,
            category=FileCategory.IMAGES,
        ),
    ]

    with pytest.raises(
        DestinationConflictError,
        match="plan contains destination conflicts",
    ):
        execute_plan(plan)


def test_execute_plan_raises_source_missing_error(tmp_path: Path) -> None:
    missing_source = tmp_path / "missing.txt"
    destination = tmp_path / "organized" / "documents" / "missing.txt"

    plan = [
        PlannedMove(
            source=missing_source,
            destination=destination,
            category=FileCategory.DOCUMENTS,
        )
    ]

    with pytest.raises(
        SourceMissingError,
        match=f"source file does not exist: {missing_source}",
    ):
        execute_plan(plan)


def test_execute_plan_raises_destination_exists_error(tmp_path: Path) -> None:
    source = tmp_path / "notes.txt"
    destination = tmp_path / "organized" / "documents" / "notes.txt"
    destination.parent.mkdir(parents=True)

    source.write_text("new notes")
    destination.write_text("existing notes")

    plan = [
        PlannedMove(
            source=source,
            destination=destination,
            category=FileCategory.DOCUMENTS,
        )
    ]

    with pytest.raises(
        DestinationExistsError,
        match=f"destination already exists: {destination}",
    ):
        execute_plan(plan)
