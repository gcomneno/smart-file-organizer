"""Application logging setup."""

import logging

_LOG_FORMAT = "%(levelname)s %(name)s %(message)s"


def configure_logging(*, verbose: bool = False) -> None:
    """Configure application logging.

    Logging is quiet by default. Verbose mode enables high-level application events.
    """
    level = logging.INFO if verbose else logging.WARNING

    logging.basicConfig(
        level=level,
        format=_LOG_FORMAT,
        force=True,
    )
