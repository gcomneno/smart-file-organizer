"""Application-specific exceptions for smart-file-organizer."""


class SourceSelectionError(ValueError):
    """Raised when CLI source selection is invalid."""


class ConfigError(ValueError):
    """Raised when application configuration is invalid."""


class DestinationConflictError(ValueError):
    """Raised when a plan contains destination conflicts."""


class SourceMissingError(FileNotFoundError):
    """Raised when a planned source file is missing."""


class DestinationExistsError(FileExistsError):
    """Raised when a planned destination already exists."""
