from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from jera_fx_api.db.models import ClientSnapshot, FeatureValue, Observation
from jera_fx_api.services import stable_hash, upsert_client_snapshot, upsert_feature_set, utcnow
from jera_fx_features.reer_canonical import REER_CANONICAL_FEATURE_SET_KEY
from jera_fx_features.reer_normalization import CANONICAL_SCALE_POLICY
from jera_fx_features.reer_bands import canonical_history, distribution_payload, latest_raw_observation
from jera_fx_registry.series_catalog import SeriesCatalog

CLIENT_OVERVIEW_FEATURE_SET_KEY = "client_overview_snapshot_v1"

def build_client_overview_snapshot(session: Session, catalog: SeriesCatalog) -> dict[str, Any]:
    feature_set = upsert_feature_set(
        session,
        feature_set_key=CLIENT_OVERVIEW_FEATURE_SET_KEY,
        name="Client overview snapshot",
        version="v1",
        description="Database-backed client overview snapshot with spot, broad REER, narrow REER, and normalization metadata.",
        scale_policy=CANONICAL_SCALE_POLICY,
        definition_hash=stable_hash({"feature_set_key": CLIENT_OVERVIEW_FEATURE_SET_KEY, "display_scale": CANONICAL_SCALE_POLICY}),
    )

    broad_raw = latest_raw_observation(session, "reer_120_br")
    narrow_raw = latest_raw_observation(session, "reer_51_br")
    ptax_sell_raw = latest_raw_observation(session, "ptax_usd_brl_sell")
    broad_canonical_frame = canonical_history(session, "reer_120_br")
    narrow_canonical_frame = canonical_history(session, "reer_51_br")
    broad_latest_canonical = broad_canonical_frame.iloc[-1]
    narrow_latest_canonical = narrow_canonical_frame.iloc[-1]
    if broad_raw.reference_month_end != narrow_raw.reference_month_end:
        raise ValueError(
            "Broad and narrow REER series are not aligned on the same reference_month_end"
        )

    broad_definition = catalog.get_series("reer_120_br")
    narrow_definition = catalog.get_series("reer_51_br")
    ptax_definition = catalog.get_series("ptax_usd_brl_sell")

    latest_reer_reference_month_end = broad_raw.reference_month_end
    snapshot_created_at = utcnow()
    payload: dict[str, Any] = {
        "snapshot_type": "client_overview",
        "reference_month_end": latest_reer_reference_month_end.isoformat(),
        "spot": {
            "series_key": ptax_definition.series_key,
            "source_code": ptax_definition.source_code,
            "observation_date": ptax_sell_raw.observation_date.isoformat(),
            "reference_month_end": ptax_sell_raw.reference_month_end.isoformat(),
            "value": ptax_sell_raw.value_numeric,
            "units": ptax_sell_raw.units,
            "scale_policy": ptax_sell_raw.scale_policy,
        },
        "reer": {
            "client_default_scale_policy": CANONICAL_SCALE_POLICY,
            "broad": {
                "series_key": broad_definition.series_key,
                "source_code": broad_definition.source_code,
                "reference_month_end": broad_raw.reference_month_end.isoformat(),
                "native": {
                    "value": broad_raw.value_numeric,
                    "units": broad_raw.units,
                    "scale_policy": broad_raw.scale_policy,
                },
                "canonical": {
                    "value": float(broad_latest_canonical["value_numeric"]),
                    "units": broad_definition.units,
                    "scale_policy": CANONICAL_SCALE_POLICY,
                },
                "distribution": distribution_payload(broad_canonical_frame),
                "normalization_factor": float(broad_latest_canonical["provenance_json"]["scale_factor"]),
            },
            "narrow": {
                "series_key": narrow_definition.series_key,
                "source_code": narrow_definition.source_code,
                "reference_month_end": narrow_raw.reference_month_end.isoformat(),
                "native": {
                    "value": narrow_raw.value_numeric,
                    "units": narrow_raw.units,
                    "scale_policy": narrow_raw.scale_policy,
                },
                "canonical": {
                    "value": float(narrow_latest_canonical["value_numeric"]),
                    "units": narrow_definition.units,
                    "scale_policy": CANONICAL_SCALE_POLICY,
                },
                "distribution": distribution_payload(narrow_canonical_frame),
                "normalization_factor": float(narrow_latest_canonical["provenance_json"]["scale_factor"]),
            },
        },
        "normalization_policy": {
            "native_scale_policy": "source-native",
            "canonical_scale_policy": CANONICAL_SCALE_POLICY,
            "anchor_year": 2020,
            "client_default_scale_policy": CANONICAL_SCALE_POLICY,
            "prototype_status": "reference-only",
        },
        "last_updated": {
            "snapshot_created_at": snapshot_created_at.isoformat(),
            "latest_reer_reference_month_end": latest_reer_reference_month_end.isoformat(),
            "latest_ptax_observation_date": ptax_sell_raw.observation_date.isoformat(),
            "sources": [
                {
                    "source_key": broad_definition.source_key,
                    "latest_observation_date": broad_raw.observation_date.isoformat(),
                    "latest_reference_month_end": broad_raw.reference_month_end.isoformat(),
                    "latest_ingested_at": broad_raw.ingested_at.isoformat(),
                },
                {
                    "source_key": ptax_definition.source_key,
                    "latest_observation_date": ptax_sell_raw.observation_date.isoformat(),
                    "latest_reference_month_end": ptax_sell_raw.reference_month_end.isoformat(),
                    "latest_ingested_at": ptax_sell_raw.ingested_at.isoformat(),
                },
            ],
        },
    }

    upsert_client_snapshot(
        session,
        snapshot_type="client_overview",
        reference_month_end=latest_reer_reference_month_end,
        feature_set_key=feature_set.feature_set_key,
        payload_json=payload,
    )
    session.commit()
    return payload


def get_latest_client_overview_snapshot(session: Session) -> ClientSnapshot | None:
    statement = (
        select(ClientSnapshot)
        .where(ClientSnapshot.snapshot_type == "client_overview")
        .order_by(ClientSnapshot.reference_month_end.desc(), ClientSnapshot.created_at.desc())
    )
    return session.execute(statement).scalars().first()
