import asyncio

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool

from app.schemas.status import SystemStatus
from app.services import detection_client, mediamtx

router = APIRouter(prefix="/status", tags=["status"])


@router.get("", response_model=SystemStatus)
async def system_status():
    # Asked side by side, so the answer waits for the slower check, not both:
    # two that hang in a row would reach the frontend's 2 s limit
    video, detection = await asyncio.gather(
        run_in_threadpool(mediamtx.is_reachable),
        run_in_threadpool(detection_client.is_reachable),
    )
    return SystemStatus(video_service=video, detection_service=detection)
