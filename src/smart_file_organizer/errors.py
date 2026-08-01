"""Application-specific exceptions for smart-file-organizer."""


class SourceSelectionError(ValueError):
    """Raised when CLI source selection is invalid."""


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
