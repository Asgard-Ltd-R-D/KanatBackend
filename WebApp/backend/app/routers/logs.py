"""Downloading the logs for support: every log file in the folder, zipped."""
import io
import logging
import zipfile
from datetime import datetime, timezone

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.core.logs import log_dir

router = APIRouter(prefix="/logs", tags=["logs"])
log = logging.getLogger(__name__)


@router.get("/export")
def export_logs():
    """Every file in the log folder (all services, every rotated day), zipped, so
    the operator can send one file to support."""
    directory = log_dir()
    buffer = io.BytesIO()
    files = 0
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        if directory.is_dir():
            for path in sorted(directory.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(directory).as_posix())
                    files += 1
    size = buffer.tell()
    buffer.seek(0)
    name = f"kanat-logs-{datetime.now(timezone.utc):%Y-%m-%d}.zip"
    log.info("Logs exported", extra={"files": files, "size_kb": round(size / 1024, 1)})
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )
