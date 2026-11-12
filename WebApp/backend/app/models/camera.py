import uuid
from datetime import datetime

from sqlalchemy import Boolean, Index, Integer, String, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.types import UtcDateTime


class Camera(Base):
    """A camera multicasting H.264 RTP on the range network.

    MediaMTX gets a path named after its alias; MediaMTX joins the multicast
    group on the camera's network card and reads the RTP directly.
    """

    __tablename__ = "cameras"
    # Unique whatever the case: an alias names a stream path, and Windows sees
    # Cam1 and cam1 as one name
    __table_args__ = (Index("uq_cameras_alias_ci", text("lower(alias)"), unique=True),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    alias: Mapped[str] = mapped_column(String, nullable=False)
    mcast_ip: Mapped[str] = mapped_column(String, nullable=False)
    mcast_port: Mapped[int] = mapped_column(Integer, nullable=False)
    # Network interface to join the group on; None lets the OS choose
    iface: Mapped[str | None] = mapped_column(String, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("1"))
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
