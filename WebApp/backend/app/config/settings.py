from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = "postgresql://postgres:postgres@localhost:5432/pdb"
    app_title: str = "Kanat WebApp API"
    app_version: str = "1.0.0"


settings = Settings()
