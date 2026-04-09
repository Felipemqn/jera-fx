from __future__ import annotations

from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from jera_fx_api.db.models import ClientSnapshot, FeatureValue, Observation
from jera_fx_api.services import stable_hash, upsert_client_snapshot, upsert_feature_set, utcnow
from jera_fx_connectors.bcb_ptax import PTAX_MONTHLY_FEATURE_SET_KEY
from jera_fx_registry.series_catalog import SeriesCatalog

SOURCE_FRESHNESS_FEATURE_SET_KEY = "source_freshness_snapshot_v1"
SPOT_FRESHNESS_FEATURE_SET_KEY = "spot_freshness_snapshot_v1"
PTAX_MONTHLY_HISTORY_FEATURE_SET_KEY = "ptax_monthly_history_snapshot_v1"


def _latest_observation(session: Session, series_key: str) -> Observation:
    statement = (
        select(Observation)
        .where(Observation.series_key == series_key)
        .order_by(Observation.observation_date.desc())
    )
    observation = session.execute(statement).scalars().first()
    if observation is None:
        raise ValueError(f"No observations found for {series_key}")
    return observation


def _source_freshness_rows(session: Session) -> list[dict[str, Any]]:
    source_rows: list[dict[str, Any]] = []
    statement = select(Observation).order_by(Observation.source_key.asc(), Observation.observation_date.desc())
    observations = session.execute(statement).scalars().all()
    by_source: dict[str, Observation] = {}
    for row in observations:
        by_source.setdefault(row.source_key, row)
    for source_key, observation in by_source.items():
        source_rows.append(
            {
                "source_key": source_key,
                "latest_observation_date": observation.observation_date.isoformat(),
                "latest_reference_month_end": observation.reference_month_end.isoformat(),
                "latest_released_at": observation.released_at.isoformat() if observation.released_at else None,
                "latest_ingested_at": observation.ingested_at.isoformat(),
            }
        )
    return source_rows


def build_ptax_monthly_history_snapshot(session: Session) -> dict[str, Any]:
    feature_set = upsert_feature_set(
        session,
        feature_set_key=PTAX_MONTHLY_HISTORY_FEATURE_SET_KEY,
        name="PTAX monthly history snapshot",
        version="v1",
        description="Curated monthly PTAX close history derived from daily observations.",
        scale_policy="source-native",
        definition_hash=stable_hash({"feature_set_key": PTAX_MONTHLY_HISTORY_FEATURE_SET_KEY}),
    )
    payload_series: list[dict[str, Any]] = []
    reference_month_end = None
    for series_key in ("ptax_usd_brl_buy", "ptax_usd_brl_sell"):
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
        series_rows = [
            {
                "reference_month_end": row.reference_month_end.isoformat(),
                "observation_date": row.observation_date.isoformat() if row.observation_date else None,
                "value": row.value_numeric,
                "units": row.units,
                "scale_policy": row.scale_policy,
            }
            for row in rows
        ]
        latest_observation = _latest_observation(session, series_key)
        payload_series.append(
            {
                "series_key": series_key,
                "source_code": latest_observation.attributes_json.get("source_code") if latest_observation else None,
                "points": series_rows,
                "latest_monthly_close": series_rows[-1] if series_rows else None,
                "latest_observation": {
                    "observation_date": latest_observation.observation_date.isoformat() if latest_observation else None,
                    "reference_month_end": latest_observation.reference_month_end.isoformat() if latest_observation else None,
                    "value": latest_observation.value_numeric if latest_observation else None,
                    "units": latest_observation.units if latest_observation else None,
                    "scale_policy": latest_observation.scale_policy if latest_observation else None,
                    "released_at": latest_observation.released_at.isoformat() if latest_observation and latest_observation.released_at else None,
                    "ingested_at": latest_observation.ingested_at.isoformat() if latest_observation else None,
                },
            }
        )
        if rows:
            reference_month_end = rows[-1].reference_month_end

    if reference_month_end is None:
        raise ValueError("No PTAX monthly history found")

    payload = {
        "snapshot_type": "ptax_monthly_history",
        "reference_month_end": reference_month_end.isoformat(),
        "snapshot_created_at": utcnow().isoformat(),
        "series": payload_series,
    }
    upsert_client_snapshot(
        session,
        snapshot_type="ptax_monthly_history",
        reference_month_end=reference_month_end,
        feature_set_key=feature_set.feature_set_key,
        payload_json=payload,
    )
    session.commit()
    return payload


