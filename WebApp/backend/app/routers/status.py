import asyncio

from fastapi import APIRouter
from starlette.concurrency import run_in_threadpool

from app.schemas.status import SystemStatus
from app.services import detection_service, mediamtx

router = APIRouter(prefix="/status", tags=["status"])


@router.get("", response_model=SystemStatus)
async def system_status():
    # Asked side by side, so a service that hangs costs one STATUS_TIMEOUT_S,
    # within the frontend's 2 s limit, however many hang
    video, detection = await asyncio.gather(
        run_in_threadpool(mediamtx.is_reachable),
        run_in_threadpool(detection_service.is_reachable),
    )
    return SystemStatus(video_service=video, detection_service=detection)
