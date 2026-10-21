from datetime import datetime

from pydantic import BaseModel


class RecordingSpan(BaseModel):
    """One unbroken stretch of recorded video."""

    start: datetime
    duration_s: float


class CameraRecording(BaseModel):
    """What a camera recorded during a Session, in time order."""

    alias: str
    spans: list[RecordingSpan]