def build_source_freshness_snapshot(session: Session, catalog: SeriesCatalog) -> dict[str, Any]:
    source_feature_set = upsert_feature_set(
        session,
        feature_set_key=SOURCE_FRESHNESS_FEATURE_SET_KEY,
        name="Source freshness snapshot",
        version="v1",
        description="Latest observation freshness by upstream source.",
        scale_policy="source-native",
        definition_hash=stable_hash({"feature_set_key": SOURCE_FRESHNESS_FEATURE_SET_KEY}),
    )
    spot_feature_set = upsert_feature_set(
        session,
        feature_set_key=SPOT_FRESHNESS_FEATURE_SET_KEY,
        name="Spot freshness snapshot",
        version="v1",
        description="Latest PTAX spot observation and latest monthly close.",
        scale_policy="source-native",
        definition_hash=stable_hash({"feature_set_key": SPOT_FRESHNESS_FEATURE_SET_KEY}),
    )

    ptax_sell = _latest_observation(session, "ptax_usd_brl_sell")
    monthly_history = build_ptax_monthly_history_snapshot(session)
    latest_monthly_close = next(
        item["latest_monthly_close"]
        for item in monthly_history["series"]
        if item["series_key"] == "ptax_usd_brl_sell"
    )
    source_rows = _source_freshness_rows(session)
    source_reference_month_end = max(
        pd.to_datetime(row["latest_reference_month_end"]).date() for row in source_rows
    )
    spot_reference_month_end = pd.to_datetime(ptax_sell.reference_month_end).date()
    snapshot_created_at = utcnow().isoformat()

    spot_payload = {
        "series_key": "ptax_usd_brl_sell",
        "source_code": catalog.get_series("ptax_usd_brl_sell").source_code,
        "latest_spot": {
            "observation_date": ptax_sell.observation_date.isoformat(),
            "reference_month_end": ptax_sell.reference_month_end.isoformat(),
            "value": ptax_sell.value_numeric,
            "units": ptax_sell.units,
            "scale_policy": ptax_sell.scale_policy,
            "released_at": ptax_sell.released_at.isoformat() if ptax_sell.released_at else None,
            "ingested_at": ptax_sell.ingested_at.isoformat(),
        },
        "latest_monthly_close": latest_monthly_close,
    }
    source_payload = {
        "snapshot_type": "source_freshness",
        "reference_month_end": source_reference_month_end.isoformat(),
        "snapshot_created_at": snapshot_created_at,
        "sources": source_rows,
        "spot_freshness": spot_payload,
    }

    upsert_client_snapshot(
        session,
        snapshot_type="spot_freshness",
        reference_month_end=spot_reference_month_end,
        feature_set_key=spot_feature_set.feature_set_key,
        payload_json={
            "snapshot_type": "spot_freshness",
            "reference_month_end": spot_reference_month_end.isoformat(),
            "snapshot_created_at": snapshot_created_at,
            **spot_payload,
        },
    )
    upsert_client_snapshot(
        session,
        snapshot_type="source_freshness",
        reference_month_end=source_reference_month_end,
        feature_set_key=source_feature_set.feature_set_key,
        payload_json=source_payload,
    )
    session.commit()
    return source_payload


def get_latest_source_freshness_snapshot(session: Session) -> ClientSnapshot | None:
    statement = (
        select(ClientSnapshot)
        .where(ClientSnapshot.snapshot_type == "source_freshness")
        .order_by(ClientSnapshot.reference_month_end.desc(), ClientSnapshot.created_at.desc())
    )
    return session.execute(statement).scalars().first()


def get_latest_ptax_monthly_history_snapshot(session: Session) -> ClientSnapshot | None:
    statement = (
        select(ClientSnapshot)
        .where(ClientSnapshot.snapshot_type == "ptax_monthly_history")
        .order_by(ClientSnapshot.reference_month_end.desc(), ClientSnapshot.created_at.desc())
    )
    return session.execute(statement).scalars().first()
