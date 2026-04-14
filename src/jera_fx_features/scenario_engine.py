"""Scenario engine v1 — reproducible BRL/USD scenario paths.

Methodology version: ``scenario-engine-v1``

This module produces a **scenario set**: a collection of named scenarios,
each with driver assumptions, probability weights, and BRL/USD paths
across standard horizons (1Y, 3Y, 5Y, 10Y).

Design principles
-----------------
* **No hardcoded paths** — every BRL/USD level is computed from driver
  assumptions (REER anchor, DXY, CDS, carry, commodity, productivity).
* **Assumptions are data** — stored in the snapshot alongside the computed
  paths so the result is fully reproducible.
* **Probability-weighted expected path** — fan chart center line is the
  probability-weighted average of the scenario paths.
* **Horizon-dependent betas** — short horizons are dominated by DXY/CDS,
  long horizons by productivity/structural mean-reversion.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from typing import Any


# ---------------------------------------------------------------------------
# Methodology constants — v1
# ---------------------------------------------------------------------------

SCENARIO_METHODOLOGY_VERSION = "scenario-engine-v1"

#: Standard horizons in years.
HORIZONS: list[int] = [1, 3, 5, 10]

#: Horizon-dependent betas.  Keys are horizon years.
#: These control how much each driver moves the fair value relative to the
#: REER anchor at each horizon.
#:   beta_dxy: elasticity of BRL/USD to broad dollar index (positive = USD strong → BRL weak)
#:   beta_cds: semi-elasticity to CDS shock in bps (positive = risk up → BRL weak)
#:   beta_carry: semi-elasticity to carry differential (positive = high carry → BRL strong, so sign is negative in formula)
#:   beta_comm: semi-elasticity to commodity terms-of-trade shock (positive = commodity up → BRL strong, negative in formula)
#:   beta_prod: semi-elasticity to US-BR productivity gap (positive = US exceptionalism → BRL weak)
HORIZON_BETAS: dict[int, dict[str, float]] = {
    1:  {"beta_dxy": 0.55, "beta_cds": 0.0012, "beta_carry": -0.04, "beta_comm": -0.003, "beta_prod": 0.00},
    3:  {"beta_dxy": 0.45, "beta_cds": 0.0010, "beta_carry": -0.03, "beta_comm": -0.004, "beta_prod": 0.02},
    5:  {"beta_dxy": 0.35, "beta_cds": 0.0008, "beta_carry": -0.02, "beta_comm": -0.005, "beta_prod": 0.04},
    10: {"beta_dxy": 0.20, "beta_cds": 0.0005, "beta_carry": -0.01, "beta_comm": -0.006, "beta_prod": 0.08},
}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ScenarioAssumptions:
    """Driver assumptions for a single scenario."""
    dxy: float                   # Broad USD index level
    cds_shock_bps: float         # CDS change from current level in bps
    carry_pct: float             # Real carry differential (%)
    commodity_shock_pct: float   # Commodity terms-of-trade change (%)
    productivity_gap_pct: float  # US minus BR productivity growth gap (%)


@dataclass
class ScenarioDefinition:
    """A named scenario with assumptions and probability."""
    scenario_key: str
    label: str
    narrative: str
    probability: float
    color: str
    assumptions: ScenarioAssumptions


@dataclass
class HorizonPoint:
    """Computed fair value at a single horizon."""
    horizon_years: int
    fair_value: float
    betas_used: dict[str, float]
    driver_contributions: dict[str, float]


@dataclass
class ScenarioResult:
    """Computed paths for a single scenario."""
    scenario_key: str
    label: str
    narrative: str
    probability: float
    color: str
    assumptions: dict[str, float]
    horizons: list[HorizonPoint]


@dataclass
class ScenarioSetResult:
    """Complete scenario set with all scenarios and weighted expected path."""
    methodology_version: str
    anchor_value: float
    anchor_source: str
    reference_date: str
    spot_value: float
    scenarios: list[ScenarioResult]
    expected_path: list[dict[str, Any]]
    fan_chart: list[dict[str, Any]]


# ---------------------------------------------------------------------------
# Default scenario definitions (v1)
# ---------------------------------------------------------------------------

def default_scenario_definitions() -> list[ScenarioDefinition]:
    """Return the v1 scenario set.

    These are the four canonical scenarios from the institutional framework.
    In future versions, scenarios may be loaded from the database or
    user-defined. For v1, they are deterministic and documented.
    """
    return [
        ScenarioDefinition(
            scenario_key="benign",
            label="Reforma + dolar mais fraco",
            narrative=(
                "Queda do premio de risco local e normalizacao do dolar global. "
                "O BRL volta para a metade forte da banda."
            ),
            probability=0.25,
            color="green",
            assumptions=ScenarioAssumptions(
                dxy=100.0,
                cds_shock_bps=-50.0,
                carry_pct=6.0,
                commodity_shock_pct=10.0,
                productivity_gap_pct=-1.0,
            ),
        ),
        ScenarioDefinition(
            scenario_key="base",
            label="Base / premio sticky",
            narrative=(
                "Sem crise classica, mas com premio domestico persistente "
                "e dolar ainda dominante. A decada termina mais fraca do que "
                "o benchmark estrutural puro."
            ),
            probability=0.50,
            color="gold",
            assumptions=ScenarioAssumptions(
                dxy=110.0,
                cds_shock_bps=0.0,
                carry_pct=4.5,
                commodity_shock_pct=0.0,
                productivity_gap_pct=0.5,
            ),
        ),
        ScenarioDefinition(
            scenario_key="fiscal_stress",
            label="Premio fiscal",
            narrative=(
                "CDS mais alto, credibilidade fiscal menor e banda nominal "
                "estruturalmente mais fraca ao longo da decada."
            ),
            probability=0.15,
            color="red",
            assumptions=ScenarioAssumptions(
                dxy=115.0,
                cds_shock_bps=150.0,
                carry_pct=3.0,
                commodity_shock_pct=-10.0,
                productivity_gap_pct=1.0,
            ),
        ),
        ScenarioDefinition(
            scenario_key="superdollar",
            label="Super-dolar / EUA excepcional",
            narrative=(
                "Dolar global em regime alto e produtividade americana "
                "persistentemente superior. E a principal cauda de longo "
                "prazo para o BRL."
            ),
            probability=0.10,
            color="orange",
            assumptions=ScenarioAssumptions(
                dxy=130.0,
                cds_shock_bps=100.0,
                carry_pct=2.0,
                commodity_shock_pct=-15.0,
                productivity_gap_pct=3.0,
            ),
        ),
    ]


# ---------------------------------------------------------------------------
# Computation
# ---------------------------------------------------------------------------

def compute_fair_value(
    anchor: float,
    assumptions: ScenarioAssumptions,
    horizon_years: int,
) -> HorizonPoint:
    """Compute fair BRL/USD value for a single scenario at one horizon.

    Formula::

        fair = anchor
             × (DXY / 100) ^ beta_dxy
             × exp(beta_cds × cds_shock_bps)
             × exp(beta_carry × carry_pct)
             × exp(beta_comm × commodity_shock_pct)
             × exp(beta_prod × productivity_gap_pct)
    """
    betas = HORIZON_BETAS.get(horizon_years)
    if betas is None:
        # Interpolate or use nearest.
        nearest = min(HORIZON_BETAS.keys(), key=lambda h: abs(h - horizon_years))
        betas = HORIZON_BETAS[nearest]

    dxy_factor = (assumptions.dxy / 100.0) ** betas["beta_dxy"]
    cds_factor = math.exp(betas["beta_cds"] * assumptions.cds_shock_bps)
    carry_factor = math.exp(betas["beta_carry"] * assumptions.carry_pct)
    comm_factor = math.exp(betas["beta_comm"] * assumptions.commodity_shock_pct)
    prod_factor = math.exp(betas["beta_prod"] * assumptions.productivity_gap_pct)

    fair = anchor * dxy_factor * cds_factor * carry_factor * comm_factor * prod_factor

    contributions = {
        "anchor": anchor,
        "dxy_factor": round(dxy_factor, 6),
        "cds_factor": round(cds_factor, 6),
        "carry_factor": round(carry_factor, 6),
        "commodity_factor": round(comm_factor, 6),
        "productivity_factor": round(prod_factor, 6),
    }

    return HorizonPoint(
        horizon_years=horizon_years,
        fair_value=round(fair, 4),
        betas_used=dict(betas),
        driver_contributions=contributions,
    )


def compute_scenario_paths(
    anchor: float,
    scenarios: list[ScenarioDefinition] | None = None,
    *,
    spot_value: float,
    reference_date: str,
    anchor_source: str = "reer_broad_median",
    horizons: list[int] | None = None,
) -> ScenarioSetResult:
    """Compute full scenario set with paths, expected path, and fan chart.

    Parameters
    ----------
    anchor
        REER-derived fair value anchor (e.g. the REER broad median in BRL/USD).
    scenarios
        List of scenario definitions. Defaults to ``default_scenario_definitions()``.
    spot_value
        Current PTAX spot for reference.
    reference_date
        ISO date string for the scenario computation date.
    anchor_source
        Label describing where the anchor comes from.
    horizons
        List of horizon years. Defaults to ``HORIZONS``.
    """
    if scenarios is None:
        scenarios = default_scenario_definitions()
    if horizons is None:
        horizons = list(HORIZONS)

    # Validate probabilities sum to ~1.
    prob_sum = sum(s.probability for s in scenarios)
    if abs(prob_sum - 1.0) > 0.05:
        raise ValueError(
            f"Scenario probabilities sum to {prob_sum:.3f}, expected ~1.0"
        )

    results: list[ScenarioResult] = []
    for scenario in scenarios:
        horizon_points = [
            compute_fair_value(anchor, scenario.assumptions, h)
            for h in horizons
        ]
        results.append(ScenarioResult(
            scenario_key=scenario.scenario_key,
            label=scenario.label,
            narrative=scenario.narrative,
            probability=scenario.probability,
            color=scenario.color,
            assumptions={
                "dxy": scenario.assumptions.dxy,
                "cds_shock_bps": scenario.assumptions.cds_shock_bps,
                "carry_pct": scenario.assumptions.carry_pct,
                "commodity_shock_pct": scenario.assumptions.commodity_shock_pct,
                "productivity_gap_pct": scenario.assumptions.productivity_gap_pct,
            },
            horizons=horizon_points,
        ))

    # Expected path: probability-weighted average at each horizon.
    expected_path: list[dict[str, Any]] = []
    for i, h in enumerate(horizons):
        weighted_fair = sum(
            r.probability * r.horizons[i].fair_value for r in results
        )
        expected_path.append({
            "horizon_years": h,
            "expected_fair_value": round(weighted_fair, 4),
        })

    # Fan chart: at each horizon, min/max/expected across scenarios.
    fan_chart: list[dict[str, Any]] = []
    for i, h in enumerate(horizons):
        values = [r.horizons[i].fair_value for r in results]
        fan_chart.append({
            "horizon_years": h,
            "min": round(min(values), 4),
            "max": round(max(values), 4),
            "expected": expected_path[i]["expected_fair_value"],
            "p25": round(sorted(values)[0], 4),   # benign
            "p75": round(sorted(values)[-2], 4),   # fiscal stress
            "scenarios": {
                r.scenario_key: r.horizons[i].fair_value for r in results
            },
        })

    return ScenarioSetResult(
        methodology_version=SCENARIO_METHODOLOGY_VERSION,
        anchor_value=round(anchor, 4),
        anchor_source=anchor_source,
        reference_date=reference_date,
        spot_value=round(spot_value, 4),
        scenarios=results,
        expected_path=expected_path,
        fan_chart=fan_chart,
    )


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

def scenario_set_to_dict(result: ScenarioSetResult) -> dict[str, Any]:
    """Serialize a full scenario set to a JSON-safe dict for snapshot storage."""
    return {
        "methodology_version": result.methodology_version,
        "anchor_value": result.anchor_value,
        "anchor_source": result.anchor_source,
        "reference_date": result.reference_date,
        "spot_value": result.spot_value,
        "scenario_count": len(result.scenarios),
        "horizons": HORIZONS,
        "horizon_betas": {
            str(k): v for k, v in HORIZON_BETAS.items()
        },
        "scenarios": [
            {
                "scenario_key": s.scenario_key,
                "label": s.label,
                "narrative": s.narrative,
                "probability": s.probability,
                "color": s.color,
                "assumptions": s.assumptions,
                "horizons": [
                    {
                        "horizon_years": hp.horizon_years,
                        "fair_value": hp.fair_value,
                        "betas_used": hp.betas_used,
                        "driver_contributions": hp.driver_contributions,
                    }
                    for hp in s.horizons
                ],
            }
            for s in result.scenarios
        ],
        "expected_path": result.expected_path,
        "fan_chart": result.fan_chart,
    }
