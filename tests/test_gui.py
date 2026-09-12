"""Headless contracts for the read-only desktop recovery prototype."""

import ast
import hashlib
import json
import os
import stat
import subprocess
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any

import pytest

from smart_file_organizer import api
from smart_file_organizer.gui import controller
from smart_file_organizer.gui.view_model import (
    AUTHORITY_NOTICE,
    TRUST_LAYER_KEYS,
    DesktopState,
    DisplayField,
    RecoverySummaryView,
    recovery_assessment_view,
)

_TIMESTAMP = "2026-09-10T12:00:00+00:00"
_MANIFEST_NAME = "apply-20260910T120000000000Z-0123456789ab.json"


def _load_tk_app() -> tuple[Any, Any]:
    try:
        import tkinter
    except ModuleNotFoundError as error:
        if error.name not in {"tkinter", "_tkinter"}:
            raise
        pytest.skip("real tkinter is unavailable")

    from smart_file_organizer.gui import tk_app

    return tkinter, tk_app


def _recovery_fixture(
    tmp_path: Path, *, current_content: bytes
) -> tuple[Path, Path, Path]:
    historical_content = b"historical payload"
    target = tmp_path / "target"
    source = tmp_path / "source.txt"
    destination = target / "documents" / "source.txt"
    destination.parent.mkdir(parents=True)
    destination.write_bytes(current_content)
    manifest_path = target / ".smart-file-organizer" / "manifests" / _MANIFEST_NAME
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "state": "completed",
                "target_root": str(target),
                "started_at": _TIMESTAMP,
                "updated_at": _TIMESTAMP,
                "finished_at": _TIMESTAMP,
                "counts": {
                    "completed": 1,
                    "failed": 0,
                    "in_progress": 0,
                    "unattempted": 0,
                },
                "moves": [
                    {
                        "original_path": str(source),
                        "final_path": str(destination),
                        "category": "documents",
                        "status": "completed",
                        "timestamp": _TIMESTAMP,
                        "error": None,
                        "identity": {
                            "algorithm": "sha256",
                            "digest": hashlib.sha256(historical_content).hexdigest(),
                            "size_bytes": len(historical_content),
                            "source_observed_at": _TIMESTAMP,
                            "destination_observed_at": _TIMESTAMP,
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return manifest_path, source, destination


def _mixed_recovery_fixture(tmp_path: Path) -> Path:
    target = tmp_path / "target"
    proposed_content = b"proposed historical payload"
    refused_content = b"refused historical payload"
    moves = []
    for name, historical_content, current_content in (
        ("proposed.txt", proposed_content, proposed_content),
        ("refused.txt", refused_content, b"changed payload"),
    ):
        source = tmp_path / name
        destination = target / "documents" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(current_content)
        moves.append(
            {
                "original_path": str(source),
                "final_path": str(destination),
                "category": "documents",
                "status": "completed",
                "timestamp": _TIMESTAMP,
                "error": None,
                "identity": {
                    "algorithm": "sha256",
                    "digest": hashlib.sha256(historical_content).hexdigest(),
                    "size_bytes": len(historical_content),
                    "source_observed_at": _TIMESTAMP,
                    "destination_observed_at": _TIMESTAMP,
                },
            }
        )
    manifest_path = target / ".smart-file-organizer" / "manifests" / _MANIFEST_NAME
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "state": "completed",
                "target_root": str(target),
                "started_at": _TIMESTAMP,
                "updated_at": _TIMESTAMP,
                "finished_at": _TIMESTAMP,
                "counts": {
                    "completed": 2,
                    "failed": 0,
                    "in_progress": 0,
                    "unattempted": 0,
                },
                "moves": moves,
            }
        ),
        encoding="utf-8",
    )
    return manifest_path


