from __future__ import annotations

from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from jera_fx_api.db.models import ClientSnapshot, FeatureValue, Observation
from jera_fx_api.services import stable_hash, upsert_client_snapshot, upsert_feature_set, utcnow
from jera_fx_connectors.bcb_ptax import PTAX_MONTHLY_FEATURE_SET_KEY
from jera_fx_features.reer_bands import canonical_history
from jera_fx_features.reer_normalization import CANONICAL_SCALE_POLICY
from jera_fx_features.tactical_signal import (
    _driver_status_rows,
    _latest_observation,
    _latest_reer_payload,
    _ptax_monthly_close_payload,
    _series_point_payload,
)
from jera_fx_registry.series_catalog import SeriesCatalog

TACTICAL_DRIVER_HISTORY_FEATURE_SET_KEY = "tactical_driver_history_snapshot_v1"
TACTICAL_DRIVER_LATEST_FEATURE_SET_KEY = "tactical_driver_latest_snapshot_v1"
TACTICAL_DRIVER_FRESHNESS_FEATURE_SET_KEY = "tactical_driver_freshness_snapshot_v1"


def _series_monthly_points(session: Session, catalog: SeriesCatalog, series_key: str) -> tuple[list[dict[str, Any]], str]:
    if series_key in {"reer_120_br", "reer_51_br"}:
        series_definition = catalog.get_series(series_key)
        frame = canonical_history(session, series_key)
        points = [
            {
                "reference_month_end": row.reference_month_end.isoformat(),
                "observation_date": row.reference_month_end.isoformat(),
                "value": float(row.value_numeric),
                "units": series_definition.units,
                "scale_policy": CANONICAL_SCALE_POLICY,
            }
            for row in frame.itertuples(index=False)
        ]
        return points, CANONICAL_SCALE_POLICY

    if series_key in {"ptax_usd_brl_buy", "ptax_usd_brl_sell"}:
        statement = (
            select(FeatureValue)
            .where(
                FeatureValue.feature_set_key == PTAX_MONTHLY_FEATURE_SET_KEY,
                FeatureValue.series_key == series_key,
                FeatureValue.feature_name == "monthly_close",
            )
            .order_by(FeatureValue.reference_month_end.asc())
        )
        rows = session.execute(statement).scalars().all()
        if not rows:
            return [], "source-native"
        return (
            [
                {
                    "reference_month_end": row.reference_month_end.isoformat(),
                    "observation_date": row.observation_date.isoformat() if row.observation_date else None,
                    "value": row.value_numeric,
                    "units": row.units,
                    "scale_policy": row.scale_policy,
                }
                for row in rows
            ],
            rows[-1].scale_policy,
        )

    statement = (
        select(Observation)
        .where(Observation.series_key == series_key)
        .order_by(Observation.observation_date.asc())
    )
    rows = session.execute(statement).scalars().all()
    if not rows:
        return [], "source-native"
    frame = pd.DataFrame(
        {
            "observation_date": [row.observation_date for row in rows],
            "reference_month_end": [row.reference_month_end for row in rows],
            "value_numeric": [row.value_numeric for row in rows],
            "units": [row.units for row in rows],
            "scale_policy": [row.scale_policy for row in rows],
        }
    )
    grouped = frame.groupby("reference_month_end", as_index=False).tail(1)
    points = [
        {
            "reference_month_end": row.reference_month_end.isoformat(),
            "observation_date": row.observation_date.isoformat(),
            "value": float(row.value_numeric),
            "units": row.units,
            "scale_policy": row.scale_policy,
        }
        for row in grouped.itertuples(index=False)
    ]
    return points, str(grouped.iloc[-1]["scale_policy"])


