import sys
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # SQLite on disk: one local single-user app, so a file database is enough
    # (core/database.py sets its pragmas). A relative path is beside where the
    # backend runs; the container overrides it to a path on a mounted volume so
    # the database survives a rebuild (docker-compose.yml).
    database_url: str = "sqlite:///./kanat.db"
    app_title: str = "Kanat WebApp API"
    app_version: str = "1.0.0"

    # MediaMTX (VideoService) on this PC: its Control API, through which the
    # cameras are configured and recording is switched, and its playback server
    mediamtx_api_url: str = "http://127.0.0.1:9997"
    mediamtx_playback_url: str = "http://127.0.0.1:9996"
    # MediaMTX's RTSP server, on which each camera is a path named after its
    # alias: the Stream a Session's Run watches
    mediamtx_rtsp_url: str = "rtsp://127.0.0.1:8554"
    # Legacy: the OS whose GStreamer recorder (run_record.sh/.ps1) MediaMTX once
    # launched per camera. MediaMTX now reads each camera's RTP directly
    # (services/camera_sync.py), so nothing reads this; kept until the Windows
    # bundle's env/compose plumbing is cleaned up with it.
    record_launcher: Literal["bash", "powershell"] = "powershell" if sys.platform == "win32" else "bash"
    # The Detection Service's control API on this PC (ADR-0008), its --port
    detection_service_url: str = "http://127.0.0.1:8010"
    # How often the cameras are re-applied to MediaMTX, which forgets them when
    # it restarts, and the Detection Service's Run reconciled with the Session
    # to watch; 0 turns both loops off (tests)
    camera_sync_interval_s: float = 5
    # Where replayed recordings are kept as files, so the player can seek in
    # them; empty means VideoService/replay-cache beside the recordings
    replay_cache_dir: str = ""
    # The most the replay cache may hold; the least recently played go first
    replay_cache_max_gb: float = 20
    # Where MediaMTX writes the recordings (its recordPath, relative to
    # VideoService/), so a deleted Session's video is deleted with it; empty
    # means this repo's VideoService/recordings
    recordings_dir: str = ""
    # MediaMTX's config file, whose paths the backend never changes or deletes;
    # empty means this repo's VideoService/mediamtx.yml
    mediamtx_config: str = ""

    # Logs (core/logs.py): the lowest level written, and the folder of
    # backend.log, shared with the app's frontend.log, which the app's Logs tab
    # reads; empty means WebApp/logs. On the range PC, /var/log/kanat in the
    # backend's container
    log_level: str = "INFO"
    log_dir: str = ""


settings = Settings()
