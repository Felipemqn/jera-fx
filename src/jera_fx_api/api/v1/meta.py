from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from jera_fx_api.db.session import get_db_session
from jera_fx_api.schemas.meta import LastUpdatedResponse
from jera_fx_features.client_overview import get_latest_client_overview_snapshot

router = APIRouter(prefix="/v1/meta", tags=["meta"])


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

