from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, Float, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from jera_fx_api.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SourceFile(Base):
    __tablename__ = "source_files"
    __table_args__ = (
        UniqueConstraint("source_key", "checksum_sha256", name="uq_source_files_source_checksum"),
        {"schema": "raw"},
    )

    source_file_key: Mapped[str] = mapped_column(String(160), primary_key=True)
    source_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    ingestion_run_key: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    logical_name: Mapped[str] = mapped_column(String(255), nullable=False)
    original_path: Mapped[str] = mapped_column(Text, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    update_header: Mapped[str | None] = mapped_column(String(255), nullable=True)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class Observation(Base):
    __tablename__ = "observations"
    __table_args__ = (
        UniqueConstraint("series_key", "observation_date", "scale_policy", name="uq_observations_series_date_scale"),
        {"schema": "raw"},
    )

    observation_key: Mapped[str] = mapped_column(String(200), primary_key=True)
    source_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    series_key: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    ingestion_run_key: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    source_file_key: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    observation_date: Mapped[date] = mapped_column(Date, nullable=False)
    reference_month_end: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    vintage_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    value_numeric: Mapped[float] = mapped_column(Float, nullable=False)
    units: Mapped[str] = mapped_column(String(64), nullable=False)
    scale_policy: Mapped[str] = mapped_column(String(64), nullable=False)
    attributes_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

