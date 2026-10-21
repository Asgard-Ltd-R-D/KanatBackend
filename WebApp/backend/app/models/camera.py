import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Camera(Base):
    """A camera multicasting H.264 RTP on the range network.

    MediaMTX gets a path named after its alias, whose run_record.sh (GStreamer)
    joins the multicast group and publishes it as RTSP.
    """

    __tablename__ = "cameras"
    __table_args__ = (UniqueConstraint("alias", name="uq_cameras_alias"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    alias: Mapped[str] = mapped_column(String, nullable=False)
    mcast_ip: Mapped[str] = mapped_column(String, nullable=False)
    mcast_port: Mapped[int] = mapped_column(Integer, nullable=False)
    # Network interface to join the group on; None lets the OS choose
    iface: Mapped[str | None] = mapped_column(String, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
