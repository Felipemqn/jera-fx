"""Risk toolkit — factor sleeves, stress testing, and regime heatmaps.

Methodology version: ``risk-toolkit-v1``

This module provides portfolio-oriented risk decomposition:
1. Factor sleeves — attribute BRL/USD exposure to named risk factors
2. Stress testing — compute BRL/USD impact under discrete driver shocks
3. Regime heatmap — DXY × CDS regime classification grid

All computations use curated snapshot data and the scenario engine betas.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from jera_fx_features.scenario_engine import HORIZON_BETAS, ScenarioAssumptions, compute_fair_value


RISK_METHODOLOGY_VERSION = "risk-toolkit-v1"

# ---------------------------------------------------------------------------
# Factor Sleeves
# ---------------------------------------------------------------------------

FACTOR_SLEEVES: dict[str, dict[str, Any]] = {
    "usd_global": {
        "label": "USD Global",
        "drivers": ["broad_usd_index"],
        "description": "Exposure to broad dollar strength. DXY up = BRL weak.",
    },
    "risco_brasil": {
        "label": "Risco Brasil",
        "drivers": ["cds_brazil_5y"],
        "description": "Sovereign risk premium. CDS up = BRL weak.",
    },
    "commodities": {
        "label": "Commodities",
        "drivers": ["commodity_terms_of_trade"],
        "description": "Terms-of-trade channel. Commodity up = BRL strong.",
    },
    "carry_juros": {
        "label": "Carry / Juros Reais",
        "drivers": ["sgs_selic_target_rate"],
        "description": "Interest rate differential / carry attractiveness. High Selic = BRL support.",
    },
}


@dataclass
class SleeveExposure:
    sleeve_key: str
    label: str
    description: str
    beta_1y: float
    beta_5y: float
    beta_10y: float
    current_driver_value: float | None
    directional_impact: str  # "brl-weak" | "brl-strong" | "neutral"


def compute_factor_sleeves(
    driver_latest: dict[str, float],
    anchor: float,
) -> list[dict[str, Any]]:
    """Compute factor sleeve exposures using scenario engine betas."""
    sleeves: list[dict[str, Any]] = []

    for sleeve_key, sleeve_def in FACTOR_SLEEVES.items():
        driver_key = sleeve_def["drivers"][0]
        current_val = driver_latest.get(driver_key)

        # Extract betas at different horizons
        betas_1y = HORIZON_BETAS.get(1, {})
        betas_5y = HORIZON_BETAS.get(5, {})
        betas_10y = HORIZON_BETAS.get(10, {})

        # Map sleeve to the relevant beta
        beta_map = {
            "usd_global": "beta_dxy",
            "risco_brasil": "beta_cds",
            "commodities": "beta_comm",
            "carry_juros": "beta_carry",
        }
        beta_name = beta_map.get(sleeve_key, "")

        sleeves.append({
            "sleeve_key": sleeve_key,
            "label": sleeve_def["label"],
            "description": sleeve_def["description"],
            "drivers": sleeve_def["drivers"],
            "beta_1y": betas_1y.get(beta_name, 0.0),
            "beta_5y": betas_5y.get(beta_name, 0.0),
            "beta_10y": betas_10y.get(beta_name, 0.0),
            "current_driver_value": round(current_val, 4) if current_val is not None else None,
        })

    return sleeves


# ---------------------------------------------------------------------------
# Stress Testing
# ---------------------------------------------------------------------------

STRESS_SCENARIOS: list[dict[str, Any]] = [
    {
        "name": "DXY +10%",
        "description": "Broad dollar rallies 10% from current",
        "shocks": {"dxy_delta_pct": 10.0, "cds_shock_bps": 0, "carry_pct": 0, "commodity_shock_pct": 0, "productivity_gap_pct": 0},
    },
    {
        "name": "CDS +200bps",
        "description": "Brazil sovereign risk spikes 200 basis points",
        "shocks": {"dxy_delta_pct": 0, "cds_shock_bps": 200, "carry_pct": 0, "commodity_shock_pct": 0, "productivity_gap_pct": 0},
    },
    {
        "name": "Commodity -20%",
        "description": "Terms-of-trade collapse of 20%",
        "shocks": {"dxy_delta_pct": 0, "cds_shock_bps": 0, "carry_pct": 0, "commodity_shock_pct": -20, "productivity_gap_pct": 0},
    },
    {
        "name": "Selic cut to 8%",
        "description": "Aggressive rate cuts remove carry support",
        "shocks": {"dxy_delta_pct": 0, "cds_shock_bps": 0, "carry_pct": -5.0, "commodity_shock_pct": 0, "productivity_gap_pct": 0},
    },
    {
        "name": "Twin shock (DXY+CDS)",
        "description": "Dollar rally + sovereign risk spike simultaneously",
        "shocks": {"dxy_delta_pct": 8.0, "cds_shock_bps": 150, "carry_pct": 0, "commodity_shock_pct": -10, "productivity_gap_pct": 0},
    },
    {
        "name": "Benign reversal",
        "description": "Dollar weakens, risk normalizes, commodity recovery",
        "shocks": {"dxy_delta_pct": -8.0, "cds_shock_bps": -80, "carry_pct": 2.0, "commodity_shock_pct": 15, "productivity_gap_pct": 0},
    },
]


def run_stress_tests(
    anchor: float,
    current_dxy: float,
    *,
    horizons: list[int] | None = None,
) -> list[dict[str, Any]]:
    """Run predefined stress scenarios and return BRL/USD impacts."""
    if horizons is None:
        horizons = [1, 5]

    results: list[dict[str, Any]] = []
    for scenario in STRESS_SCENARIOS:
        shocks = scenario["shocks"]
        # Apply DXY shock as percentage
        shocked_dxy = current_dxy * (1 + shocks["dxy_delta_pct"] / 100)

        assumptions = ScenarioAssumptions(
            dxy=shocked_dxy,
            cds_shock_bps=shocks["cds_shock_bps"],
            carry_pct=shocks["carry_pct"],
            commodity_shock_pct=shocks["commodity_shock_pct"],
            productivity_gap_pct=shocks["productivity_gap_pct"],
        )

        horizon_results = []
        for h in horizons:
            hp = compute_fair_value(anchor, assumptions, h)
            impact = hp.fair_value - anchor
            impact_pct = (impact / anchor * 100) if anchor else 0
            horizon_results.append({
                "horizon_years": h,
                "fair_value": round(hp.fair_value, 4),
                "impact_brl": round(impact, 4),
                "impact_pct": round(impact_pct, 2),
            })

        results.append({
            "name": scenario["name"],
            "description": scenario["description"],
            "shocks": shocks,
            "horizons": horizon_results,
        })

    return results


# ---------------------------------------------------------------------------
# Regime Heatmap (DXY × CDS)
# ---------------------------------------------------------------------------

def build_regime_heatmap(
    anchor: float,
    *,
    dxy_range: tuple[float, float, float] = (95, 135, 5),   # min, max, step
    cds_range: tuple[float, float, float] = (-100, 300, 50),  # min, max, step (bps shock)
    horizon: int = 5,
) -> dict[str, Any]:
    """Build a DXY × CDS regime heatmap of fair BRL/USD values."""
    dxy_vals = []
    v = dxy_range[0]
    while v <= dxy_range[1]:
        dxy_vals.append(v)
        v += dxy_range[2]

    cds_vals = []
    v = cds_range[0]
    while v <= cds_range[1]:
        cds_vals.append(v)
        v += cds_range[2]

    cells: list[dict[str, Any]] = []
    all_fairs: list[float] = []
    for cds in cds_vals:
        for dxy in dxy_vals:
            assumptions = ScenarioAssumptions(
                dxy=dxy, cds_shock_bps=cds, carry_pct=0, commodity_shock_pct=0, productivity_gap_pct=0,
            )
            hp = compute_fair_value(anchor, assumptions, horizon)
            cells.append({"dxy": dxy, "cds_shock_bps": cds, "fair_value": round(hp.fair_value, 4)})
            all_fairs.append(hp.fair_value)

    return {
        "methodology_version": RISK_METHODOLOGY_VERSION,
        "horizon_years": horizon,
        "anchor": round(anchor, 4),
        "dxy_values": dxy_vals,
        "cds_values": cds_vals,
        "cells": cells,
        "min_fair": round(min(all_fairs), 4) if all_fairs else 0,
        "max_fair": round(max(all_fairs), 4) if all_fairs else 0,
    }


# ---------------------------------------------------------------------------
# Full risk snapshot
# ---------------------------------------------------------------------------

def build_risk_snapshot(
    anchor: float,
    spot: float,
    driver_latest: dict[str, float],
    current_dxy: float,
) -> dict[str, Any]:
    """Build the complete risk toolkit snapshot."""
    sleeves = compute_factor_sleeves(driver_latest, anchor)
    stress = run_stress_tests(anchor, current_dxy)
    heatmap = build_regime_heatmap(anchor)

    return {
        "methodology_version": RISK_METHODOLOGY_VERSION,
        "anchor": round(anchor, 4),
        "spot": round(spot, 4),
        "current_dxy": round(current_dxy, 4),
        "factor_sleeves": sleeves,
        "stress_tests": stress,
        "regime_heatmap": heatmap,
    }
