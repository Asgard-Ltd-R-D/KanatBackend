"""A Run's captured baseline camera frame: stored as a file under the log
directory (beside the debug recorder's), its relative path kept on the Run."""
import hashlib
import re
import uuid
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.orm import Session as DBSession

from app.core.logs import log_dir
from app.repositories import runs as runs_repo

EXTENSIONS = {"image/png": ".png", "image/jpeg": ".jpg"}
_MEDIA_TYPES = {".png": "image/png", ".jpg": "image/jpeg"}
# Names Windows refuses for a file, whatever its extension
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def _safe_name(alias: str) -> str:
    """The alias as a filename valid on every OS: unusual characters replaced,
    reserved names prefixed, and a short digest of the alias appended so two
    aliases that sanitise alike do not share a file."""
    stem = re.sub(r"[^A-Za-z0-9_-]", "_", alias).strip("_")[:40] or "camera"
    if stem.upper() in _RESERVED:
        stem = f"_{stem}"
    return f"{stem}-{hashlib.sha1(alias.encode()).hexdigest()[:8]}"


def store(db: DBSession, session_id: uuid.UUID, alias: str, content_type: str | None, data: bytes) -> None:
    """Writes the image and records it on the camera's latest Run: 415 for a
    type other than PNG or JPEG, 404 when the camera has no Run in the Session."""
    extension = EXTENSIONS.get((content_type or "").split(";")[0].strip().lower())
    if extension is None:
        raise HTTPException(status_code=415, detail="Baseline image must be image/png or image/jpeg")
    run = runs_repo.latest(db, session_id, alias)
    if run is None:
        raise HTTPException(status_code=404, detail="No Run for this camera in the Session")
    # A re-upload replaces the Run's image, whatever its type, rather than orphaning it
    if run.baseline_image_path:
        previous = absolute_path(run.baseline_image_path)
        if previous is not None:
            previous.unlink()
    taken = run.taken_at.strftime("%Y%m%dT%H%M%S%f")
    relative = Path("baseline-images") / str(session_id) / f"{_safe_name(alias)}-{taken}{extension}"
    target = log_dir() / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    run.baseline_image_path = relative.as_posix()
    runs_repo.save(db)


def latest_baseline_image_path(db: DBSession, session_id: uuid.UUID, alias: str) -> str | None:
    """The latest Run's stored image path, relative to the log directory, or
    None when there is no Run or it has no image."""
    run = runs_repo.latest(db, session_id, alias)
    return run.baseline_image_path if run else None


def absolute_path(relative: str) -> Path | None:
    """The stored file for a relative path, or None if it is missing or lies
    outside the log directory."""
    base = log_dir().resolve()
    path = (base / relative).resolve()
    return path if path.is_relative_to(base) and path.is_file() else None


def media_type(path: Path) -> str:
    return _MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream")
