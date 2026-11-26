import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session as DBSession

from app.core.deps import get_db
from app.services import baseline_image as svc

router = APIRouter(prefix="/sessions/{session_id}/cameras/{alias}/baseline-image", tags=["baseline-image"])


@router.post("", status_code=204)
async def upload_baseline_image(session_id: uuid.UUID, alias: str, request: Request, db: DBSession = Depends(get_db)):
    svc.store(db, session_id, alias, request.headers.get("content-type"), await request.body())
    return Response(status_code=204)


@router.get("")
def get_baseline_image(session_id: uuid.UUID, alias: str, db: DBSession = Depends(get_db)):
    relative = svc.latest_baseline_image_path(db, session_id, alias)
    path = svc.absolute_path(relative) if relative else None
    if path is None:
        raise HTTPException(status_code=404, detail="No baseline image for this camera")
    return FileResponse(path, media_type=svc.media_type(path))
