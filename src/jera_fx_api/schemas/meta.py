from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel

from jera_fx_api.schemas.client_overview import SourceFreshness


class LastUpdatedResponse(BaseModel):
    snapshot_type: str
    reference_month_end: date
    snapshot_created_at: datetime
    latest_reer_reference_month_end: date
    latest_ptax_observation_date: date
    sources: list[SourceFreshness]


class HealthResponse(BaseModel):
    status: str  # "ok" | "degraded" | "down"
    version: str
    db: str  # "ok" | "error: <msg>"
    timestamp: datetime

