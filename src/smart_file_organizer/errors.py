"""Application-specific exceptions for smart-file-organizer."""


class SourceSelectionError(ValueError):
    """Raised when planning source selection is invalid."""


class ConfigError(ValueError):
    """Raised when application configuration is invalid."""


class DestinationConflictError(ValueError):
    """Raised when a plan contains destination conflicts."""


class InvalidSourceError(ValueError):
    """Raised when a source is not an allowed file."""


class SourceMissingError(InvalidSourceError, FileNotFoundError):
    """Raised when a planned source file is missing."""


class UnsafePathError(ValueError):
    """Raised when a source/target or destination path violates safety rules."""


class DestinationExistsError(FileExistsError):
    """Raised when a planned destination already exists."""


class DestinationParentError(OSError):
    """Raised when a destination parent cannot be prepared safely."""


class ManifestWriteError(OSError):
    """Raised when durable apply evidence cannot be persisted."""


class ManifestError(ValueError):
    """Base class for controlled operational manifest failures."""


class ManifestPathError(ManifestError):
    """Raised when a manifest path is outside the supported safe location."""


class ManifestAccessError(ManifestError):
    """Raised when a manifest cannot be read safely."""


class ManifestFormatError(ManifestError):
    """Raised when a manifest is malformed or incompatible."""


class BrokenSourceSymlinkError(InvalidSourceError):
    """Raised when an explicit source symlink has no existing referent."""


class UnsupportedSourceSymlinkError(InvalidSourceError):
    """Raised when a source symlink does not point to a regular file."""
