from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, Float, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from jera_fx_api.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class FeatureSet(Base):
    __tablename__ = "feature_sets"
    __table_args__ = {"schema": "curated"}

    feature_set_key: Mapped[str] = mapped_column(String(160), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    definition_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    scale_policy: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class FeatureValue(Base):
    __tablename__ = "feature_values"
    __table_args__ = (
        UniqueConstraint(
            "feature_set_key",
            "feature_name",
            "series_key",
            "reference_month_end",
            name="uq_feature_values_set_feature_series_month",
        ),
        {"schema": "curated"},
    )

    feature_value_key: Mapped[str] = mapped_column(String(220), primary_key=True)
    feature_set_key: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    series_key: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    feature_name: Mapped[str] = mapped_column(String(120), nullable=False)
    reference_month_end: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    observation_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    value_numeric: Mapped[float] = mapped_column(Float, nullable=False)
    units: Mapped[str] = mapped_column(String(64), nullable=False)
    scale_policy: Mapped[str] = mapped_column(String(64), nullable=False)
    provenance_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ClientSnapshot(Base):
    __tablename__ = "client_snapshots"
    __table_args__ = (
        UniqueConstraint("snapshot_type", "reference_month_end", name="uq_client_snapshots_type_month"),
        {"schema": "curated"},
    )

    snapshot_key: Mapped[str] = mapped_column(String(180), primary_key=True)
    snapshot_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    reference_month_end: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    feature_set_key: Mapped[str] = mapped_column(String(160), nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