def build_tactical_driver_history_snapshot(session: Session, catalog: SeriesCatalog) -> dict[str, Any]:
    feature_set = upsert_feature_set(
        session,
        feature_set_key=TACTICAL_DRIVER_HISTORY_FEATURE_SET_KEY,
        name="Tactical driver history snapshot",
        version="v1",
        description="Database-backed monthly history for tactical drivers using month-end aligned curated points.",
        scale_policy="mixed",
        definition_hash=stable_hash({"feature_set_key": TACTICAL_DRIVER_HISTORY_FEATURE_SET_KEY}),
    )
    available_rows, missing_rows = _driver_status_rows(session, catalog)
    status_map = {row["driver_key"]: row for row in [*available_rows, *missing_rows]}
    drivers: list[dict[str, Any]] = []
    latest_reference_month_end = None
    for requirement in catalog.tactical_signal.required_drivers:
        status = status_map[requirement.driver_key]
        if status["status"] == "missing" or requirement.series_key is None:
            drivers.append(
                {
                    "driver_key": requirement.driver_key,
                    "label": requirement.label,
                    "category": requirement.category,
                    "status": "missing",
                    "required_for_signal": requirement.required_for_signal,
                    "series_key": requirement.series_key,
                    "source_key": status["source_key"],
                    "provider": status["provider"],
                    "source_type": status["source_type"],
                    "source_mode": status["source_mode"],
                    "automation_mode": status["automation_mode"],
                    "production_ingestion_approved": status["production_ingestion_approved"],
                    "configured_for_runtime": status["configured_for_runtime"],
                    "required_configuration": status["required_configuration"],
                    "history_scale_policy": None,
                    "points": [],
                    "reason": status["reason"],
                    "notes": status["notes"],
                }
            )
            continue

        points, history_scale_policy = _series_monthly_points(session, catalog, requirement.series_key)
        if points:
            latest_reference_month_end = max(
                pd.to_datetime(points[-1]["reference_month_end"]).date(),
                latest_reference_month_end or pd.to_datetime(points[-1]["reference_month_end"]).date(),
            )
        drivers.append(
            {
                "driver_key": requirement.driver_key,
                "label": requirement.label,
                "category": requirement.category,
                "status": "available",
                "required_for_signal": requirement.required_for_signal,
                "series_key": requirement.series_key,
                "source_key": status["source_key"],
                "provider": status["provider"],
                "source_type": status["source_type"],
                "source_mode": status["source_mode"],
                "automation_mode": status["automation_mode"],
                "production_ingestion_approved": status["production_ingestion_approved"],
                "configured_for_runtime": status["configured_for_runtime"],
                "required_configuration": status["required_configuration"],
                "history_scale_policy": history_scale_policy,
                "points": points,
                "reason": None,
                "notes": status["notes"],
            }
        )

    if latest_reference_month_end is None:
        raise ValueError("No tactical driver history available")
    payload = {
        "snapshot_type": "tactical_driver_history",
        "reference_month_end": latest_reference_month_end.isoformat(),
        "snapshot_created_at": utcnow().isoformat(),
        "drivers": drivers,
    }
    upsert_client_snapshot(
        session,
        snapshot_type="tactical_driver_history",
        reference_month_end=latest_reference_month_end,
        feature_set_key=feature_set.feature_set_key,
        payload_json=payload,
    )
    session.commit()
    return payload


