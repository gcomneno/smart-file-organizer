"""Installed package version helpers."""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as distribution_version


DISTRIBUTION_NAME = "smart-file-organizer"


def get_version() -> str:
    """Return the installed distribution version."""
    try:
        return distribution_version(DISTRIBUTION_NAME)
    except PackageNotFoundError:
        return "0+unknown"


__version__ = get_version()