def _snapshot(
    root: Path,
) -> tuple[tuple[str, str, bytes | str | None, int, int], ...]:
    entries: list[tuple[str, str, bytes | str | None, int, int]] = []

    def visit(directory: Path) -> None:
        with os.scandir(directory) as children:
            for child in sorted(children, key=lambda entry: entry.name):
                path = Path(child.path)
                metadata = child.stat(follow_symlinks=False)
                if child.is_symlink():
                    kind = "symlink"
                    payload: bytes | str | None = os.readlink(path)
                elif child.is_file(follow_symlinks=False):
                    kind = "regular file"
                    payload = path.read_bytes()
                elif child.is_dir(follow_symlinks=False):
                    kind = "directory"
                    payload = None
                else:
                    kind = "other"
                    payload = None
                entries.append(
                    (
                        str(path.relative_to(root)),
                        kind,
                        payload,
                        stat.S_IMODE(metadata.st_mode),
                        metadata.st_mtime_ns,
                    )
                )
                if kind == "directory":
                    visit(path)

    visit(root)
    return tuple(entries)


def test_safe_proposed_assessment_maps_deterministically_to_view_model(
    tmp_path: Path,
) -> None:
    manifest_path, _source, destination = _recovery_fixture(
        tmp_path, current_content=b"historical payload"
    )
    assessment = api.assess_recovery(manifest_path)

    first = recovery_assessment_view(assessment)
    second = recovery_assessment_view(assessment)

    assert first == second
    assert first.authority_notice == AUTHORITY_NOTICE
    assert tuple(layer.key for layer in first.items[0].layers) == TRUST_LAYER_KEYS
    assert first.items[0].layers[3].state == "Safe to recover"
    assert first.items[0].layers[4].state == "Proposed"
    assert first.items[0].layers[4].fields[0].value == str(destination)


def test_refused_assessment_is_a_valid_safety_result_in_view_model(
    tmp_path: Path,
) -> None:
    manifest_path, _source, _destination = _recovery_fixture(
        tmp_path, current_content=b"changed payload"
    )

    state = controller.assess_manifest(DesktopState(str(manifest_path)))

    assert state.diagnostic is None
    assert state.assessment is not None
    view = state.assessment
    assert view.items[0].layers[3].state == "Refused"
    assert view.items[0].layers[3].fields[0].value == "Destination changed"
    assert view.items[0].layers[4].state == "Refused"
    assert view.items[0].layers[4].fields[0].value == (
        "No recovery operation is proposed"
    )


def test_mixed_assessment_has_deterministic_immutable_summary(tmp_path: Path) -> None:
    assessment = api.assess_recovery(_mixed_recovery_fixture(tmp_path))

    first = recovery_assessment_view(assessment)
    second = recovery_assessment_view(assessment)

    assert (
        first.summary
        == second.summary
        == RecoverySummaryView(
            total_move_records=2,
            proposed_count=1,
            refused_count=1,
        )
    )
    assert first.summary.fields == (
        DisplayField("Total move records", "2"),
        DisplayField("Proposed", "1"),
        DisplayField("Refused", "1"),
    )
    assert [item.layers[4].state for item in first.items] == ["Proposed", "Refused"]
    with pytest.raises(FrozenInstanceError):
        first.summary.proposed_count = 2  # ty: ignore[invalid-assignment]


def test_trust_layers_are_separate_ordered_immutable_values(tmp_path: Path) -> None:
    manifest_path, _source, _destination = _recovery_fixture(
        tmp_path, current_content=b"historical payload"
    )
    view = recovery_assessment_view(api.assess_recovery(manifest_path))
    layers = view.items[0].layers

    assert [layer.title for layer in layers] == [
        "1. Historical manifest evidence",
        "2. Current reconciliation",
        "3. Identity verification",
        "4. Recovery safety",
        "5. Recovery proposal / refusal",
    ]
    with pytest.raises(FrozenInstanceError):
        layers[0].title = "collapsed"  # ty: ignore[invalid-assignment]


