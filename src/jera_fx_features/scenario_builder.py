"""Scenario set snapshot builder.

Pulls the REER anchor and spot from curated snapshots, computes the full
scenario set, and persists it as a ``ClientSnapshot``.
"""
from __future__ import annotations

from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from jera_fx_api.db.models import ClientSnapshot
from jera_fx_api.services import stable_hash, upsert_client_snapshot, upsert_feature_set, utcnow
from jera_fx_features.reer_bands import get_latest_reer_bands_snapshot
from jera_fx_features.scenario_engine import (
    SCENARIO_METHODOLOGY_VERSION,
    compute_scenario_paths,
    default_scenario_definitions,
    scenario_set_to_dict,
)
from jera_fx_features.source_freshness import get_latest_source_freshness_snapshot

SCENARIO_SET_FEATURE_SET_KEY = "scenario_set_snapshot_v1"


def _resolve_anchor_and_spot(session: Session) -> tuple[float, float, str]:
    """Derive the REER-based anchor and current spot from curated snapshots.

    For v1 the anchor is the latest PTAX spot. In future versions this may
    switch to a REER-implied fair value once the conversion layer exists.

    Returns (anchor, spot, anchor_source_label).
    """
    # Get spot from source freshness (it contains spot_freshness).
    freshness_snapshot = get_latest_source_freshness_snapshot(session)
    if freshness_snapshot is not None:
        spot_data = freshness_snapshot.payload_json.get("spot_freshness", {})
        latest_spot = spot_data.get("latest_spot", {})
        spot_value = latest_spot.get("value")
        if spot_value is not None:
            return float(spot_value), float(spot_value), "ptax_spot_latest"

    # Fallback: read from client overview.
    overview_snapshot = session.execute(
        select(ClientSnapshot)
        .where(ClientSnapshot.snapshot_type == "client_overview")
        .order_by(ClientSnapshot.reference_month_end.desc(), ClientSnapshot.created_at.desc())
    ).scalars().first()
    if overview_snapshot is not None:
        spot_value = overview_snapshot.payload_json.get("spot", {}).get("value")
        if spot_value is not None:
            return float(spot_value), float(spot_value), "client_overview_spot"

    raise ValueError(
        "Cannot resolve anchor/spot for scenario engine: "
        "no source freshness or client overview snapshot found."
    )


def build_scenario_set_snapshot(
    session: Session,
    *,
    anchor_override: float | None = None,
) -> dict[str, Any]:
    """Build and persist a scenario set snapshot.

    Parameters
    ----------
    session
        Active DB session.
    anchor_override
        If provided, overrides the auto-resolved anchor (useful for testing
        or for using a REER-implied fair value once available).
    """
    feature_set = upsert_feature_set(
        session,
        feature_set_key=SCENARIO_SET_FEATURE_SET_KEY,
        name="Scenario set snapshot",
        version="v1",
        description="Reproducible BRL/USD scenario paths with driver assumptions and fan chart.",
        scale_policy="nominal-brl-usd",
        definition_hash=stable_hash({"feature_set_key": SCENARIO_SET_FEATURE_SET_KEY}),
    )

    resolved_anchor, spot_value, anchor_source = _resolve_anchor_and_spot(session)
    anchor = anchor_override if anchor_override is not None else resolved_anchor
    if anchor_override is not None:
        anchor_source = f"manual-override ({anchor_source} was {resolved_anchor:.4f})"

    today = utcnow().date()
    scenario_result = compute_scenario_paths(
        anchor,
        spot_value=spot_value,
        reference_date=today.isoformat(),
        anchor_source=anchor_source,
    )
    payload = {
        "snapshot_type": "scenario_set",
        "reference_month_end": today.isoformat(),
        "snapshot_created_at": utcnow().isoformat(),
        **scenario_set_to_dict(scenario_result),
    }
    upsert_client_snapshot(
        session,
        snapshot_type="scenario_set",
        reference_month_end=today,
        feature_set_key=feature_set.feature_set_key,
        payload_json=payload,
    )
    session.commit()
    return payload


def get_latest_scenario_set_snapshot(session: Session) -> ClientSnapshot | None:
    statement = (
        select(ClientSnapshot)
        .where(ClientSnapshot.snapshot_type == "scenario_set")
        .order_by(ClientSnapshot.reference_month_end.desc(), ClientSnapshot.created_at.desc())
    )
    return session.execute(statement).scalars().first()