def build_tactical_driver_latest_snapshot(session: Session, catalog: SeriesCatalog) -> dict[str, Any]:
    feature_set = upsert_feature_set(
        session,
        feature_set_key=TACTICAL_DRIVER_LATEST_FEATURE_SET_KEY,
        name="Tactical driver latest snapshot",
        version="v1",
        description="Latest available tactical driver values and audit metadata.",
        scale_policy="mixed",
        definition_hash=stable_hash({"feature_set_key": TACTICAL_DRIVER_LATEST_FEATURE_SET_KEY}),
    )
    available_rows, missing_rows = _driver_status_rows(session, catalog)
    status_map = {row["driver_key"]: row for row in [*available_rows, *missing_rows]}
    drivers: list[dict[str, Any]] = []
    latest_reference_month_end = None

    for requirement in catalog.tactical_signal.required_drivers:
        status = status_map[requirement.driver_key]
        if status["status"] == "missing" or requirement.series_key is None:
            drivers.append(
                {
                    "driver_key": requirement.driver_key,
                    "label": requirement.label,
                    "category": requirement.category,
                    "status": "missing",
                    "required_for_signal": requirement.required_for_signal,
                    "series_key": requirement.series_key,
                    "source_key": status["source_key"],
                    "provider": status["provider"],
                    "source_type": status["source_type"],
                    "source_mode": status["source_mode"],
                    "automation_mode": status["automation_mode"],
                    "production_ingestion_approved": status["production_ingestion_approved"],
                    "configured_for_runtime": status["configured_for_runtime"],
                    "required_configuration": status["required_configuration"],
                    "latest": None,
                    "latest_monthly_close": None,
                    "latest_native": None,
                    "latest_canonical": None,
                    "normalization_factor": None,
                    "reason": status["reason"],
                    "notes": status["notes"],
                }
            )
            continue

        observation = _latest_observation(session, requirement.series_key)
        if observation is None:
            continue
        latest_reference_month_end = max(
            observation.reference_month_end,
            latest_reference_month_end or observation.reference_month_end,
        )

        if requirement.series_key in {"reer_120_br", "reer_51_br"}:
            reer_payload = _latest_reer_payload(session, catalog, requirement.series_key)
            drivers.append(
                {
                    "driver_key": requirement.driver_key,
                    "label": requirement.label,
                    "category": requirement.category,
                    "status": "available",
                    "required_for_signal": requirement.required_for_signal,
                    "series_key": requirement.series_key,
                    "source_key": reer_payload["source_key"],
                    "provider": status["provider"],
                    "source_type": status["source_type"],
                    "source_mode": status["source_mode"],
                    "automation_mode": status["automation_mode"],
                    "production_ingestion_approved": status["production_ingestion_approved"],
                    "configured_for_runtime": status["configured_for_runtime"],
                    "required_configuration": status["required_configuration"],
                    "latest": None,
                    "latest_monthly_close": None,
                    "latest_native": reer_payload["native"],
                    "latest_canonical": reer_payload["canonical"],
                    "normalization_factor": reer_payload["normalization_factor"],
                    "latest_observation_date": reer_payload["observation_date"],
                    "latest_reference_month_end": reer_payload["reference_month_end"],
                    "reason": None,
                    "notes": status["notes"],
                }
            )
            continue

        latest_payload = _series_point_payload(observation, catalog.get_series(requirement.series_key))
        latest_monthly_close = None
        if requirement.series_key == "ptax_usd_brl_sell":
            latest_monthly_close = _ptax_monthly_close_payload(session, catalog, requirement.series_key)

        drivers.append(
            {
                "driver_key": requirement.driver_key,
                "label": requirement.label,
                "category": requirement.category,
                "status": "available",
                "required_for_signal": requirement.required_for_signal,
                "series_key": requirement.series_key,
                "source_key": latest_payload["source_key"],
                "provider": status["provider"],
                "source_type": status["source_type"],
                "source_mode": status["source_mode"],
                "automation_mode": status["automation_mode"],
                "production_ingestion_approved": status["production_ingestion_approved"],
                "configured_for_runtime": status["configured_for_runtime"],
                "required_configuration": status["required_configuration"],
                "latest": latest_payload,
                "latest_monthly_close": latest_monthly_close,
                "latest_native": None,
                "latest_canonical": None,
                "normalization_factor": None,
                "latest_observation_date": latest_payload["observation_date"],
                "latest_reference_month_end": latest_payload["reference_month_end"],
                "reason": None,
                "notes": status["notes"],
            }
        )

    if latest_reference_month_end is None:
        raise ValueError("No tactical driver latest values available")
    payload = {
        "snapshot_type": "tactical_driver_latest",
        "reference_month_end": latest_reference_month_end.isoformat(),
        "snapshot_created_at": utcnow().isoformat(),
        "drivers": drivers,
    }
    upsert_client_snapshot(
        session,
        snapshot_type="tactical_driver_latest",
        reference_month_end=latest_reference_month_end,
        feature_set_key=feature_set.feature_set_key,
        payload_json=payload,
    )
    session.commit()
    return payload


