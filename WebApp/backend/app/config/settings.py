from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = "postgresql://postgres:postgres@localhost:5432/pdb"
    app_title: str = "Kanat WebApp API"
    app_version: str = "1.0.0"

    # MediaMTX (VideoService) on this PC: its Control API, through which the
    # cameras are configured and recording is switched, and its playback server
    mediamtx_api_url: str = "http://127.0.0.1:9997"
    mediamtx_playback_url: str = "http://127.0.0.1:9996"
    # How often the cameras are re-applied to MediaMTX, which forgets them when
    # it restarts; 0 turns the sync loop off (tests)
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


settings = Settings()
