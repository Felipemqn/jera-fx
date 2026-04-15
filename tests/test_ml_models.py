"""Tests for ML research models."""
from __future__ import annotations

import numpy as np

from jera_fx_features.ml_models import (
    ML_METHODOLOGY_VERSION,
    build_model_registry,
    walk_forward_backtest,
)


def _make_linear_data(n: int = 60, k: int = 5):
    rng = np.random.RandomState(42)
    X = rng.randn(n, k)
    true_betas = np.array([0.5, -0.3, 0.2, -0.1, 0.4])[:k]
    y = X @ true_betas + 3.0 + rng.randn(n) * 0.1
    dates = [f"2024-{i//12+1:02d}-28" for i in range(n)]
    drivers = [f"driver_{j}" for j in range(k)]
    return X, y, dates, drivers


def test_ridge_backtest_produces_valid_metrics():
    X, y, dates, _ = _make_linear_data()
    result = walk_forward_backtest(X, y, dates, model="ridge", min_train=24)
    assert result.n_test_steps > 0
    assert result.rmse > 0
    assert result.mae > 0
    assert -1.0 <= result.r_squared_oos <= 1.0
    assert len(result.predictions) == result.n_test_steps


def test_gbm_backtest_produces_valid_metrics():
    X, y, dates, _ = _make_linear_data()
    result = walk_forward_backtest(X, y, dates, model="gbm", min_train=24)
    assert result.n_test_steps > 0
    assert result.rmse > 0


def test_model_registry_produces_two_models():
    X, y, dates, drivers = _make_linear_data()
    entries = build_model_registry(X, y, dates, drivers, min_train=24)
    assert len(entries) == 2
    names = {e["model_name"] for e in entries}
    assert names == {"ridge", "gbm"}
    for e in entries:
        assert e["methodology_version"] == ML_METHODOLOGY_VERSION
        assert e["status"] == "research"
        assert e["approval_state"] == "not-approved"
        assert "backtest" in e


def test_model_registry_with_short_data():
    X, y, dates, drivers = _make_linear_data(n=10)
    entries = build_model_registry(X, y, dates, drivers, min_train=8)
    assert len(entries) == 2
    # Should still produce results, even if metrics are poor
    for e in entries:
        assert e["backtest"]["n_test_steps"] >= 0


def test_ridge_backtest_on_linear_data_has_positive_r2():
    """Ridge should perform well on linear data."""
    X, y, dates, _ = _make_linear_data(n=80)
    result = walk_forward_backtest(X, y, dates, model="ridge", min_train=30)
    assert result.r_squared_oos > 0.5, f"Expected good R² on linear data, got {result.r_squared_oos}"
