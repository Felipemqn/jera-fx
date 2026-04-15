"""Investment mode snapshot builders.

Produces:
- Rolling regression snapshot (all windows)
- 1Y driver variation dashboard
- Saved scenario persistence (CRUD via API)
"""

from __future__ import annotations

from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from jera_fx_api.db.models import ClientSnapshot
from jera_fx_api.services import stable_hash, upsert_client_snapshot, upsert_feature_set, utcnow
from jera_fx_features.rolling_regression import (
    REGRESSION_DRIVERS,
    REGRESSION_METHODOLOGY_VERSION,
    compute_rolling_regressions,
    regression_result_to_dict,
)
from jera_fx_features.tactical_drivers import get_latest_tactical_driver_history_snapshot

ROLLING_REGRESSION_FEATURE_SET_KEY = "rolling_regression_snapshot_v1"
DRIVER_VARIATIONS_FEATURE_SET_KEY = "driver_variations_snapshot_v1"


def _extract_monthly_series(
    history_snapshot: ClientSnapshot,
) -> tuple[list[float], dict[str, list[float]], dict[str, list[str]]]:
    """Pull monthly value arrays from tactical driver history snapshot.

    Returns (dependent_values, driver_histories, driver_dates).
    """
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

    # Dependent variable
    dep_key = "ptax_usd_brl_sell"
    dep_series = series_map.get(dep_key, [])
    dependent_values = [v for _, v in dep_series]
    dependent_dates = [d for d, _ in dep_series]

    # Independent variables
    driver_histories: dict[str, list[float]] = {}
    driver_dates: dict[str, list[str]] = {}
    for dk in REGRESSION_DRIVERS:
        if dk in series_map:
            driver_histories[dk] = [v for _, v in series_map[dk]]
            driver_dates[dk] = [d for d, _ in series_map[dk]]

    return dependent_values, driver_histories, driver_dates


def build_rolling_regression_snapshot(session: Session) -> dict[str, Any]:
    """Build and persist rolling regression results."""
    feature_set = upsert_feature_set(
        session,
        feature_set_key=ROLLING_REGRESSION_FEATURE_SET_KEY,
        name="Rolling regression snapshot",
        version="v1",
        description="Multi-window OLS regressions of PTAX vs tactical drivers.",
        scale_policy="regression-coefficients",
        definition_hash=stable_hash({"feature_set_key": ROLLING_REGRESSION_FEATURE_SET_KEY}),
    )

    history_snapshot = get_latest_tactical_driver_history_snapshot(session)
    if history_snapshot is None:
        raise ValueError("Rolling regression requires tactical driver history snapshot")

    dep_values, driver_histories, _ = _extract_monthly_series(history_snapshot)

    result = compute_rolling_regressions(dep_values, driver_histories)
    result_dict = regression_result_to_dict(result)

    today = utcnow().date()
    payload = {
        "snapshot_type": "rolling_regression",
        "reference_month_end": today.isoformat(),
        "snapshot_created_at": utcnow().isoformat(),
        **result_dict,
    }

    upsert_client_snapshot(
        session,
        snapshot_type="rolling_regression",
        reference_month_end=today,
        feature_set_key=feature_set.feature_set_key,
        payload_json=payload,
    )
    session.commit()
    return payload


def build_driver_variations_snapshot(session: Session) -> dict[str, Any]:
    """Build 1Y variation dashboard for all drivers."""
    feature_set = upsert_feature_set(
        session,
        feature_set_key=DRIVER_VARIATIONS_FEATURE_SET_KEY,
        name="Driver variations snapshot",
        version="v1",
        description="Last-12-month variation for all tactical drivers.",
        scale_policy="percentage-change",
        definition_hash=stable_hash({"feature_set_key": DRIVER_VARIATIONS_FEATURE_SET_KEY}),
    )

    history_snapshot = get_latest_tactical_driver_history_snapshot(session)
    if history_snapshot is None:
        raise ValueError("Driver variations require tactical driver history snapshot")

    drivers_payload = history_snapshot.payload_json.get("drivers", [])
    variations: list[dict[str, Any]] = []

    for driver in drivers_payload:
        dk = driver["driver_key"]
        points = driver.get("points", [])
        if not points or driver.get("status") == "missing":
            variations.append({
                "driver_key": dk,
                "label": driver.get("label", dk),
                "category": driver.get("category", ""),
                "status": "missing",
                "current_value": None,
                "value_12m_ago": None,
                "change_absolute": None,
                "change_percent": None,
                "points_available": len(points),
            })
            continue

        current = points[-1]["value"]
        # Find value ~12 months ago
        idx_12m = max(0, len(points) - 12)
        value_12m = points[idx_12m]["value"]
        change_abs = current - value_12m
        change_pct = (change_abs / abs(value_12m) * 100) if value_12m != 0 else 0.0

        variations.append({
            "driver_key": dk,
            "label": driver.get("label", dk),
            "category": driver.get("category", ""),
            "status": "available",
            "current_value": round(current, 4),
            "value_12m_ago": round(value_12m, 4),
            "change_absolute": round(change_abs, 4),
            "change_percent": round(change_pct, 2),
            "points_available": len(points),
            "date_current": points[-1].get("reference_month_end"),
            "date_12m_ago": points[idx_12m].get("reference_month_end"),
        })

    today = utcnow().date()
    payload = {
        "snapshot_type": "driver_variations",
        "reference_month_end": today.isoformat(),
        "snapshot_created_at": utcnow().isoformat(),
        "variations": variations,
    }

    upsert_client_snapshot(
        session,
        snapshot_type="driver_variations",
        reference_month_end=today,
        feature_set_key=feature_set.feature_set_key,
        payload_json=payload,
    )
    session.commit()
    return payload


def get_latest_rolling_regression_snapshot(session: Session) -> ClientSnapshot | None:
    return session.execute(
        select(ClientSnapshot)
        .where(ClientSnapshot.snapshot_type == "rolling_regression")
        .order_by(ClientSnapshot.reference_month_end.desc(), ClientSnapshot.created_at.desc())
    ).scalars().first()


def get_latest_driver_variations_snapshot(session: Session) -> ClientSnapshot | None:
    return session.execute(
        select(ClientSnapshot)
        .where(ClientSnapshot.snapshot_type == "driver_variations")
        .order_by(ClientSnapshot.reference_month_end.desc(), ClientSnapshot.created_at.desc())
    ).scalars().first()
