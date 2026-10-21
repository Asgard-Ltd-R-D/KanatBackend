"""Serving a file in byte ranges (HTTP Range, RFC 9110), which a <video> needs
to read an MP4's index and to seek. Starlette's FileResponse answers ranges only
from 0.39; this backend is on 0.38 (pinned by FastAPI 0.115)."""
import re
from collections.abc import Iterator
from pathlib import Path

from fastapi import Response
from fastapi.responses import FileResponse, StreamingResponse

CHUNK = 256 * 1024
# One range: ASCII digits only (RFC 9110's DIGIT), unlike int(), which also
# takes signs, spaces, underscores and other scripts' digits
_RANGE = re.compile(r"([0-9]*)-([0-9]*)")


class Unsatisfiable(Exception):
    """The range starts beyond the end of the file."""


def parse_range(header: str | None, size: int) -> tuple[int, int] | None:
    """The first range of a Range header as inclusive (start, end), or None to
    send the whole file, as for a malformed one. Raises Unsatisfiable for a
    range past the end."""
    if not header or not header.startswith("bytes="):
        return None
    spec = _RANGE.fullmatch(header[len("bytes="):].split(",")[0].strip())
    if spec is None or spec[0] == "-":
        return None
    first, last = spec.groups()
    if first == "":
        # "-n": the last n bytes
        n = int(last)
        if n <= 0:
            raise Unsatisfiable
        return max(size - n, 0), size - 1
    start = int(first)
    end = int(last) if last else size - 1
    if start >= size or start > end:
        raise Unsatisfiable
    return start, min(end, size - 1)


def _read(path: Path, start: int, end: int) -> Iterator[bytes]:
    with open(path, "rb") as f:
        f.seek(start)
        remaining = end - start + 1
        while remaining > 0:
            data = f.read(min(CHUNK, remaining))
            if not data:
                break
            remaining -= len(data)
            yield data


def file_response(path: Path, range_header: str | None, media_type: str) -> Response:
    """The file, or the requested part of it (206), always offering ranges."""
    size = path.stat().st_size
    try:
        wanted = parse_range(range_header, size)
    except Unsatisfiable:
        return Response(status_code=416, headers={"Content-Range": f"bytes */{size}"})
    if wanted is None:
        return FileResponse(path, media_type=media_type, headers={"Accept-Ranges": "bytes"})

    start, end = wanted
    return StreamingResponse(
        _read(path, start, end),
        status_code=206,
        media_type=media_type,
        headers={
            "Accept-Ranges": "bytes",
            "Content-Range": f"bytes {start}-{end}/{size}",
            "Content-Length": str(end - start + 1),
        },
    )
