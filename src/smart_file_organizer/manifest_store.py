"""Safe operational access to apply manifests; no filesystem mutation."""

import errno
import os
import re
import stat
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from smart_file_organizer.errors import (
    ManifestAccessError,
    ManifestError,
    ManifestFormatError,
    ManifestPathError,
)
from smart_file_organizer.manifest_models import (
    ApplyManifest,
    ManifestReference,
    ManifestReferenceStatus,
)
from smart_file_organizer.manifest_schema import loads_manifest


_MANIFEST_RELATIVE_DIRECTORY = Path(".smart-file-organizer") / "manifests"
_MANIFEST_NAME = re.compile(r"apply-\d{8}T\d{12}Z-[0-9a-f]{12}\.json\Z")
_DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
_FILE_FLAGS = os.O_RDONLY | os.O_NOFOLLOW


class ManifestStore:
    """Concrete boundary for strict manifest loading and deterministic listing."""

    def __init__(self, *, schema_version: int) -> None:
        self._schema_version = schema_version

    def load(self, path: Path) -> ApplyManifest:
        """Load one manifest only from its declared target's safe store directory."""
        candidate = _absolute_path(path)
        _require_manifest_name(candidate.name)
        target_root = _target_root_for_manifest_path(candidate)
        with _target_root_fd(target_root) as root_fd:
            with _child_directory_fd(
                root_fd, ".smart-file-organizer", allow_missing=False
            ) as metadata_fd:
                assert metadata_fd is not None
                with _child_directory_fd(
                    metadata_fd, "manifests", allow_missing=False
                ) as manifest_fd:
                    assert manifest_fd is not None
                    return self._load_from_directory(
                        manifest_fd, candidate.name, candidate, target_root
                    )

    def list_for_target(self, target_root: Path) -> tuple[ManifestReference, ...]:
        """List only recognized direct manifest filename candidates by name."""
        root = _absolute_path(target_root)
        with _target_root_fd(root) as root_fd:
            with _child_directory_fd(
                root_fd, ".smart-file-organizer", allow_missing=True
            ) as metadata_fd:
                if metadata_fd is None:
                    return ()
                with _child_directory_fd(
                    metadata_fd, "manifests", allow_missing=True
                ) as manifest_fd:
                    if manifest_fd is None:
                        return ()
                    try:
                        names = sorted(
                            name
                            for name in os.listdir(manifest_fd)
                            if _MANIFEST_NAME.fullmatch(name)
                        )
                    except OSError as error:
                        raise ManifestAccessError(
                            "manifest directory cannot be inspected"
                        ) from error
                    directory = root / _MANIFEST_RELATIVE_DIRECTORY
                    return tuple(
                        self._reference_for_name(manifest_fd, directory / name, root)
                        for name in names
                    )

    def _reference_for_name(
        self, directory_fd: int, path: Path, target_root: Path
    ) -> ManifestReference:
        try:
            manifest = self._load_from_directory(
                directory_fd, path.name, path, target_root
            )
        except ManifestError as error:
            return ManifestReference(
                path=path,
                status=ManifestReferenceStatus.INVALID,
                error_code=_error_code(error),
            )
        return ManifestReference(
            path=path,
            status=ManifestReferenceStatus.VALID,
            manifest=manifest,
        )

    def _load_from_directory(
        self, directory_fd: int, name: str, path: Path, target_root: Path
    ) -> ApplyManifest:
        text = _read_manifest_file(directory_fd, name)
        manifest = loads_manifest(
            text, path=path, expected_version=self._schema_version
        )
        if manifest.target_root != target_root:
            raise ManifestPathError(
                "manifest location disagrees with declared target root"
            )
        _require_operational_location(directory_fd, manifest.target_root)
        return manifest


def _error_code(error: ManifestError) -> str:
    if isinstance(error, ManifestPathError):
        return "unsafe_path"
    if isinstance(error, ManifestAccessError):
        return "unreadable"
    if isinstance(error, ManifestFormatError):
        return "invalid_manifest"
    return "invalid_manifest"


def _require_manifest_name(name: str) -> None:
    if not _MANIFEST_NAME.fullmatch(name):
        raise ManifestPathError("manifest filename is not supported")


def _target_root_for_manifest_path(path: Path) -> Path:
    """Return the lexical target-root spelling for one manifest pathname."""
    directory = path.parent
    if (
        directory.name != "manifests"
        or directory.parent.name != ".smart-file-organizer"
    ):
        raise ManifestPathError("manifest path is outside the manifest directory")
    return directory.parent.parent


def _absolute_path(path: Path) -> Path:
    """Return an absolute lexical path without observing the filesystem."""
    try:
        return Path(os.path.abspath(path))
    except (OSError, ValueError) as error:
        raise ManifestPathError("manifest path is invalid") from error


