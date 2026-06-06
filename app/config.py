from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_path: Path = Path("data/tiangou.sqlite3")
    overpass_url: str = "https://overpass-api.de/api/interpreter"
    overpass_timeout_seconds: float = 130.0

    model_config = SettingsConfigDict(env_prefix="TIANGOU_")


settings = Settings()