def test_changing_manifest_input_invalidates_previous_assessment(
    tmp_path: Path,
) -> None:
    manifest_path, _source, _destination = _recovery_fixture(
        tmp_path, current_content=b"historical payload"
    )
    assessed = controller.assess_manifest(DesktopState(str(manifest_path)))

    changed = assessed.with_manifest_input(str(tmp_path / "another.json"))

    assert assessed.assessment is not None
    assert changed.assessment is None
    assert changed.diagnostic is None


def test_same_value_manifest_input_write_invalidates_previous_assessment(
    tmp_path: Path,
) -> None:
    manifest_path, _source, _destination = _recovery_fixture(
        tmp_path, current_content=b"historical payload"
    )
    assessed = controller.assess_manifest(DesktopState(str(manifest_path)))

    rewritten = assessed.with_manifest_input_write(str(manifest_path))

    assert assessed.assessment is not None
    assert rewritten == DesktopState(str(manifest_path))
    assert rewritten.assessment is None
    assert rewritten.diagnostic is None


@pytest.mark.parametrize(
    "written_value",
    ["", " \t\n"],
    ids=["blank", "whitespace-only"],
)
def test_blank_manifest_input_write_invalidates_previous_assessment(
    tmp_path: Path, written_value: str
) -> None:
    manifest_path, _source, _destination = _recovery_fixture(
        tmp_path, current_content=b"historical payload"
    )
    assessed = controller.assess_manifest(DesktopState(str(manifest_path)))

    rewritten = assessed.with_manifest_input_write(written_value)

    assert assessed.assessment is not None
    assert rewritten == DesktopState(written_value)
    assert rewritten.assessment is None
    assert rewritten.diagnostic is None


@pytest.mark.parametrize(
    "written_value",
    ["changed.json", "same", "", " \t\n"],
    ids=["changed", "equal", "blank", "whitespace-only"],
)
def test_real_tk_stringvar_trace_invalidates_previous_assessment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    written_value: str,
) -> None:
    tkinter, tk_app = _load_tk_app()
    manifest_path, _source, _destination = _recovery_fixture(
        tmp_path, current_content=b"historical payload"
    )
    assessed = controller.assess_manifest(DesktopState(str(manifest_path)))
    expected_value = (
        str(tmp_path / written_value)
        if written_value == "changed.json"
        else written_value
    )
    if written_value == "same":
        expected_value = str(manifest_path)
    interpreter = tkinter.Tcl()
    real_variable = tkinter.StringVar(master=interpreter)

    class Widget:
        def pack(self, **_kwargs: object) -> None:
            pass

        def bind(self, *_args: object, **_kwargs: object) -> None:
            pass

        def configure(self, **_kwargs: object) -> None:
            pass

        def create_window(self, *_args: object, **_kwargs: object) -> int:
            return 1

        def bbox(self, *_args: object) -> tuple[int, int, int, int]:
            return (0, 0, 0, 0)

        def itemconfigure(self, *_args: object, **_kwargs: object) -> None:
            pass

        def winfo_children(self) -> tuple[()]:
            return ()

        def yview(self, *_args: object) -> None:
            pass

        def set(self, *_args: object) -> None:
            pass

    class Root:
        def title(self, _value: str) -> None:
            pass

        def geometry(self, _value: str) -> None:
            pass

        def minsize(self, _width: int, _height: int) -> None:
            pass

    def widget_factory(*_args: object, **_kwargs: object) -> Widget:
        return Widget()

    monkeypatch.setattr(tk_app.tk, "StringVar", lambda: real_variable)
    monkeypatch.setattr(tk_app.tk, "Canvas", widget_factory)
    for widget_name in ("Frame", "Label", "Entry", "Button", "Scrollbar"):
        monkeypatch.setattr(tk_app.ttk, widget_name, widget_factory)

    application = tk_app.RecoveryDesktopApplication(Root())
    assert real_variable.trace_info()
    real_variable.set(expected_value)
    application._state = assessed

    real_variable.set(expected_value)

    assert assessed.assessment is not None
    assert application._state == DesktopState(expected_value)


