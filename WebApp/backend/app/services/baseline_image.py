"""A Run's captured baseline camera frame: stored as a file under the log
directory (beside the debug recorder's), its relative path kept on the Run."""
import hashlib
import io
import logging
import re
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.orm import Session as DBSession

from app.core.locks import db_write
from app.core.logs import log_dir
from app.repositories import runs as runs_repo

EXTENSIONS = {"image/png": ".png", "image/jpeg": ".jpg"}
_MEDIA_TYPES = {".png": "image/png", ".jpg": "image/jpeg"}
log = logging.getLogger(__name__)

# A camera frame is a few megapixels; far beyond that is refused undecoded
MAX_PIXELS = 50_000_000
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


def _decoded(data: bytes) -> tuple[bytes, str]:
    """The upload decoded as a PNG or JPEG and encoded again, with its
    extension: 415 for anything else. Only the decoded pixels are kept, so a
    file that merely claims to be an image (an SVG, say, which the PDF
    renderer would otherwise parse) is never stored."""
    from PIL import Image, UnidentifiedImageError

    try:
        with Image.open(io.BytesIO(data), formats=["PNG", "JPEG"]) as image:
            if image.width * image.height > MAX_PIXELS:
                raise HTTPException(status_code=413, detail="Baseline image is too large")
            image.load()
            # Only the pixels: no ICC profile, text chunks or EXIF carried over
            image.info.clear()
            out = io.BytesIO()
            if image.format == "PNG":
                image.save(out, format="PNG")
                return out.getvalue(), ".png"
            image.save(out, format="JPEG", quality=95)
            return out.getvalue(), ".jpg"
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError, SyntaxError):
        raise HTTPException(status_code=415, detail="Baseline image is not a valid PNG or JPEG image")


def store(db: DBSession, session_id: uuid.UUID, alias: str, content_type: str | None, data: bytes,
          taken_at: datetime, replace: bool = False) -> None:
    """Writes the image and records it on the camera's Run taken at `taken_at`
    (the one the frame was captured for): 415 for a type other than PNG or
    JPEG, 404 when there is no such Run, 409 when the Run already has one and
    `replace` is not set (a second tab's later frame never replaces the
    Run's baseline). Each upload gets a file of its own,
    recorded only once written, and the one it replaces is removed under the
    same lock: two uploads at once never delete or truncate each other's file,
    and a Session deleted meanwhile cannot get its folder back."""
    if EXTENSIONS.get((content_type or "").split(";")[0].strip().lower()) is None:
        raise HTTPException(status_code=415, detail="Baseline image must be image/png or image/jpeg")
    data, extension = _decoded(data)
    with db_write:
        run = runs_repo.get_for_update(db, session_id, alias, taken_at)
        if run is None:
            raise HTTPException(status_code=404, detail="No such Run for this camera in the Session")
        if run.baseline_image_path and not replace:
            raise HTTPException(status_code=409, detail="This Run already has a baseline image")
        previous_relative = run.baseline_image_path
        taken = run.taken_at.strftime("%Y%m%dT%H%M%S%f")
        name = f"{_safe_name(alias)}-{taken}-{uuid.uuid4().hex[:8]}{extension}"
        relative = Path("baseline-images") / str(session_id) / name
        target = log_dir() / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            target.write_bytes(data)
            run.baseline_image_path = relative.as_posix()
            runs_repo.save(db)
        except Exception:
            # The Run keeps its previous image; the half-written one goes
            target.unlink(missing_ok=True)
            raise
        if previous_relative and previous_relative != run.baseline_image_path:
            _remove(absolute_path(previous_relative))


def _remove(path: Path | None) -> None:
    """Deletes a replaced image; one held open (a download on Windows) is left,
    logged, rather than failing the upload that replaced it."""
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError:
        log.warning("Could not remove a replaced baseline image", extra={"path": str(path)}, exc_info=True)


def read(db: DBSession, session_id: uuid.UUID, alias: str, taken_at: datetime) -> tuple[bytes, str] | None:
    """The image of the Run taken at `taken_at` and its media type, or None
    when there is no such Run or it has no image. Read under the write lock,
    so a re-upload cannot remove the file between finding and reading it."""
    with db_write:
        run = runs_repo.get_for_update(db, session_id, alias, taken_at)
        path = absolute_path(run.baseline_image_path) if run and run.baseline_image_path else None
        if path is None:
            return None
        try:
            return path.read_bytes(), media_type(path)
        except FileNotFoundError:
            return None


def absolute_path(relative: str) -> Path | None:
    """The stored file for a relative path, or None if it is missing or lies
    outside the log directory."""
    base = log_dir().resolve()
    path = (base / relative).resolve()
    return path if path.is_relative_to(base) and path.is_file() else None


def media_type(path: Path) -> str:
    return _MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream")