@contextmanager
def _target_root_fd(path: Path) -> Iterator[int]:
    """Resolve the designated root alias, then safely open its physical directory."""
    with _directory_fd(_resolve_target_root(path)) as descriptor:
        yield descriptor


def _resolve_target_root(path: Path) -> Path:
    """Resolve only the caller-designated root alias before safe traversal below it."""
    if not path.is_absolute():
        raise ManifestPathError("manifest path must be absolute")
    try:
        return path.resolve(strict=True)
    except RuntimeError as error:
        raise ManifestPathError(
            "manifest target root symlink cannot be resolved"
        ) from error
    except (OSError, ValueError) as error:
        raise _target_root_error(error) from error


def _target_root_error(error: OSError | ValueError) -> ManifestError:
    if isinstance(error, OSError) and error.errno in {errno.ENOENT, errno.ENOTDIR}:
        return ManifestPathError("manifest target root does not exist")
    if isinstance(error, OSError) and error.errno == errno.ELOOP:
        return ManifestPathError("manifest target root symlink cannot be resolved")
    return ManifestAccessError("manifest target root cannot be inspected")


@contextmanager
def _directory_fd(path: Path) -> Iterator[int]:
    """Open every absolute path component without following a symlink."""
    if not path.is_absolute():
        raise ManifestPathError("manifest path must be absolute")
    try:
        descriptor = os.open(path.anchor, _DIRECTORY_FLAGS)
    except OSError as error:
        raise _directory_error(error) from error
    try:
        for component in path.parts[1:]:
            next_descriptor = _open_directory_component(descriptor, component)
            os.close(descriptor)
            descriptor = next_descriptor
        yield descriptor
    finally:
        os.close(descriptor)


@contextmanager
def _child_directory_fd(
    parent_fd: int, name: str, *, allow_missing: bool
) -> Iterator[int | None]:
    """Open one known child directory from an already safe parent descriptor."""
    try:
        descriptor = _open_directory_component(parent_fd, name)
    except ManifestPathError as error:
        if (
            allow_missing
            and error.__cause__ is not None
            and isinstance(error.__cause__, FileNotFoundError)
        ):
            yield None
            return
        raise
    try:
        yield descriptor
    finally:
        os.close(descriptor)


def _open_directory_component(parent_fd: int, name: str) -> int:
    try:
        return os.open(name, _DIRECTORY_FLAGS, dir_fd=parent_fd)
    except OSError as error:
        raise _directory_error(error) from error


def _directory_error(error: OSError) -> ManifestError:
    if error.errno == errno.ENOENT:
        return ManifestPathError("manifest directory does not exist")
    if error.errno in {errno.ELOOP, errno.ENOTDIR}:
        return ManifestPathError("manifest path symlinks are not supported")
    return ManifestAccessError("manifest directory cannot be inspected")


def _read_manifest_file(directory_fd: int, name: str) -> str:
    _require_manifest_name(name)
    try:
        descriptor = os.open(name, _FILE_FLAGS, dir_fd=directory_fd)
    except OSError as error:
        if error.errno in {errno.ELOOP, errno.ENOTDIR}:
            raise ManifestPathError(
                "manifest file symlinks are not supported"
            ) from error
        if error.errno == errno.ENOENT:
            raise ManifestPathError("manifest path does not exist") from error
        raise ManifestAccessError("manifest cannot be read") from error
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ManifestPathError("manifest path is not a regular file")
        try:
            with os.fdopen(descriptor, "r", encoding="utf-8") as stream:
                descriptor = -1
                return stream.read()
        except (OSError, UnicodeError) as error:
            raise ManifestAccessError("manifest cannot be read") from error
    finally:
        if descriptor != -1:
            os.close(descriptor)


def _require_operational_location(directory_fd: int, target_root: Path) -> None:
    """Require the opened file's directory to be the target's live store."""
    with _target_root_fd(target_root) as root_fd:
        with _child_directory_fd(
            root_fd, ".smart-file-organizer", allow_missing=False
        ) as metadata_fd:
            assert metadata_fd is not None
            with _child_directory_fd(
                metadata_fd, "manifests", allow_missing=False
            ) as expected_fd:
                assert expected_fd is not None
                if not _same_directory(directory_fd, expected_fd):
                    raise ManifestPathError(
                        "manifest location disagrees with target root"
                    )


def _same_directory(first_fd: int, second_fd: int) -> bool:
    first, second = os.fstat(first_fd), os.fstat(second_fd)
    return (first.st_dev, first.st_ino) == (second.st_dev, second.st_ino)
