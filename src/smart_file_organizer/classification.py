"""File classification helpers."""

from pathlib import Path

from smart_file_organizer.models import FileCategory


_EXTENSION_CATEGORIES: dict[str, FileCategory] = {
    ".7z": FileCategory.ARCHIVES,
    ".gz": FileCategory.ARCHIVES,
    ".rar": FileCategory.ARCHIVES,
    ".tar": FileCategory.ARCHIVES,
    ".zip": FileCategory.ARCHIVES,
    ".flac": FileCategory.AUDIO,
    ".mp3": FileCategory.AUDIO,
    ".wav": FileCategory.AUDIO,
    ".css": FileCategory.CODE,
    ".html": FileCategory.CODE,
    ".js": FileCategory.CODE,
    ".json": FileCategory.CODE,
    ".py": FileCategory.CODE,
    ".md": FileCategory.DOCUMENTS,
    ".pdf": FileCategory.DOCUMENTS,
    ".txt": FileCategory.DOCUMENTS,
    ".doc": FileCategory.DOCUMENTS,
    ".docx": FileCategory.DOCUMENTS,
    ".gif": FileCategory.IMAGES,
    ".jpeg": FileCategory.IMAGES,
    ".jpg": FileCategory.IMAGES,
    ".png": FileCategory.IMAGES,
    ".svg": FileCategory.IMAGES,
    ".mkv": FileCategory.VIDEOS,
    ".mov": FileCategory.VIDEOS,
    ".mp4": FileCategory.VIDEOS,
    ".webm": FileCategory.VIDEOS,
}


def classify_path(path: Path) -> FileCategory:
    """Return the category for a path based on its file extension."""
    extension = path.suffix.lower()

    return _EXTENSION_CATEGORIES.get(extension, FileCategory.OTHER)
