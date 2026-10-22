from pydantic import BaseModel


class SystemStatus(BaseModel):
    """What the frontend shows in its status indicator. The backend answering
    at all is the backend's own status."""

    video_service: bool
    detection_service: bool
