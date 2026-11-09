from pydantic import BaseModel


class SystemStatus(BaseModel):
    """What the frontend shows in its status indicator. The backend answering
    at all is the backend's own status."""

    video_service: bool
    detection_service: bool
    # What the Detection Service's detector runs on and with, as it last named
    # them; kept after it goes down, so shown only while it is up
    detector_device: str | None = None
    detector_model: str | None = None
