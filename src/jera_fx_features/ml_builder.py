"""ML model snapshot builder.

Trains ridge + GBM, runs walk-forward backtests, and persists
model registry entries as a ClientSnapshot.
"""
from __future__ import annotations

from typing import Any

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from jera_fx_api.db.models import ClientSnapshot
from jera_fx_api.services import stable_hash, upsert_client_snapshot, upsert_feature_set, utcnow
from jera_fx_features.ml_models import ML_METHODOLOGY_VERSION, build_model_registry
from jera_fx_features.rolling_regression import REGRESSION_DRIVERS
from jera_fx_features.tactical_drivers import get_latest_tactical_driver_history_snapshot

ML_REGISTRY_FEATURE_SET_KEY = "ml_model_registry_v1"


def build_ml_registry_snapshot(session: Session) -> dict[str, Any]:
    """Train models, backtest, and persist registry."""
    feature_set = upsert_feature_set(
        session,
        feature_set_key=ML_REGISTRY_FEATURE_SET_KEY,
        name="ML model registry",
        version="v1",
        description="Ridge and GBM research models with walk-forward backtests.",
        scale_policy="model-registry",
        definition_hash=stable_hash({"feature_set_key": ML_REGISTRY_FEATURE_SET_KEY}),
    )

    history_snapshot = get_latest_tactical_driver_history_snapshot(session)
    if history_snapshot is None:
        raise ValueError("ML registry requires tactical driver history snapshot")

    drivers = history_snapshot.payload_json.get("drivers", [])
    series_map: dict[str, list[tuple[str, float]]] = {}
    for driver in drivers:
        dk = driver["driver_key"]
        if driver.get("status") == "missing" or not driver.get("points"):
            continue
        series_map[dk] = [
            (p["reference_month_end"], p["value"])
            for p in driver["points"]
            if p.get("value") is not None
        ]

    dep_key = "ptax_usd_brl_sell"
    dep_series = series_map.get(dep_key, [])
    if not dep_series:
        raise ValueError("No PTAX data for ML training")

    y = np.array([v for _, v in dep_series])
    dates = [d for d, _ in dep_series]

    # Build feature matrix from available drivers
    available_drivers = [dk for dk in REGRESSION_DRIVERS if dk in series_map]
    n = min(len(dep_series), *(len(series_map[dk]) for dk in available_drivers))
    y = y[-n:]
    dates = dates[-n:]
    X = np.column_stack([np.array([v for _, v in series_map[dk][-n:]]) for dk in available_drivers])

    entries = build_model_registry(X, y, dates, available_drivers, min_train=min(24, n - 1))

    # Compare against v1 baseline (tactical signal z-score)
    baseline_comparison = {
        "baseline": "tactical-signal-score-v1",
        "note": "ML models are research-only. Promotion to client-facing requires explicit approval.",
    }

    today = utcnow().date()
    payload = {
        "snapshot_type": "ml_model_registry",
        "reference_month_end": today.isoformat(),
        "snapshot_created_at": utcnow().isoformat(),
        "methodology_version": ML_METHODOLOGY_VERSION,
        "driver_keys": available_drivers,
        "n_observations": n,
        "models": entries,
        "baseline_comparison": baseline_comparison,
    }

    upsert_client_snapshot(
        session,
        snapshot_type="ml_model_registry",
        reference_month_end=today,
        feature_set_key=feature_set.feature_set_key,
        payload_json=payload,
    )
    session.commit()
    return payload


def get_latest_ml_registry_snapshot(session: Session) -> ClientSnapshot | None:
    return session.execute(
        select(ClientSnapshot)
        .where(ClientSnapshot.snapshot_type == "ml_model_registry")
        .order_by(ClientSnapshot.reference_month_end.desc(), ClientSnapshot.created_at.desc())
    ).scalars().first()
