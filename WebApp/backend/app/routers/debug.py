"""TEMPORARY debug endpoints (delete before production), paired with
app/services/debug_recorder.py and one button in the frontend. They record a
live session's raw camera stream, logs and app view into one folder.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from app.core.deps import get_db
from app.repositories import cameras as cameras_repo
from app.services import debug_recorder

router = APIRouter(prefix="/debug/recordings", tags=["debug"])


class StartBody(BaseModel):
    camera: str | None = None  # alias; defaults to the one enabled camera


class StartedRecording(BaseModel):
    id: str
    folder: str


class StoppedRecording(BaseModel):
    folder: str


def _resolve_camera(alias: str | None, db: DBSession):
    cameras = cameras_repo.list_all(db)
    if alias is not None:
        match = next((c for c in cameras if c.alias == alias), None)
        if match is None:
            raise HTTPException(404, f"no camera named {alias!r}")
        return match
    enabled = [c for c in cameras if c.enabled]
    if len(enabled) != 1:
        raise HTTPException(400, f"name the camera to record: {len(enabled)} are enabled")
    return enabled[0]


@router.post("", response_model=StartedRecording)
async def start_recording(body: StartBody, db: DBSession = Depends(get_db)):
    camera = _resolve_camera(body.camera, db)
    return await run_in_threadpool(debug_recorder.start, camera)


@router.post("/{recording_id}/overlay", status_code=204)
async def upload_overlay(recording_id: str, request: Request):
    # The renderer POSTs the recorded blob as the raw body (video/webm or
    # video/mp4), so no multipart dependency is needed for this debug feature.
    data = await request.body()
    webm = "webm" in (request.headers.get("content-type") or "")
    try:
        await run_in_threadpool(debug_recorder.save_overlay, recording_id, data, webm)
    except KeyError:
        raise HTTPException(404, "no such recording")


@router.post("/{recording_id}/stop", response_model=StoppedRecording)
async def stop_recording(recording_id: str):
    try:
        return await run_in_threadpool(debug_recorder.stop, recording_id)
    except KeyError:
        raise HTTPException(404, "no such recording")
