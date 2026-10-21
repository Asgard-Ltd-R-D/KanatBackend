"""MediaMTX (VideoService) on this PC: its Control API (v3) and playback server."""
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import httpx
import yaml

from app.config.settings import settings

TIMEOUT_S = 3


class MediaMTXUnreachable(Exception):
    """MediaMTX did not answer, or answered with an error."""


def _api(method: str, path: str, **kwargs) -> httpx.Response:
    try:
        res = httpx.request(method, f"{settings.mediamtx_api_url}/v3{path}", timeout=TIMEOUT_S, **kwargs)
    except httpx.HTTPError as e:
        raise MediaMTXUnreachable(f"{method} {path}: {e}") from e
    if res.is_error:
        raise MediaMTXUnreachable(f"{method} {path}: HTTP {res.status_code} {res.text[:200]}")
    return res


@dataclass(frozen=True)
class ConfigPaths:
    """The paths mediamtx.yml defines: MediaMTX's own, which the WebApp must
    never patch, delete or take the name of, whatever their settings. A key is
    a name (loopdemo), a regular expression after "~" (~^external[0-9]+$) that
    applies to every name it matches, or all_others (formerly all), which
    applies to every name nothing else defines."""
    names: frozenset[str] = frozenset()
    patterns: tuple[re.Pattern, ...] = ()
    catch_all: bool = False

    def defines(self, name: str) -> bool:
        """Whether a name or a regular expression defines this path. The catch-all
        does not count: adding a camera's own path is what takes a name out of it."""
        return name in self.names or any(p.search(name) for p in self.patterns)


def config_paths() -> ConfigPaths | None:
    """The paths mediamtx.yml defines. None when the file cannot be read, or
    holds a regular expression Python reads differently from MediaMTX (Go),
    so callers can stay on the safe side."""
    if settings.mediamtx_config:
        path = Path(settings.mediamtx_config)
    else:
        parents = Path(__file__).resolve().parents
        # app/services/mediamtx.py -> KanatBackend/
        if len(parents) <= 4:
            return None
        path = parents[4] / "VideoService" / "mediamtx.yml"
    try:
        config = yaml.safe_load(path.read_text())
    except (OSError, yaml.YAMLError):
        return None
    paths = config.get("paths") if isinstance(config, dict) else None
    if not isinstance(paths, dict):
        return ConfigPaths()
    names, patterns, catch_all = set(), [], False
    for key in map(str, paths):
        if key.startswith("~"):
            try:
                patterns.append(re.compile(key[1:]))  # unanchored, as Go's MatchString
            except re.error:
                return None
        elif key in ("all_others", "all"):
            catch_all = True
        else:
            names.add(key)
    return ConfigPaths(frozenset(names), tuple(patterns), catch_all)


def list_path_configs() -> dict[str, dict]:
    """Every configured path by name, from mediamtx.yml and from the API alike."""
    items = _api("GET", "/config/paths/list", params={"itemsPerPage": 1000}).json()["items"]
    return {item["name"]: item for item in items}


def add_path(name: str, config: dict) -> None:
    _api("POST", f"/config/paths/add/{name}", json=config)


def patch_path(name: str, fields: dict) -> None:
    """Changes only these fields. Changing `record` alone does not restart the
    path's runOnInit command (checked on v1.21.2), so the stream keeps going."""
    _api("PATCH", f"/config/paths/patch/{name}", json=fields)


def delete_path(name: str) -> None:
    _api("DELETE", f"/config/paths/delete/{name}")


def path_states() -> dict[str, dict]:
    """Every active path by name, with `ready` and its `inboundBytes` counter."""
    items = _api("GET", "/paths/list", params={"itemsPerPage": 1000}).json()["items"]
    return {item["name"]: item for item in items}


def list_recordings(path: str, start: datetime, end: datetime) -> list[dict]:
    """The recorded spans of `path` between `start` and `end`, as
    [{"start": RFC 3339, "duration": seconds}]. None recorded is an empty list."""
    try:
        res = httpx.get(
            f"{settings.mediamtx_playback_url}/list",
            params={"path": path, "start": start.isoformat(), "end": end.isoformat()},
            timeout=TIMEOUT_S,
        )
    except httpx.HTTPError as e:
        raise MediaMTXUnreachable(f"playback list {path}: {e}") from e
    # 404: nothing recorded in that window; 400: the path is not configured
    if res.status_code in (400, 404):
        return []
    if res.is_error:
        raise MediaMTXUnreachable(f"playback list {path}: HTTP {res.status_code} {res.text[:200]}")
    return res.json()


# Shared by the replay downloads. A part is generated as it is read, so reads
# may pause, but a playback server silent this long has stalled.
PLAYBACK_READ_TIMEOUT_S = 30
_playback = httpx.Client(timeout=httpx.Timeout(TIMEOUT_S, read=PLAYBACK_READ_TIMEOUT_S))


def open_recording(path: str, start: datetime, duration_s: float) -> httpx.Response:
    """A recorded span as one MP4, opened as a stream. The caller iterates and
    closes it."""
    request = _playback.build_request(
        "GET",
        f"{settings.mediamtx_playback_url}/get",
        params={"path": path, "start": start.isoformat(), "duration": duration_s, "format": "mp4"},
    )
    try:
        res = _playback.send(request, stream=True)
    except httpx.HTTPError as e:
        raise MediaMTXUnreachable(f"playback get {path}: {e}") from e
    if res.is_error:
        res.close()
        raise MediaMTXUnreachable(f"playback get {path}: HTTP {res.status_code}")
    return res
