from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from jera_fx_api.db.session import get_db_session
from jera_fx_api.schemas.meta import HealthResponse, LastUpdatedResponse
from jera_fx_features.client_overview import get_latest_client_overview_snapshot

router = APIRouter(prefix="/v1/meta", tags=["meta"])

API_VERSION = "1.0.1"


@router.get("/health", response_model=HealthResponse)
def get_health(session: Session = Depends(get_db_session)) -> HealthResponse:
    """Liveness + DB ping. Used by load balancers and monitoring."""
    db_status = "ok"
    try:
        session.execute(text("SELECT 1"))
    except Exception as exc:
        db_status = f"error: {exc.__class__.__name__}"

    overall = "ok" if db_status == "ok" else "degraded"
    return HealthResponse(
        status=overall,
        version=API_VERSION,
        db=db_status,
        timestamp=datetime.now(timezone.utc),
    )


@router.get("/last-updated", response_model=LastUpdatedResponse)
def get_last_updated(session: Session = Depends(get_db_session)) -> LastUpdatedResponse:
    snapshot = get_latest_client_overview_snapshot(session)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Client overview snapshot not found")
    payload = snapshot.payload_json
    return LastUpdatedResponse.model_validate(
        {
            "snapshot_type": payload["snapshot_type"],
            "reference_month_end": payload["reference_month_end"],
            "snapshot_created_at": payload["last_updated"]["snapshot_created_at"],
            "latest_reer_reference_month_end": payload["last_updated"]["latest_reer_reference_month_end"],
            "latest_ptax_observation_date": payload["last_updated"]["latest_ptax_observation_date"],
            "sources": payload["last_updated"]["sources"],
        }
    )

