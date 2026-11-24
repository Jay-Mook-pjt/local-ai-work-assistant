"""File storage under STORAGE_DIR. All paths are generated server-side and
confined to the storage root (path traversal protection)."""

import logging
import shutil
from pathlib import Path

from app.config import get_settings

log = logging.getLogger(__name__)

ORIGINAL_DIR = "audio/original"
PROCESSED_DIR = "audio/processed"
# Per-meeting directories that are removed when a meeting is deleted.
MEETING_DIRS = (ORIGINAL_DIR, PROCESSED_DIR, "transcripts", "minutes", "exports")


class UnsafePathError(ValueError):
    pass


def root() -> Path:
    return get_settings().storage_dir


def resolve(relative: str | Path) -> Path:
    """Absolute path for a storage-relative path; refuses anything outside the root."""
    base = root().resolve()
    p = (base / relative).resolve()
    if p != base and base not in p.parents:
        raise UnsafePathError(f"path escapes storage root: {relative}")
    return p


def relative(path: Path) -> str:
    return str(path.resolve().relative_to(root().resolve()))


def meeting_dir(kind: str, meeting_id: str) -> Path:
    if not meeting_id.isalnum():
        raise UnsafePathError("invalid meeting id")
    d = resolve(Path(kind) / meeting_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def delete_meeting_files(meeting_id: str) -> None:
    if not meeting_id.isalnum():
        raise UnsafePathError("invalid meeting id")
    for kind in MEETING_DIRS:
        d = resolve(Path(kind) / meeting_id)
        if d.exists():
            shutil.rmtree(d)
            log.info("Deleted %s", relative(d))
