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
    # cameras are configured
    mediamtx_api_url: str = "http://127.0.0.1:9997"
    # MediaMTX's RTSP server, on which each camera is a path named after its
    # alias: the Stream a Session's Run watches
    mediamtx_rtsp_url: str = "rtsp://127.0.0.1:8554"
    # The Detection Service's control API on this PC (ADR-0008), its --port
    detection_service_url: str = "http://127.0.0.1:8010"
    # How often the cameras are re-applied to MediaMTX, which forgets them when
    # it restarts, and the Detection Service's Run reconciled with the Session
    # to watch; 0 turns both loops off (tests)
    camera_sync_interval_s: float = 5
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
