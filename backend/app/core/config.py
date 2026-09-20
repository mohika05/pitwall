from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    app_env: str = "development"

    database_url: str = (
        "postgresql+asyncpg://pitwall:pitwall@localhost:5433/pitwall"
    )

    redis_url: str = (
        "redis://localhost:6379/0"
    )

    frontend_origin: str = (
        "http://localhost:5173"
    )

    openf1_base_url: str = "https://api.openf1.org/v1"
    openf1_timeout_seconds: float = 60.0
    openf1_min_request_interval_seconds: float = 0.40
    openf1_max_retries: int = 4
    openf1_access_token: str | None = None

    # ---------------------------------------------------------
    # DATA DIRECTORIES
    # ---------------------------------------------------------

    data_dir: Path = (
        REPO_ROOT
        / "data"
    )

    fastf1_cache_dir: Path = (
        REPO_ROOT
        / "data"
        / "fastf1_cache"
    )

    telemetry_dir: Path = (
        REPO_ROOT
        / "data"
        / "telemetry"
    )

    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()