def test_same_path_browse_reselection_invalidates_previous_assessment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _tkinter, tk_app = _load_tk_app()

    manifest_path, _source, _destination = _recovery_fixture(
        tmp_path, current_content=b"historical payload"
    )
    assessed = controller.assess_manifest(DesktopState(str(manifest_path)))
    application = object.__new__(tk_app.RecoveryDesktopApplication)

    class ManifestVariable:
        def __init__(self, value: str) -> None:
            self.value = value

        def get(self) -> str:
            return self.value

        def set(self, value: str) -> None:
            self.value = value
            application._manifest_changed()

    application.__dict__["_state"] = assessed
    application.__dict__["_manifest_input"] = ManifestVariable(str(manifest_path))
    application.__dict__["_render"] = lambda: None
    monkeypatch.setattr(
        tk_app.filedialog, "askopenfilename", lambda **_kwargs: str(manifest_path)
    )

    application._choose_manifest()

    assert assessed.assessment is not None
    assert application._state == DesktopState(str(manifest_path))


def test_cancelled_browse_keeps_current_assessment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _tkinter, tk_app = _load_tk_app()

    manifest_path, _source, _destination = _recovery_fixture(
        tmp_path, current_content=b"historical payload"
    )
    assessed = controller.assess_manifest(DesktopState(str(manifest_path)))
    application = object.__new__(tk_app.RecoveryDesktopApplication)

    class ManifestVariable:
        def set(self, _value: str) -> None:
            raise AssertionError("cancelled browse must not write the input")

    application.__dict__["_state"] = assessed
    application.__dict__["_manifest_input"] = ManifestVariable()
    monkeypatch.setattr(tk_app.filedialog, "askopenfilename", lambda **_kwargs: "")

    application._choose_manifest()

    assert application._state is assessed


@pytest.mark.parametrize(
    "error",
    [
        api.ManifestPathError("manifest path does not exist"),
        api.ManifestAccessError("manifest cannot be read"),
        api.ManifestFormatError("manifest JSON is malformed"),
        api.ManifestFormatError("manifest schema version is unsupported"),
    ],
)
def test_expected_api_errors_become_controlled_diagnostics(
    monkeypatch: pytest.MonkeyPatch, error: api.ManifestError
) -> None:
    def fail(_path: Path) -> api.RecoveryAssessment:
        raise error

    monkeypatch.setattr(controller.api, "assess_recovery", fail)

    state = controller.assess_manifest(DesktopState("/untrusted/manifest.json"))

    assert state.assessment is None
    assert state.diagnostic is not None
    assert state.diagnostic.message == f"Could not assess manifest: {error}"
    assert "Traceback" not in state.diagnostic.message


def test_failed_reassessment_discards_previous_successful_assessment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path, _source, _destination = _recovery_fixture(
        tmp_path, current_content=b"historical payload"
    )
    assessed = controller.assess_manifest(DesktopState(str(manifest_path)))
    error = api.ManifestPathError("manifest path does not exist")

    def fail(_path: Path) -> api.RecoveryAssessment:
        raise error

    monkeypatch.setattr(controller.api, "assess_recovery", fail)

    reassessed = controller.assess_manifest(assessed)

    assert assessed.assessment is not None
    assert reassessed.assessment is None
    assert reassessed.diagnostic is not None
    assert reassessed.diagnostic.message == f"Could not assess manifest: {error}"
    assert "Traceback" not in reassessed.diagnostic.message


def test_unexpected_programming_errors_are_not_swallowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(_path: Path) -> api.RecoveryAssessment:
        raise RuntimeError("programming defect")

    monkeypatch.setattr(controller.api, "assess_recovery", fail)

    with pytest.raises(RuntimeError, match="programming defect"):
        controller.assess_manifest(DesktopState("/untrusted/manifest.json"))


