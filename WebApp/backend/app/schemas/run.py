from datetime import datetime

from pydantic import AwareDatetime, BaseModel, ConfigDict

Point = tuple[float, float]
Row = tuple[float, float, float]


class Picture(BaseModel):
    width: int
    height: int


class BaselineView(BaseModel):
    """Where a Run's baseline frame showed the Board in the camera's picture
    (ADR-0009), as the Detection Service's run view carries it."""

    # The baseline frame's time, on the clock of the Bullet Holes' first_seen_at
    taken_at: AwareDatetime
    # The baseline frame's size, in px
    picture: Picture
    # Template coordinates onto the baseline frame's px, row-major
    template_to_picture: tuple[Row, Row, Row]
    # One outline per Target, in template coordinates; its index is target_index
    targets: list[list[Point]]


class RunResponse(BaseModel):
    """One Run of the Detection Service that watched the Session."""

    model_config = ConfigDict(from_attributes=True)

    camera_alias: str
    taken_at: datetime
    baseline_view: BaselineView
