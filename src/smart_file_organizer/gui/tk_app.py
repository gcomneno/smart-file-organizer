"""Stdlib tkinter projection of the read-only recovery view model."""

import sys
import tkinter as tk
from tkinter import filedialog, ttk

from smart_file_organizer.gui.controller import assess_manifest
from smart_file_organizer.gui.view_model import DesktopState, RecoveryAssessmentView


class RecoveryDesktopApplication:
    """Small read-only desktop shell for recovery trust inspection."""

    def __init__(self, root: tk.Tk) -> None:
        self._root = root
        self._state = DesktopState()
        self._manifest_input = tk.StringVar()
        self._manifest_input.trace_add("write", self._manifest_changed)

        root.title("Smart File Organizer — Recovery assessment")
        root.geometry("980x720")
        root.minsize(760, 520)

        shell = ttk.Frame(root, padding=12)
        shell.pack(fill=tk.BOTH, expand=True)
        ttk.Label(
            shell,
            text="Read-only recovery assessment",
            font=("TkDefaultFont", 16, "bold"),
        ).pack(anchor=tk.W)
        ttk.Label(
            shell,
            text=(
                "Inspect the evidence and proposal layers. This prototype cannot "
                "move, delete, overwrite, or restore files."
            ),
            wraplength=900,
        ).pack(anchor=tk.W, pady=(2, 10))

        chooser = ttk.Frame(shell)
        chooser.pack(fill=tk.X)
        ttk.Entry(chooser, textvariable=self._manifest_input).pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )
        ttk.Button(chooser, text="Browse…", command=self._choose_manifest).pack(
            side=tk.LEFT, padx=(8, 0)
        )
        ttk.Button(chooser, text="Assess", command=self._assess).pack(
            side=tk.LEFT, padx=(8, 0)
        )

        self._status = ttk.Label(shell, wraplength=900)
        self._status.pack(fill=tk.X, pady=(10, 4))

        canvas = tk.Canvas(shell, highlightthickness=0)
        scrollbar = ttk.Scrollbar(shell, orient=tk.VERTICAL, command=canvas.yview)
        self._results = ttk.Frame(canvas)
        self._results.bind(
            "<Configure>",
            lambda _event: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        window = canvas.create_window((0, 0), window=self._results, anchor=tk.NW)
        canvas.bind(
            "<Configure>",
            lambda event: canvas.itemconfigure(window, width=event.width),
        )
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self._render()

    def _manifest_changed(self, *_args: str) -> None:
        self._state = self._state.with_manifest_input_write(self._manifest_input.get())
        self._render()

    def _choose_manifest(self) -> None:
        selected = filedialog.askopenfilename(
            title="Select a Smart File Organizer manifest",
            filetypes=(("JSON manifests", "*.json"), ("All files", "*")),
        )
        if selected:
            self._manifest_input.set(selected)

    def _assess(self) -> None:
        self._state = assess_manifest(self._state)
        self._render()

    def _render(self) -> None:
        for child in self._results.winfo_children():
            child.destroy()
        if self._state.diagnostic is not None:
            self._status.configure(text=self._state.diagnostic.message)
            return
        if self._state.assessment is None:
            self._status.configure(text="No current assessment.")
            return
        self._status.configure(text="Assessment complete. No files were changed.")
        self._render_assessment(self._state.assessment)

    def _render_assessment(self, assessment: RecoveryAssessmentView) -> None:
        notice = ttk.LabelFrame(self._results, text="Authority boundary", padding=10)
        notice.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(notice, text=assessment.authority_notice, wraplength=880).pack(
            anchor=tk.W
        )

        manifest = ttk.LabelFrame(
            self._results, text="Manifest historical record", padding=10
        )
        manifest.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(manifest, text=assessment.manifest_path).pack(anchor=tk.W)
        for field in assessment.manifest_fields:
            ttk.Label(manifest, text=f"{field.label}: {field.value}").pack(anchor=tk.W)

        summary = ttk.LabelFrame(self._results, text="Assessment summary", padding=10)
        summary.pack(fill=tk.X, pady=(0, 10))
        for field in assessment.summary.fields:
            ttk.Label(summary, text=f"{field.label}: {field.value}").pack(anchor=tk.W)

        for item in assessment.items:
            item_frame = ttk.LabelFrame(
                self._results, text=f"Move record {item.index}", padding=10
            )
            item_frame.pack(fill=tk.X, pady=(0, 12))
            for layer in item.layers:
                layer_frame = ttk.LabelFrame(
                    item_frame,
                    text=f"{layer.title} — {layer.state}",
                    padding=8,
                )
                layer_frame.pack(fill=tk.X, pady=4)
                for field in layer.fields:
                    ttk.Label(
                        layer_frame,
                        text=f"{field.label}: {field.value}",
                        wraplength=840,
                    ).pack(anchor=tk.W)


def main() -> int:
    """Launch the read-only recovery assessment window."""
    try:
        root = tk.Tk()
    except tk.TclError as error:
        print(f"smart-file-organizer: GUI unavailable: {error}", file=sys.stderr)
        return 1
    RecoveryDesktopApplication(root)
    root.mainloop()
    return 0
