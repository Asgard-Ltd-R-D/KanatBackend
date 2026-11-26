import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session as DBSession

from app.core.deps import get_db
from app.services import baseline_image as svc

router = APIRouter(prefix="/sessions/{session_id}/cameras/{alias}/baseline-image", tags=["baseline-image"])


# A baseline frame is a few MB at most; anything bigger is refused unread
MAX_BYTES = 25 * 1024 * 1024


@router.post("", status_code=204)
async def upload_baseline_image(session_id: uuid.UUID, alias: str, request: Request,
                                taken_at: datetime, replace: bool = False, db: DBSession = Depends(get_db)):
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="Baseline image is too large")
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_BYTES:
            raise HTTPException(status_code=413, detail="Baseline image is too large")
        chunks.append(chunk)
    await run_in_threadpool(svc.store, db, session_id, alias, request.headers.get("content-type"), b"".join(chunks),
                            taken_at, replace)
    return Response(status_code=204)


@router.get("")
def get_baseline_image(session_id: uuid.UUID, alias: str, taken_at: datetime,
                       db: DBSession = Depends(get_db)):
    found = svc.read(db, session_id, alias, taken_at)
    if found is None:
        raise HTTPException(status_code=404, detail="No baseline image for this camera")
    data, media_type = found
    return Response(content=data, media_type=media_type)
