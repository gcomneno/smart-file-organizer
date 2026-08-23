"""Private regular-file payload identity primitives."""

import hashlib
import os
import stat
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


_FINGERPRINT_CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True, slots=True)
class _Fingerprint:
    digest: str
    size_bytes: int
    observed_at: datetime


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _fingerprint_regular_file(path: Path) -> _Fingerprint:
    """Observe one regular-file payload through one complete bounded stream."""
    try:
        initial = path.lstat()
    except (OSError, ValueError) as error:
        raise OSError(f"could not fingerprint regular file: {path}: {error}") from error
    if not stat.S_ISREG(initial.st_mode):
        raise OSError(f"fingerprint path is not a regular file: {path}")

    # O_NONBLOCK is best-effort portability protection: platforms that expose it
    # avoid blocking if a regular file is replaced by a FIFO before open.
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(path, flags)
    except (OSError, ValueError) as error:
        raise OSError(f"could not fingerprint regular file: {path}: {error}") from error

    try:
        current = os.fstat(descriptor)
        if not stat.S_ISREG(current.st_mode):
            raise OSError(f"fingerprint path is not a regular file: {path}")
        if (current.st_dev, current.st_ino) != (initial.st_dev, initial.st_ino):
            raise OSError(f"fingerprint path changed during observation: {path}")

        digest = hashlib.sha256()
        size_bytes = 0
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = -1
            while chunk := stream.read(_FINGERPRINT_CHUNK_SIZE):
                digest.update(chunk)
                size_bytes += len(chunk)
    finally:
        if descriptor != -1:
            os.close(descriptor)

    return _Fingerprint(
        digest=digest.hexdigest(),
        size_bytes=size_bytes,
        observed_at=_utc_now(),
    )
