from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = Field(default="development", alias="APP_ENV")
    database_url: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/jera_fx",
        alias="DATABASE_URL",
    )
    series_catalog_path: Path = Field(
        default=Path("config/series_catalog.yml"),
        alias="SERIES_CATALOG_PATH",
    )
    reer_workbook_path: Path = Field(
        default=Path("data/raw/reer/REER_database_ver11Mar2026.xlsx"),
        alias="REER_WORKBOOK_PATH",
    )
    cds_brazil_5y_file_path: Path = Field(
        default=Path("data/raw/cds/BRGV5YUSAC=R_2026-04-07.csv"),
        alias="CDS_BRAZIL_5Y_FILE_PATH",
    )
    sqlite_schema_dir: Path | None = Field(default=None, alias="SQLITE_SCHEMA_DIR")
    api_host: str = Field(default="127.0.0.1", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
