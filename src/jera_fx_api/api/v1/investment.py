"""Investment mode API endpoints.

Internal-use endpoints for the investment team workspace.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from jera_fx_api.db.session import get_db_session
from jera_fx_features.investment_builder import (
    get_latest_driver_variations_snapshot,
    get_latest_rolling_regression_snapshot,
)

router = APIRouter(prefix="/v1/investment", tags=["investment"])


@router.get("/rolling-regression")
def get_rolling_regression(session: Session = Depends(get_db_session)):
    snapshot = get_latest_rolling_regression_snapshot(session)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Rolling regression snapshot not found")
    return snapshot.payload_json


@router.get("/driver-variations")
def get_driver_variations(session: Session = Depends(get_db_session)):
    snapshot = get_latest_driver_variations_snapshot(session)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Driver variations snapshot not found")
    return snapshot.payload_json
