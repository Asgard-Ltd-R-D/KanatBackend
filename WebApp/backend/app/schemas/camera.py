import uuid
from datetime import datetime
from ipaddress import IPv4Address
from typing import Annotated, Literal, Optional

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, Field

# These values go into the shell command MediaMTX runs for the camera
# (services/camera_sync.py), so each one is held to characters that cannot
# break out of it.


def _blank_to_none(value: object) -> object:
    return None if isinstance(value, str) and not value.strip() else value


def _multicast(value: IPv4Address) -> IPv4Address:
    if not value.is_multicast:
        raise ValueError("must be a multicast group, 224.0.0.0 to 239.255.255.255")
    return value


Alias = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{1,62}$")]
# The group the camera multicasts to: a unicast address would be accepted by
# run_record.sh and leave the camera on No signal for good
MulticastGroup = Annotated[IPv4Address, AfterValidator(_multicast)]
Iface = Annotated[Optional[Annotated[str, Field(pattern=r"^[A-Za-z0-9._:-]{1,32}$")]], BeforeValidator(_blank_to_none)]

# live: video is arriving from the camera. no_signal: the camera is configured,
# but no video arrives from its multicast group. disabled: switched off here.
# unreachable: MediaMTX did not answer, so the state is unknown.
CameraStatus = Literal["live", "no_signal", "disabled", "unreachable"]


class CameraInput(BaseModel):
    alias: Alias
    mcast_ip: MulticastGroup
    mcast_port: int = Field(ge=1, le=65535)
    iface: Iface = None
    enabled: bool = True


class CameraResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    alias: str
    mcast_ip: str
    mcast_port: int
    iface: Optional[str]
    enabled: bool
    created_at: datetime
    status: CameraStatus = "unreachable"
