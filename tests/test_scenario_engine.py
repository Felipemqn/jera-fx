"""Tests for the scenario engine v1."""
from __future__ import annotations

import math

from jera_fx_features.scenario_engine import (
    HORIZONS,
    HORIZON_BETAS,
    SCENARIO_METHODOLOGY_VERSION,
    ScenarioAssumptions,
    ScenarioDefinition,
    compute_fair_value,
    compute_scenario_paths,
    default_scenario_definitions,
    scenario_set_to_dict,
)


def test_default_scenarios_probabilities_sum_to_one() -> None:
    scenarios = default_scenario_definitions()
    total = sum(s.probability for s in scenarios)
    assert abs(total - 1.0) < 1e-9


def test_default_scenarios_have_all_required_fields() -> None:
    for s in default_scenario_definitions():
        assert s.scenario_key
        assert s.label
        assert s.narrative
        assert 0.0 < s.probability <= 1.0
        assert s.color
        assert isinstance(s.assumptions, ScenarioAssumptions)


def test_neutral_assumptions_produce_near_anchor() -> None:
    """When all shocks are zero and DXY=100, fair ≈ anchor."""
    anchor = 5.50
    neutral = ScenarioAssumptions(
        dxy=100.0,
        cds_shock_bps=0.0,
        carry_pct=0.0,
        commodity_shock_pct=0.0,
        productivity_gap_pct=0.0,
    )
    for h in HORIZONS:
        hp = compute_fair_value(anchor, neutral, h)
        assert abs(hp.fair_value - anchor) < 0.01, (
            f"At {h}Y horizon, expected ~{anchor}, got {hp.fair_value}"
        )


def test_high_dxy_raises_fair_value() -> None:
    anchor = 5.50
    neutral = ScenarioAssumptions(
        dxy=100.0, cds_shock_bps=0.0, carry_pct=0.0,
        commodity_shock_pct=0.0, productivity_gap_pct=0.0,
    )
    strong_usd = ScenarioAssumptions(
        dxy=130.0, cds_shock_bps=0.0, carry_pct=0.0,
        commodity_shock_pct=0.0, productivity_gap_pct=0.0,
    )
    for h in HORIZONS:
        neutral_hp = compute_fair_value(anchor, neutral, h)
        strong_hp = compute_fair_value(anchor, strong_usd, h)
        assert strong_hp.fair_value > neutral_hp.fair_value, (
            f"At {h}Y, strong USD should raise BRL/USD"
        )


def test_high_cds_raises_fair_value() -> None:
    anchor = 5.50
    calm = ScenarioAssumptions(
        dxy=110.0, cds_shock_bps=0.0, carry_pct=0.0,
        commodity_shock_pct=0.0, productivity_gap_pct=0.0,
    )
    stress = ScenarioAssumptions(
        dxy=110.0, cds_shock_bps=200.0, carry_pct=0.0,
        commodity_shock_pct=0.0, productivity_gap_pct=0.0,
    )
    for h in HORIZONS:
        calm_hp = compute_fair_value(anchor, calm, h)
        stress_hp = compute_fair_value(anchor, stress, h)
        assert stress_hp.fair_value > calm_hp.fair_value


def test_high_carry_lowers_fair_value() -> None:
    anchor = 5.50
    low_carry = ScenarioAssumptions(
        dxy=110.0, cds_shock_bps=0.0, carry_pct=0.0,
        commodity_shock_pct=0.0, productivity_gap_pct=0.0,
    )
    high_carry = ScenarioAssumptions(
        dxy=110.0, cds_shock_bps=0.0, carry_pct=8.0,
        commodity_shock_pct=0.0, productivity_gap_pct=0.0,
    )
    for h in HORIZONS:
        low_hp = compute_fair_value(anchor, low_carry, h)
        high_hp = compute_fair_value(anchor, high_carry, h)
        assert high_hp.fair_value < low_hp.fair_value, (
            f"At {h}Y, high carry should strengthen BRL (lower fair value)"
        )


def test_high_commodity_lowers_fair_value() -> None:
    anchor = 5.50
    neutral = ScenarioAssumptions(
        dxy=110.0, cds_shock_bps=0.0, carry_pct=0.0,
        commodity_shock_pct=0.0, productivity_gap_pct=0.0,
    )
    commodity_boom = ScenarioAssumptions(
        dxy=110.0, cds_shock_bps=0.0, carry_pct=0.0,
        commodity_shock_pct=20.0, productivity_gap_pct=0.0,
    )
    for h in HORIZONS:
        neutral_hp = compute_fair_value(anchor, neutral, h)
        boom_hp = compute_fair_value(anchor, commodity_boom, h)
        assert boom_hp.fair_value < neutral_hp.fair_value


def test_compute_scenario_paths_produces_fan_chart() -> None:
    result = compute_scenario_paths(
        anchor=5.50,
        spot_value=5.30,
        reference_date="2026-04-13",
    )
    assert result.methodology_version == SCENARIO_METHODOLOGY_VERSION
    assert len(result.scenarios) == 4
    assert len(result.expected_path) == len(HORIZONS)
    assert len(result.fan_chart) == len(HORIZONS)

    # Expected path should be between min and max at each horizon.
    for fc in result.fan_chart:
        assert fc["min"] <= fc["expected"] <= fc["max"]


def test_scenario_paths_ordering() -> None:
    """Benign should produce lower (stronger BRL) values than superdollar."""
    result = compute_scenario_paths(
        anchor=5.50,
        spot_value=5.30,
        reference_date="2026-04-13",
    )
    benign = next(s for s in result.scenarios if s.scenario_key == "benign")
    superdollar = next(s for s in result.scenarios if s.scenario_key == "superdollar")

    for i, h in enumerate(HORIZONS):
        assert benign.horizons[i].fair_value < superdollar.horizons[i].fair_value, (
            f"At {h}Y, benign should produce lower BRL/USD than superdollar"
        )


def test_serialization_round_trip() -> None:
    result = compute_scenario_paths(
        anchor=5.50,
        spot_value=5.30,
        reference_date="2026-04-13",
    )
    d = scenario_set_to_dict(result)
    assert d["methodology_version"] == SCENARIO_METHODOLOGY_VERSION
    assert d["scenario_count"] == 4
    assert len(d["scenarios"]) == 4
    assert len(d["expected_path"]) == len(HORIZONS)
    assert len(d["fan_chart"]) == len(HORIZONS)
    # All values should be JSON-serializable (no special types).
    import json
    json.dumps(d)  # should not raise


def test_integration_build_scenario_set_snapshot(overview_ready_session, catalog) -> None:
    """Integration: build scenario snapshot from curated data."""
    from jera_fx_features.scenario_builder import build_scenario_set_snapshot

    payload = build_scenario_set_snapshot(overview_ready_session)

    assert payload["snapshot_type"] == "scenario_set"
    assert payload["methodology_version"] == SCENARIO_METHODOLOGY_VERSION
    assert payload["scenario_count"] == 4
    assert len(payload["scenarios"]) == 4
    assert len(payload["expected_path"]) == len(HORIZONS)
    assert len(payload["fan_chart"]) == len(HORIZONS)
    assert payload["anchor_value"] > 0
    assert payload["spot_value"] > 0
