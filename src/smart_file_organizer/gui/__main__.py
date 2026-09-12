"""Module launcher for the optional stdlib tkinter desktop adapter."""

import sys


def main() -> int:
    """Launch the GUI, reporting unavailable Tk support without a traceback."""
    try:
        from smart_file_organizer.gui.tk_app import main as run
    except ModuleNotFoundError as error:
        if error.name not in {"tkinter", "_tkinter"}:
            raise
        print(
            "smart-file-organizer: GUI unavailable because Tk support is missing",
            file=sys.stderr,
        )
        return 1
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