def test_desktop_controller_calls_supported_assess_recovery_seam(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path, _source, _destination = _recovery_fixture(
        tmp_path, current_content=b"historical payload"
    )
    assessment = api.assess_recovery(manifest_path)
    received: list[Path] = []

    def assess(path: Path) -> api.RecoveryAssessment:
        received.append(path)
        return assessment

    monkeypatch.setattr(controller.api, "assess_recovery", assess)

    state = controller.assess_manifest(DesktopState(str(manifest_path)))

    assert received == [manifest_path]
    assert state.assessment == recovery_assessment_view(assessment)


def test_assessment_and_presentation_workflow_does_not_mutate_filesystem(
    tmp_path: Path,
) -> None:
    manifest_path, source, destination = _recovery_fixture(
        tmp_path, current_content=b"historical payload"
    )
    destination_link = tmp_path / "destination-link"
    destination_link.symlink_to(destination)
    before = _snapshot(tmp_path)

    state = controller.assess_manifest(DesktopState(str(manifest_path)))

    assert state.assessment is not None
    assert _snapshot(tmp_path) == before
    assert not source.exists()
    assert destination.read_bytes() == b"historical payload"
    assert destination_link.is_symlink()
    assert destination_link.readlink() == destination


def test_view_model_import_has_no_tkinter_dependency(tmp_path: Path) -> None:
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment["PYTHONNOUSERSITE"] = "1"
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys\n"
                "import smart_file_organizer.gui.view_model\n"
                "assert 'tkinter' not in sys.modules\n"
                "assert '_tkinter' not in sys.modules\n"
            ),
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr


def test_controller_import_has_no_tkinter_dependency(tmp_path: Path) -> None:
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment["PYTHONNOUSERSITE"] = "1"
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys\n"
                "import smart_file_organizer.gui.controller\n"
                "assert 'tkinter' not in sys.modules\n"
                "assert '_tkinter' not in sys.modules\n"
            ),
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr


def test_launcher_reports_missing_tk_support_without_traceback(tmp_path: Path) -> None:
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment["PYTHONNOUSERSITE"] = "1"
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import builtins\n"
                "real_import = builtins.__import__\n"
                "def guarded_import(name, *args, **kwargs):\n"
                "    if name in {'tkinter', '_tkinter'}:\n"
                "        raise ModuleNotFoundError(name=name)\n"
                "    return real_import(name, *args, **kwargs)\n"
                "builtins.__import__ = guarded_import\n"
                "from smart_file_organizer.gui.__main__ import main\n"
                "raise SystemExit(main())\n"
            ),
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode != 0
    assert "GUI unavailable because Tk support is missing" in completed.stderr
    assert "Traceback" not in completed.stderr


def test_launcher_reports_tcl_error_without_traceback(tmp_path: Path) -> None:
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment["PYTHONNOUSERSITE"] = "1"
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys\n"
                "import types\n"
                "tk = types.ModuleType('tkinter')\n"
                "class TclError(Exception):\n"
                "    pass\n"
                "def unavailable_root():\n"
                "    raise TclError('no display available')\n"
                "tk.TclError = TclError\n"
                "tk.Tk = unavailable_root\n"
                "tk.filedialog = types.ModuleType('tkinter.filedialog')\n"
                "tk.ttk = types.ModuleType('tkinter.ttk')\n"
                "sys.modules['tkinter'] = tk\n"
                "sys.modules['tkinter.filedialog'] = tk.filedialog\n"
                "sys.modules['tkinter.ttk'] = tk.ttk\n"
                "from smart_file_organizer.gui.__main__ import main\n"
                "raise SystemExit(main())\n"
            ),
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode != 0
    assert "GUI unavailable: no display available" in completed.stderr
    assert "Traceback" not in completed.stderr


