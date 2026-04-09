from __future__ import annotations

from pathlib import Path
import tempfile

from sqlalchemy import MetaData, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

SCHEMA_NAMES = ("meta", "raw", "curated")
metadata_obj = MetaData(naming_convention=NAMING_CONVENTION)


class Base(DeclarativeBase):
    metadata = metadata_obj


def is_sqlite_url(url: str) -> bool:
    return url.startswith("sqlite")


def configure_sqlite_schemas(engine: Engine, schema_dir: Path | None = None) -> None:
    if engine.dialect.name != "sqlite":
        return

    root_dir = schema_dir or (Path(tempfile.gettempdir()) / "jera_fx" / "sqlite_schemas")
    root_dir.mkdir(parents=True, exist_ok=True)
    schema_paths = {
        schema_name: (root_dir / f"{schema_name}.db").resolve()
        for schema_name in SCHEMA_NAMES
    }

    @event.listens_for(engine, "connect")
    def _attach_sqlite_schemas(dbapi_connection, _connection_record) -> None:  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        current = {row[1] for row in cursor.execute("PRAGMA database_list").fetchall()}
        for schema_name, schema_path in schema_paths.items():
            if schema_name in current:
                continue
            escaped = str(schema_path).replace("'", "''")
            cursor.execute(f"ATTACH DATABASE '{escaped}' AS {schema_name}")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
