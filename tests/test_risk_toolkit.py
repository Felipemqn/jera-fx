"""Tests for the risk toolkit."""
from __future__ import annotations

from jera_fx_features.risk_toolkit import (
    RISK_METHODOLOGY_VERSION,
    build_regime_heatmap,
    build_risk_snapshot,
    compute_factor_sleeves,
    run_stress_tests,
)


def test_factor_sleeves_returns_all_sleeves():
    sleeves = compute_factor_sleeves(
        {"broad_usd_index": 120.0, "cds_brazil_5y": 150.0, "commodity_terms_of_trade": 100.0, "sgs_selic_target_rate": 13.75},
        anchor=5.50,
    )
    assert len(sleeves) == 4
    keys = {s["sleeve_key"] for s in sleeves}
    assert keys == {"usd_global", "risco_brasil", "commodities", "carry_juros"}
    for s in sleeves:
        assert s["beta_1y"] != 0 or s["beta_5y"] != 0


def test_stress_tests_produce_results():
    results = run_stress_tests(anchor=5.50, current_dxy=115.0)
    assert len(results) == 6
    for r in results:
        assert r["name"]
        assert len(r["horizons"]) == 2
        for h in r["horizons"]:
            assert "fair_value" in h
            assert "impact_brl" in h
            assert "impact_pct" in h


def test_dxy_shock_weakens_brl():
    results = run_stress_tests(anchor=5.50, current_dxy=115.0)
    dxy_shock = next(r for r in results if r["name"] == "DXY +10%")
    for h in dxy_shock["horizons"]:
        assert h["impact_brl"] > 0, "DXY rally should weaken BRL (increase fair value)"


def test_benign_reversal_strengthens_brl():
    results = run_stress_tests(anchor=5.50, current_dxy=115.0)
    benign = next(r for r in results if r["name"] == "Benign reversal")
    for h in benign["horizons"]:
        assert h["impact_brl"] < 0, "Benign reversal should strengthen BRL"


def test_regime_heatmap_produces_grid():
    heatmap = build_regime_heatmap(anchor=5.50)
    assert heatmap["methodology_version"] == RISK_METHODOLOGY_VERSION
    assert len(heatmap["cells"]) == len(heatmap["dxy_values"]) * len(heatmap["cds_values"])
    assert heatmap["min_fair"] < heatmap["max_fair"]


def test_full_risk_snapshot():
    snapshot = build_risk_snapshot(
        anchor=5.50,
        spot=5.30,
        driver_latest={"broad_usd_index": 120.0, "cds_brazil_5y": 150.0, "commodity_terms_of_trade": 100.0, "sgs_selic_target_rate": 13.75},
        current_dxy=120.0,
    )
    assert snapshot["methodology_version"] == RISK_METHODOLOGY_VERSION
    assert len(snapshot["factor_sleeves"]) == 4
    assert len(snapshot["stress_tests"]) == 6
    assert "regime_heatmap" in snapshot
    assert snapshot["anchor"] == 5.50
    assert snapshot["spot"] == 5.30