def test_core_api_and_cli_imports_do_not_import_tkinter_or_gui(
    tmp_path: Path,
) -> None:
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment["PYTHONNOUSERSITE"] = "1"
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys\n"
                "import smart_file_organizer\n"
                "import smart_file_organizer.api\n"
                "import smart_file_organizer.cli\n"
                "assert 'tkinter' not in sys.modules\n"
                "assert '_tkinter' not in sys.modules\n"
                "assert not any(name.startswith('smart_file_organizer.gui') "
                "for name in sys.modules)\n"
            ),
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr


def _gui_api_boundary_violations(source: str) -> tuple[str, ...]:
    tree = ast.parse(source)
    api_aliases: set[str] = set()
    gui_module_aliases: set[str] = set()
    importlib_aliases: set[str] = set()
    import_module_aliases: set[str] = set()
    violations: list[str] = []
    public_names = set(api.__all__)

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level == 2 and module == "api":
                for name in node.names:
                    if name.name not in public_names:
                        violations.append(f"non-public API import: {name.name}")
                continue
            if node.level > 1:
                violations.append("forbidden relative package import")
                continue
            if node.level == 1:
                if any(name.name == "api" for name in node.names):
                    violations.append("forbidden GUI-local api re-export")
                for name in node.names:
                    if name.name != "api":
                        gui_module_aliases.add(name.asname or name.name)
            elif module == "smart_file_organizer":
                for name in node.names:
                    if name.name != "api":
                        violations.append(f"forbidden package import: {name.name}")
                    else:
                        api_aliases.add(name.asname or name.name)
            elif module == "smart_file_organizer.api":
                for name in node.names:
                    if name.name not in public_names:
                        violations.append(f"non-public API import: {name.name}")
            elif module == "importlib":
                for name in node.names:
                    if name.name == "import_module":
                        import_module_aliases.add(name.asname or name.name)
            elif module.startswith("smart_file_organizer") and not (
                module == "smart_file_organizer.gui"
                or module.startswith("smart_file_organizer.gui.")
            ):
                violations.append(f"forbidden module import: {module}")
            elif module == "smart_file_organizer.gui" or module.startswith(
                "smart_file_organizer.gui."
            ):
                for name in node.names:
                    if name.name == "api":
                        violations.append("forbidden GUI-local api re-export")
                    else:
                        gui_module_aliases.add(name.asname or name.name)
        elif isinstance(node, ast.Import):
            for name in node.names:
                if name.name == "smart_file_organizer.api":
                    if name.asname is not None:
                        api_aliases.add(name.asname)
                elif name.name == "importlib" or name.name.startswith("importlib."):
                    importlib_aliases.add(name.asname or "importlib")
                elif name.name.startswith("smart_file_organizer.gui."):
                    if name.asname is not None:
                        gui_module_aliases.add(name.asname)
                elif name.name.startswith("smart_file_organizer") and not (
                    name.name == "smart_file_organizer.gui"
                    or name.name.startswith("smart_file_organizer.gui.")
                ):
                    violations.append(f"forbidden module import: {name.name}")

    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id in api_aliases and node.attr not in public_names:
                violations.append(f"non-public API attribute: {node.attr}")
            elif node.value.id in gui_module_aliases and node.attr == "api":
                violations.append("forbidden GUI-local api member access")
        elif (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Attribute)
            and isinstance(node.value.value, ast.Name)
            and node.value.value.id == "smart_file_organizer"
            and node.value.attr == "api"
            and node.attr not in public_names
        ):
            violations.append(f"non-public API attribute: {node.attr}")
        elif (
            isinstance(node, ast.Attribute)
            and node.attr == "api"
            and _attribute_name(node.value).startswith("smart_file_organizer.gui.")
        ):
            violations.append("forbidden GUI-local api member access")
        elif isinstance(node, ast.Call):
            target = (
                node.args[0]
                if node.args
                else next(
                    (
                        keyword.value
                        for keyword in node.keywords
                        if keyword.arg == "name"
                    ),
                    None,
                )
            )
            if not isinstance(target, ast.Constant) or not isinstance(
                target.value, str
            ):
                continue
            function = node.func
            is_dynamic_import = (
                isinstance(function, ast.Name)
                and (
                    function.id == "__import__" or function.id in import_module_aliases
                )
            ) or (
                isinstance(function, ast.Attribute)
                and function.attr == "import_module"
                and isinstance(function.value, ast.Name)
                and function.value.id in importlib_aliases
            )
            if is_dynamic_import and _is_internal_package_module(target.value):
                violations.append(f"forbidden dynamic import: {target.value}")

    return tuple(violations)


