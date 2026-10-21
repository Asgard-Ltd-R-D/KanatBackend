from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = "postgresql://postgres:postgres@localhost:5432/pdb"
    app_title: str = "Kanat WebApp API"
    app_version: str = "1.0.0"

    # MediaMTX (VideoService) on this PC: its Control API, through which the
    # cameras are configured
    mediamtx_api_url: str = "http://127.0.0.1:9997"
    # How often the cameras are re-applied to MediaMTX, which forgets them when
    # it restarts; 0 turns the sync loop off (tests)
    camera_sync_interval_s: float = 5


settings = Settings()
