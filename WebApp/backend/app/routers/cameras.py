import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session as DBSession

from app.core.deps import get_db
from app.schemas.camera import CameraInput, CameraResponse
from app.services import camera_sync
from app.services import cameras as svc

router = APIRouter(prefix="/cameras", tags=["cameras"])

# Every change is applied to MediaMTX straight away (camera_sync.sync_soon)


@router.get("", response_model=list[CameraResponse])
def list_cameras(db: DBSession = Depends(get_db)):
    return svc.with_status(svc.list_cameras(db))


def _refuse_reserved(alias: str) -> None:
    if camera_sync.taken_by_config(alias):
        raise HTTPException(status_code=409, detail=f"'{alias}' is reserved by the video service")


@router.post("", response_model=CameraResponse, status_code=201)
def create_camera(body: CameraInput, db: DBSession = Depends(get_db)):
    _refuse_reserved(body.alias)
    camera = svc.create_camera(body, db)
    camera_sync.sync_soon(db)
    return svc.with_status([camera])[0]


@router.put("/{camera_id}", response_model=CameraResponse)
def update_camera(camera_id: uuid.UUID, body: CameraInput, db: DBSession = Depends(get_db)):
    _refuse_reserved(body.alias)
    camera = svc.update_camera(camera_id, body, db)
    camera_sync.sync_soon(db)
    return svc.with_status([camera])[0]


@router.delete("/{camera_id}", status_code=204)
def delete_camera(camera_id: uuid.UUID, db: DBSession = Depends(get_db)):
    svc.delete_camera(camera_id, db)
    camera_sync.sync_soon(db)
    return Response(status_code=204)
