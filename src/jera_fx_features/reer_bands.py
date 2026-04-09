from __future__ import annotations

from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from jera_fx_api.db.models import ClientSnapshot, FeatureValue, Observation
from jera_fx_api.services import stable_hash, upsert_client_snapshot, upsert_feature_set
from jera_fx_features.reer_canonical import REER_CANONICAL_FEATURE_SET_KEY
from jera_fx_features.reer_normalization import CANONICAL_SCALE_POLICY, RAW_SCALE_POLICY
from jera_fx_registry.series_catalog import SeriesCatalog

REER_BANDS_FEATURE_SET_KEY = "reer_bands_snapshot_v1"


def latest_raw_observation(session: Session, series_key: str) -> Observation:
    statement = (
        select(Observation)
        .where(Observation.series_key == series_key)
        .order_by(Observation.observation_date.desc())
    )
    observation = session.execute(statement).scalars().first()
    if observation is None:
        raise ValueError(f"No raw observations found for {series_key}")
    return observation


def canonical_history(session: Session, series_key: str) -> pd.DataFrame:
    statement = (
        select(FeatureValue)
        .where(
            FeatureValue.feature_set_key == REER_CANONICAL_FEATURE_SET_KEY,
            FeatureValue.series_key == series_key,
            FeatureValue.feature_name == "canonical_value",
        )
        .order_by(FeatureValue.reference_month_end.asc())
    )
    rows = session.execute(statement).scalars().all()
    if not rows:
        raise ValueError(f"No canonical REER feature values found for {series_key}")
    return pd.DataFrame(
        {
            "reference_month_end": [item.reference_month_end for item in rows],
            "value_numeric": [item.value_numeric for item in rows],
            "provenance_json": [item.provenance_json for item in rows],
        }
    )


def distribution_payload(frame: pd.DataFrame) -> dict[str, float]:
    series = frame["value_numeric"]
    latest_value = float(series.iloc[-1])
    quantiles = series.quantile([0.10, 0.25, 0.50, 0.75, 0.90])
    return {
        "percentile_rank": float((series <= latest_value).mean() * 100.0),
        "p10": float(quantiles.loc[0.10]),
        "p25": float(quantiles.loc[0.25]),
        "p50": float(quantiles.loc[0.50]),
        "p75": float(quantiles.loc[0.75]),
        "p90": float(quantiles.loc[0.90]),
    }


def _series_band_payload(session: Session, catalog: SeriesCatalog, series_key: str) -> dict[str, Any]:
    series_definition = catalog.get_series(series_key)
    raw_observation = latest_raw_observation(session, series_key)
    canonical_frame = canonical_history(session, series_key)
    latest_canonical = canonical_frame.iloc[-1]
    return {
        "series_key": series_key,
        "source_code": series_definition.source_code,
        "reference_month_end": raw_observation.reference_month_end.isoformat(),
        "native": {
            "value": raw_observation.value_numeric,
            "units": raw_observation.units,
            "scale_policy": RAW_SCALE_POLICY,
        },
        "canonical": {
            "value": float(latest_canonical["value_numeric"]),
            "units": series_definition.units,
            "scale_policy": CANONICAL_SCALE_POLICY,
        },
        "distribution": distribution_payload(canonical_frame),
        "normalization_factor": float(latest_canonical["provenance_json"]["scale_factor"]),
    }


def build_reer_bands_snapshot(session: Session, catalog: SeriesCatalog) -> dict[str, Any]:
    feature_set = upsert_feature_set(
        session,
        feature_set_key=REER_BANDS_FEATURE_SET_KEY,
        name="REER bands snapshot",
        version="v1",
        description="Canonical REER broad and narrow percentile bands for client presentation.",
        scale_policy=CANONICAL_SCALE_POLICY,
        definition_hash=stable_hash({"feature_set_key": REER_BANDS_FEATURE_SET_KEY, "display_scale": CANONICAL_SCALE_POLICY}),
    )

    broad_payload = _series_band_payload(session, catalog, "reer_120_br")
    narrow_payload = _series_band_payload(session, catalog, "reer_51_br")
    reference_month_end = broad_payload["reference_month_end"]
    payload: dict[str, Any] = {
        "snapshot_type": "reer_bands",
        "reference_month_end": reference_month_end,
        "client_default_scale_policy": CANONICAL_SCALE_POLICY,
        "normalization_policy": {
            "native_scale_policy": RAW_SCALE_POLICY,
            "canonical_scale_policy": CANONICAL_SCALE_POLICY,
            "anchor_year": 2020,
            "client_default_scale_policy": CANONICAL_SCALE_POLICY,
            "prototype_status": "reference-only",
        },
        "broad": broad_payload,
        "narrow": narrow_payload,
    }
    upsert_client_snapshot(
        session,
        snapshot_type="reer_bands",
        reference_month_end=pd.to_datetime(reference_month_end).date(),
        feature_set_key=feature_set.feature_set_key,
        payload_json=payload,
    )
    session.commit()
    return payload


def get_latest_reer_bands_snapshot(session: Session) -> ClientSnapshot | None:
    statement = (
        select(ClientSnapshot)
        .where(ClientSnapshot.snapshot_type == "reer_bands")
        .order_by(ClientSnapshot.reference_month_end.desc(), ClientSnapshot.created_at.desc())
    )
    return session.execute(statement).scalars().first()
