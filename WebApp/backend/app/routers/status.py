from fastapi import APIRouter

from app.schemas.status import SystemStatus
from app.services import mediamtx

router = APIRouter(prefix="/status", tags=["status"])


@router.get("", response_model=SystemStatus)
def system_status():
    return SystemStatus(video_service=mediamtx.is_reachable())
