from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from jera_fx_api.db.session import get_db_session
from jera_fx_api.schemas.client_overview import (
    ClientOverviewResponse,
    PtaxHistoryResponse,
    ReerBandsResponse,
    ScenarioSetResponse,
    SourceFreshnessResponse,
    TacticalDriverFreshnessResponse,
    TacticalDriversResponse,
    TacticalSignalResponse,
    TacticalSignalInputsResponse,
    TacticalSignalReadinessResponse,
)
from jera_fx_features.client_overview import get_latest_client_overview_snapshot
from jera_fx_features.reer_bands import get_latest_reer_bands_snapshot
from jera_fx_features.source_freshness import (
    get_latest_ptax_monthly_history_snapshot,
    get_latest_source_freshness_snapshot,
)
from jera_fx_features.tactical_drivers import (
    get_latest_tactical_driver_freshness_snapshot,
    get_latest_tactical_driver_history_snapshot,
    get_latest_tactical_driver_latest_snapshot,
)
from jera_fx_features.scenario_builder import get_latest_scenario_set_snapshot
from jera_fx_features.tactical_signal import (
    get_latest_tactical_signal_snapshot,
    get_latest_tactical_signal_inputs_snapshot,
    get_latest_tactical_signal_readiness_snapshot,
)

router = APIRouter(prefix="/v1/client", tags=["client"])


@router.get("/overview", response_model=ClientOverviewResponse)
def get_client_overview(session: Session = Depends(get_db_session)) -> ClientOverviewResponse:
    snapshot = get_latest_client_overview_snapshot(session)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Client overview snapshot not found")
    return ClientOverviewResponse.model_validate(snapshot.payload_json)


@router.get("/reer-bands", response_model=ReerBandsResponse)
def get_client_reer_bands(session: Session = Depends(get_db_session)) -> ReerBandsResponse:
    snapshot = get_latest_reer_bands_snapshot(session)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="REER bands snapshot not found")
    return ReerBandsResponse.model_validate(snapshot.payload_json)


@router.get("/source-freshness", response_model=SourceFreshnessResponse)
def get_client_source_freshness(session: Session = Depends(get_db_session)) -> SourceFreshnessResponse:
    snapshot = get_latest_source_freshness_snapshot(session)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Source freshness snapshot not found")
    return SourceFreshnessResponse.model_validate(snapshot.payload_json)


@router.get("/ptax-history", response_model=PtaxHistoryResponse)
def get_client_ptax_history(session: Session = Depends(get_db_session)) -> PtaxHistoryResponse:
    snapshot = get_latest_ptax_monthly_history_snapshot(session)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="PTAX monthly history snapshot not found")
    return PtaxHistoryResponse.model_validate(snapshot.payload_json)


@router.get("/tactical-inputs", response_model=TacticalSignalInputsResponse)
def get_client_tactical_inputs(session: Session = Depends(get_db_session)) -> TacticalSignalInputsResponse:
    snapshot = get_latest_tactical_signal_inputs_snapshot(session)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Tactical signal inputs snapshot not found")
    return TacticalSignalInputsResponse.model_validate(snapshot.payload_json)


@router.get("/tactical-signal-readiness", response_model=TacticalSignalReadinessResponse)
def get_client_tactical_signal_readiness(session: Session = Depends(get_db_session)) -> TacticalSignalReadinessResponse:
    snapshot = get_latest_tactical_signal_readiness_snapshot(session)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Tactical signal readiness snapshot not found")
    return TacticalSignalReadinessResponse.model_validate(snapshot.payload_json)


@router.get("/tactical-drivers", response_model=TacticalDriversResponse)
def get_client_tactical_drivers(session: Session = Depends(get_db_session)) -> TacticalDriversResponse:
    latest_snapshot = get_latest_tactical_driver_latest_snapshot(session)
    history_snapshot = get_latest_tactical_driver_history_snapshot(session)
    readiness_snapshot = get_latest_tactical_signal_readiness_snapshot(session)
    if latest_snapshot is None or history_snapshot is None or readiness_snapshot is None:
        raise HTTPException(status_code=404, detail="Tactical driver snapshots not found")

    history_map = {item["driver_key"]: item for item in history_snapshot.payload_json["drivers"]}
    drivers = []
    for latest_driver in latest_snapshot.payload_json["drivers"]:
        merged = dict(latest_driver)
        history_driver = history_map.get(latest_driver["driver_key"], {})
        merged["history_scale_policy"] = history_driver.get("history_scale_policy")
        merged["points"] = history_driver.get("points", [])
        drivers.append(merged)

    payload = {
        "snapshot_type": "tactical_drivers",
        "reference_month_end": latest_snapshot.payload_json["reference_month_end"],
        "latest_snapshot_created_at": latest_snapshot.payload_json["snapshot_created_at"],
        "history_snapshot_created_at": history_snapshot.payload_json["snapshot_created_at"],
        "signal_computable": readiness_snapshot.payload_json["signal_computable"],
        "missing_driver_keys": readiness_snapshot.payload_json["missing_driver_keys"],
        "drivers": drivers,
    }
    return TacticalDriversResponse.model_validate(payload)


@router.get("/tactical-driver-freshness", response_model=TacticalDriverFreshnessResponse)
def get_client_tactical_driver_freshness(session: Session = Depends(get_db_session)) -> TacticalDriverFreshnessResponse:
    snapshot = get_latest_tactical_driver_freshness_snapshot(session)
    readiness_snapshot = get_latest_tactical_signal_readiness_snapshot(session)
    if snapshot is None or readiness_snapshot is None:
        raise HTTPException(status_code=404, detail="Tactical driver freshness snapshot not found")
    payload = {
        **snapshot.payload_json,
        "signal_computable": readiness_snapshot.payload_json["signal_computable"],
        "missing_driver_keys": readiness_snapshot.payload_json["missing_driver_keys"],
    }
    return TacticalDriverFreshnessResponse.model_validate(payload)


@router.get("/tactical-signal", response_model=TacticalSignalResponse)
def get_client_tactical_signal(session: Session = Depends(get_db_session)) -> TacticalSignalResponse:
    snapshot = get_latest_tactical_signal_snapshot(session)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Tactical signal snapshot not found")
    return TacticalSignalResponse.model_validate(snapshot.payload_json)


@router.get("/scenarios", response_model=ScenarioSetResponse)
def get_client_scenarios(session: Session = Depends(get_db_session)) -> ScenarioSetResponse:
    snapshot = get_latest_scenario_set_snapshot(session)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Scenario set snapshot not found")
    return ScenarioSetResponse.model_validate(snapshot.payload_json)
