"""MediaMTX (VideoService) on this PC: its Control API (v3)."""

import httpx

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


def list_path_configs() -> dict[str, dict]:
    """Every configured path by name, from mediamtx.yml and from the API alike."""
    items = _api("GET", "/config/paths/list", params={"itemsPerPage": 1000}).json()["items"]
    return {item["name"]: item for item in items}


def add_path(name: str, config: dict) -> None:
    _api("POST", f"/config/paths/add/{name}", json=config)


def patch_path(name: str, fields: dict) -> None:
    """Changes only these fields."""
    _api("PATCH", f"/config/paths/patch/{name}", json=fields)


def delete_path(name: str) -> None:
    _api("DELETE", f"/config/paths/delete/{name}")


def path_states() -> dict[str, dict]:
    """Every active path by name, with `ready` and its `inboundBytes` counter."""
    items = _api("GET", "/paths/list", params={"itemsPerPage": 1000}).json()["items"]
    return {item["name"]: item for item in items}
