import uuid
from datetime import datetime
from ipaddress import IPv4Address
from typing import Annotated, Literal, Optional

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, Field

# These values go into the camera's MediaMTX source URL and stream description
# (services/camera_sync.py), so each one is held to safe characters; the card
# name is also percent-encoded there.


def _blank_to_none(value: object) -> object:
    return None if isinstance(value, str) and not value.strip() else value


def _multicast(value: IPv4Address) -> IPv4Address:
    if not value.is_multicast:
        raise ValueError("must be a multicast group, 224.0.0.0 to 239.255.255.255")
    return value


# The alias names the camera's recordings folder too, which Windows refuses
# for its device names, whatever the case
_WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{n}" for n in range(1, 10)), *(f"LPT{n}" for n in range(1, 10))}


def _not_reserved(value: str) -> str:
    if value.upper() in _WINDOWS_RESERVED:
        raise ValueError(f"'{value}' is a name Windows keeps for a device: choose another")
    return value


Alias = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{1,62}$"), AfterValidator(_not_reserved)]
# The group the camera multicasts to: a unicast address would leave the camera
# on No signal for good
MulticastGroup = Annotated[IPv4Address, AfterValidator(_multicast)]
# The network card to read the camera on, by its name. Windows friendly names
# can hold spaces and punctuation ("Ethernet 2", "Wi-Fi"); it is percent-encoded
# into the source URL, so the set here only keeps out control characters.
Iface = Annotated[Optional[Annotated[str, Field(pattern=r"^[A-Za-z0-9 ._:#()*-]{1,64}$")]], BeforeValidator(_blank_to_none)]

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
