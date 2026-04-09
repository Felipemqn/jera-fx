from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from jera_fx_api.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Source(Base):
    __tablename__ = "sources"
    __table_args__ = {"schema": "meta"}

    source_key: Mapped[str] = mapped_column(String(100), primary_key=True)
    provider: Mapped[str] = mapped_column(String(255), nullable=False)
    base_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    official: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    release_metadata_behavior: Mapped[str] = mapped_column(String(255), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    connection: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class SeriesDefinition(Base):
    __tablename__ = "series_definitions"
    __table_args__ = (
        UniqueConstraint("source_key", "source_code", name="uq_series_definitions_source_code"),
        {"schema": "meta"},
    )

    series_key: Mapped[str] = mapped_column(String(120), primary_key=True)
    source_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    source_code: Mapped[str] = mapped_column(String(255), nullable=False)
    provider: Mapped[str] = mapped_column(String(255), nullable=False)
    frequency: Mapped[str] = mapped_column(String(32), nullable=False)
    units: Mapped[str] = mapped_column(String(64), nullable=False)
    release_metadata_behavior: Mapped[str] = mapped_column(String(255), nullable=False)
    transformation_rules: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    display_metadata: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    canonical_scale_policy: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    is_placeholder: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_ingestion_runs_idempotency_key"),
        {"schema": "meta"},
    )

    ingestion_run_key: Mapped[str] = mapped_column(String(160), primary_key=True)
    source_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    job_name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    parameters_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