def _attribute_name(node: ast.expr) -> str:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return ""
    return ".".join((node.id, *reversed(parts)))


def _is_internal_package_module(module: str) -> bool:
    return module.startswith("smart_file_organizer.") and not (
        module == "smart_file_organizer.api"
        or module == "smart_file_organizer.gui"
        or module.startswith("smart_file_organizer.gui.")
    )


def test_gui_modules_do_not_bypass_the_supported_api() -> None:
    gui_root = Path(controller.__file__).parent

    violations = {
        path.name: found
        for path in sorted(gui_root.glob("*.py"))
        if (found := _gui_api_boundary_violations(path.read_text(encoding="utf-8")))
    }

    assert violations == {}


@pytest.mark.parametrize(
    "source",
    [
        "from smart_file_organizer import application",
        "from smart_file_organizer import manifest_models",
        "from smart_file_organizer.manifest_models import RecoveryPlan",
        "import smart_file_organizer.recovery_safety",
        "import smart_file_organizer.application as app",
        "from .. import application",
        "from ..application import something",
        "from smart_file_organizer import api\napi._private_name",
        "import smart_file_organizer.api as facade\nfacade._private_name",
        "from smart_file_organizer.api import _private_name",
        "from smart_file_organizer.gui.controller import api\napi._private_name",
        "from .controller import api\napi._private_name",
        (
            "from smart_file_organizer.gui import controller\n"
            "controller.api._private_name"
        ),
        (
            "import smart_file_organizer.gui.controller as controller\n"
            "controller.api._private_name"
        ),
        (
            "import smart_file_organizer.gui.controller\n"
            "smart_file_organizer.gui.controller.api._private_name"
        ),
        (
            "import importlib\n"
            'importlib.import_module("smart_file_organizer.application")'
        ),
        (
            "import importlib\n"
            'importlib.import_module(name="smart_file_organizer.application")'
        ),
        (
            "import importlib as il\n"
            'il.import_module("smart_file_organizer.application")'
        ),
        (
            "from importlib import import_module\n"
            'import_module("smart_file_organizer.application")'
        ),
        (
            "from importlib import import_module\n"
            'import_module(name="smart_file_organizer.application")'
        ),
        (
            "import importlib.util\n"
            'importlib.import_module("smart_file_organizer.application")'
        ),
        '__import__("smart_file_organizer.application")',
        '__import__(name="smart_file_organizer.application")',
    ],
)
def test_gui_api_boundary_rejects_internal_bypasses(source: str) -> None:
    assert _gui_api_boundary_violations(source)


@pytest.mark.parametrize(
    "source",
    [
        "import smart_file_organizer.api as api\napi.assess_recovery",
        "from smart_file_organizer import api\napi.RecoveryAssessment",
        "from smart_file_organizer.api import assess_recovery",
        "from smart_file_organizer.api import RecoveryAssessment as Assessment",
        "from ..api import assess_recovery",
        "from ..api import RecoveryAssessment as Assessment",
        "from smart_file_organizer.gui import controller",
        ('import importlib\nimportlib.import_module(name="smart_file_organizer.api")'),
    ],
)
def test_gui_api_boundary_accepts_public_facade_and_gui_imports(source: str) -> None:
    assert _gui_api_boundary_violations(source) == ()
