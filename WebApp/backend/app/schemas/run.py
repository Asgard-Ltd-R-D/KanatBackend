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
    # One point per Baseline Mark, in template coordinates; none on a Run
    # stored before the Detection Service sent them
    baseline_marks: list[Point] = []


class Place(BaseModel):
    """Where a Run's registered Look showed the Board in the camera's picture
    (ADR-0009)."""

    # The Look's frame time, on the clock of the Bullet Holes' first_seen_at
    at: AwareDatetime
    # Template coordinates onto the Look's frame px, row-major
    template_to_picture: tuple[Row, Row, Row]


class RunResponse(BaseModel):
    """One Run of the Detection Service that watched the Session."""

    model_config = ConfigDict(from_attributes=True)

    camera_alias: str
    taken_at: datetime
    # Its latest Look's frame time the backend has read, registered or Lost
    watched_until: datetime
    baseline_view: BaselineView
    # Where it registered the Board, in time order, starting with the
    # baseline's: each kept once it moved more than a couple of px
    places: list[Place]
