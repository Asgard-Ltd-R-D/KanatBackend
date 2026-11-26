import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session as DBSession

from app.core.deps import get_db
from app.services import baseline_image as svc

router = APIRouter(prefix="/sessions/{session_id}/cameras/{alias}/baseline-image", tags=["baseline-image"])


# A baseline frame is a few MB at most; anything bigger is refused unread
MAX_BYTES = 25 * 1024 * 1024


@router.post("", status_code=204)
async def upload_baseline_image(session_id: uuid.UUID, alias: str, request: Request, db: DBSession = Depends(get_db)):
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="Baseline image is too large")
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_BYTES:
            raise HTTPException(status_code=413, detail="Baseline image is too large")
        chunks.append(chunk)
    await run_in_threadpool(svc.store, db, session_id, alias, request.headers.get("content-type"), b"".join(chunks))
    return Response(status_code=204)


@router.get("")
def get_baseline_image(session_id: uuid.UUID, alias: str, db: DBSession = Depends(get_db)):
    relative = svc.latest_baseline_image_path(db, session_id, alias)
    path = svc.absolute_path(relative) if relative else None
    if path is None:
        raise HTTPException(status_code=404, detail="No baseline image for this camera")
    return FileResponse(path, media_type=svc.media_type(path))
