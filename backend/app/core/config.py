from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    app_env: str = "development"
    frontend_dist_dir: Path = Path("/app/frontend_dist")

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

    # Canonical files use local storage during development and an
    # S3-compatible object store (for example Cloudflare R2) in production.
    storage_backend: str = "local"
    storage_cache_dir: Path = REPO_ROOT / "data" / "object_cache"
    storage_cache_max_bytes: int = 2 * 1024 * 1024 * 1024
    s3_bucket: str | None = None
    s3_prefix: str = "pitwall"
    s3_endpoint_url: str | None = None
    s3_region: str = "auto"
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None

    # FastF1's decoded session cache is disposable after every telemetry file
    # has been published and the session manifest has been verified.
    fastf1_cleanup_after_prepare: bool = True
    fastf1_use_requests_cache: bool = False
    persist_historical_events_in_database: bool = False

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        value = str(value)
        if value.startswith("postgres://"):
            value = "postgresql+asyncpg://" + value.removeprefix("postgres://")
        elif value.startswith("postgresql://"):
            value = "postgresql+asyncpg://" + value.removeprefix("postgresql://")
        value = value.replace("?sslmode=", "?ssl=").replace("&sslmode=", "&ssl=")
        return value

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