def build_tactical_driver_freshness_snapshot(session: Session, catalog: SeriesCatalog) -> dict[str, Any]:
    feature_set = upsert_feature_set(
        session,
        feature_set_key=TACTICAL_DRIVER_FRESHNESS_FEATURE_SET_KEY,
        name="Tactical driver freshness snapshot",
        version="v1",
        description="Latest freshness metadata for tactical drivers.",
        scale_policy="status-only",
        definition_hash=stable_hash({"feature_set_key": TACTICAL_DRIVER_FRESHNESS_FEATURE_SET_KEY}),
    )
    available_rows, missing_rows = _driver_status_rows(session, catalog)
    status_map = {row["driver_key"]: row for row in [*available_rows, *missing_rows]}
    drivers: list[dict[str, Any]] = []
    latest_reference_month_end = None
    for requirement in catalog.tactical_signal.required_drivers:
        status = status_map[requirement.driver_key]
        if status["status"] == "missing" or requirement.series_key is None:
            drivers.append(
                {
                    "driver_key": requirement.driver_key,
                    "label": requirement.label,
                    "category": requirement.category,
                    "status": "missing",
                    "required_for_signal": requirement.required_for_signal,
                    "series_key": requirement.series_key,
                    "source_key": status["source_key"],
                    "provider": status["provider"],
                    "source_type": status["source_type"],
                    "source_mode": status["source_mode"],
                    "automation_mode": status["automation_mode"],
                    "production_ingestion_approved": status["production_ingestion_approved"],
                    "configured_for_runtime": status["configured_for_runtime"],
                    "required_configuration": status["required_configuration"],
                    "latest_observation_date": status["latest_observation_date"],
                    "latest_reference_month_end": status["latest_reference_month_end"],
                    "latest_released_at": None,
                    "latest_ingested_at": None,
                    "reason": status["reason"],
                    "notes": status["notes"],
                }
            )
            continue

        observation = _latest_observation(session, requirement.series_key)
        if observation is None:
            continue
        latest_reference_month_end = max(
            observation.reference_month_end,
            latest_reference_month_end or observation.reference_month_end,
        )
        drivers.append(
            {
                "driver_key": requirement.driver_key,
                "label": requirement.label,
                "category": requirement.category,
                "status": "available",
                "required_for_signal": requirement.required_for_signal,
                "series_key": requirement.series_key,
                "source_key": observation.source_key,
                "provider": status["provider"],
                "source_type": status["source_type"],
                "source_mode": status["source_mode"],
                "automation_mode": status["automation_mode"],
                "production_ingestion_approved": status["production_ingestion_approved"],
                "configured_for_runtime": status["configured_for_runtime"],
                "required_configuration": status["required_configuration"],
                "latest_observation_date": observation.observation_date.isoformat(),
                "latest_reference_month_end": observation.reference_month_end.isoformat(),
                "latest_released_at": observation.released_at.isoformat() if observation.released_at else None,
                "latest_ingested_at": observation.ingested_at.isoformat(),
                "reason": None,
                "notes": status["notes"],
            }
        )

    if latest_reference_month_end is None:
        raise ValueError("No tactical driver freshness available")
    payload = {
        "snapshot_type": "tactical_driver_freshness",
        "reference_month_end": latest_reference_month_end.isoformat(),
        "snapshot_created_at": utcnow().isoformat(),
        "drivers": drivers,
    }
    upsert_client_snapshot(
        session,
        snapshot_type="tactical_driver_freshness",
        reference_month_end=latest_reference_month_end,
        feature_set_key=feature_set.feature_set_key,
        payload_json=payload,
    )
    session.commit()
    return payload


def get_latest_tactical_driver_history_snapshot(session: Session) -> ClientSnapshot | None:
    statement = (
        select(ClientSnapshot)
        .where(ClientSnapshot.snapshot_type == "tactical_driver_history")
        .order_by(ClientSnapshot.reference_month_end.desc(), ClientSnapshot.created_at.desc())
    )
    return session.execute(statement).scalars().first()


def get_latest_tactical_driver_latest_snapshot(session: Session) -> ClientSnapshot | None:
    statement = (
        select(ClientSnapshot)
        .where(ClientSnapshot.snapshot_type == "tactical_driver_latest")
        .order_by(ClientSnapshot.reference_month_end.desc(), ClientSnapshot.created_at.desc())
    )
    return session.execute(statement).scalars().first()


def get_latest_tactical_driver_freshness_snapshot(session: Session) -> ClientSnapshot | None:
    statement = (
        select(ClientSnapshot)
        .where(ClientSnapshot.snapshot_type == "tactical_driver_freshness")
        .order_by(ClientSnapshot.reference_month_end.desc(), ClientSnapshot.created_at.desc())
    )
    return session.execute(statement).scalars().first()
