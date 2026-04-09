from __future__ import annotations

from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from jera_fx_api.config import Settings
from jera_fx_api.db.base import configure_sqlite_schemas


def build_engine(settings: Settings, sqlite_schema_dir: Path | None = None) -> Engine:
    engine = create_engine(settings.database_url, future=True)
    configure_sqlite_schemas(engine, sqlite_schema_dir or settings.sqlite_schema_dir)
    return engine


def build_session_factory(
    settings: Settings,
    sqlite_schema_dir: Path | None = None,
) -> sessionmaker[Session]:
    engine = build_engine(settings, sqlite_schema_dir=sqlite_schema_dir)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db_session() -> Iterator[Session]:
    from jera_fx_api.config import get_settings

    session_factory = build_session_factory(get_settings())
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
