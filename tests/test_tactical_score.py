"""Tests for the tactical signal score v1 methodology."""
from __future__ import annotations

from jera_fx_features.tactical_score import (
    FACTOR_WEIGHTS,
    METHODOLOGY_VERSION,
    MIN_HISTORY_POINTS,
    classify_regime,
    compute_tactical_score,
    score_result_to_dict,
)


def _make_flat_history(value: float, n: int = 24) -> list[float]:
    """Return a flat history where z-score for the last value is ~0."""
    return [value] * n


def _make_trending_history(start: float, end: float, n: int = 24) -> list[float]:
    step = (end - start) / (n - 1)
    return [start + i * step for i in range(n)]


def test_score_weights_sum_to_one() -> None:
    assert abs(sum(FACTOR_WEIGHTS.values()) - 1.0) < 1e-9


def test_flat_histories_produce_neutral_score() -> None:
    """When every driver has flat history and latest == mean, score should be ~0."""
    histories = {
        "reer_120_br": _make_flat_history(100.0),
        "reer_51_br": _make_flat_history(95.0),
        "broad_usd_index": _make_flat_history(120.0),
        "cds_brazil_5y": _make_flat_history(150.0),
        "commodity_terms_of_trade": _make_flat_history(100.0),
        "sgs_selic_target_rate": _make_flat_history(13.75),
    }
    latest = {k: v[-1] for k, v in histories.items()}
    result = compute_tactical_score(
        histories,
        latest,
        focus_exchange_values=_make_flat_history(5.5),
        focus_exchange_latest=5.5,
    )
    assert result.status == "scored"
    assert result.score is not None
    assert abs(result.score) < 1.0, f"expected near-zero score, got {result.score}"
    assert result.regime == "neutral"
    assert result.methodology_version == METHODOLOGY_VERSION


def test_all_drivers_at_high_z_produce_adverse_score() -> None:
    """Push all drivers to high z-score (including inverted sign logic)."""
    n = 24
    histories = {
        "reer_120_br": _make_flat_history(100.0, n),
        "reer_51_br": _make_flat_history(95.0, n),
        "broad_usd_index": _make_flat_history(120.0, n),
        "cds_brazil_5y": _make_flat_history(150.0, n),
        "commodity_terms_of_trade": _make_flat_history(100.0, n),
        "sgs_selic_target_rate": _make_flat_history(13.75, n),
    }
    # Make histories have variance so z-scores are meaningful
    for key in histories:
        histories[key] = _make_trending_history(
            histories[key][0] - 10.0, histories[key][0], n
        )

    # Latest values that stress BRL:
    latest = {
        "reer_120_br": 115.0,        # high REER = BRL expensive
        "reer_51_br": 108.0,         # high narrow REER
        "broad_usd_index": 135.0,    # strong USD
        "cds_brazil_5y": 200.0,      # high risk
        "commodity_terms_of_trade": 75.0,  # INVERTED: low commodity = bad for BRL
        "sgs_selic_target_rate": 8.0,     # INVERTED: low Selic = no flow support
    }
    result = compute_tactical_score(
        histories,
        latest,
        focus_exchange_values=_make_trending_history(5.0, 5.5, n),
        focus_exchange_latest=7.0,  # expected depreciation
    )
    assert result.status == "scored"
    assert result.score is not None
    assert result.score > 10.0, f"expected adverse score, got {result.score}"


def test_degraded_when_insufficient_history() -> None:
    short = [100.0] * (MIN_HISTORY_POINTS - 1)
    histories = {
        "reer_120_br": short,
        "reer_51_br": _make_flat_history(95.0),
        "broad_usd_index": _make_flat_history(120.0),
        "cds_brazil_5y": _make_flat_history(150.0),
        "commodity_terms_of_trade": _make_flat_history(100.0),
        "sgs_selic_target_rate": _make_flat_history(13.75),
    }
    latest = {
        "reer_120_br": 100.0,
        "reer_51_br": 95.0,
        "broad_usd_index": 120.0,
        "cds_brazil_5y": 150.0,
        "commodity_terms_of_trade": 100.0,
        "sgs_selic_target_rate": 13.75,
    }
    result = compute_tactical_score(
        histories,
        latest,
        focus_exchange_values=_make_flat_history(5.5),
        focus_exchange_latest=5.5,
    )
    assert result.status == "degraded"
    assert result.score is None
    assert result.regime is None
    assert any("reer_120_br" in r for r in result.degraded_reasons)


def test_degraded_when_driver_missing() -> None:
    histories = {
        "reer_120_br": _make_flat_history(100.0),
        # reer_51_br missing entirely
        "broad_usd_index": _make_flat_history(120.0),
        "cds_brazil_5y": _make_flat_history(150.0),
        "commodity_terms_of_trade": _make_flat_history(100.0),
        "sgs_selic_target_rate": _make_flat_history(13.75),
    }
    latest = {k: v[-1] for k, v in histories.items()}
    result = compute_tactical_score(
        histories,
        latest,
        focus_exchange_values=_make_flat_history(5.5),
        focus_exchange_latest=5.5,
    )
    assert result.status == "degraded"
    assert result.score is None
    assert "reer_51_br" in result.coverage["missing"]


def test_classify_regime_thresholds() -> None:
    assert classify_regime(-50.0) == "brl-favorable"
    assert classify_regime(-30.0) == "brl-favorable"
    assert classify_regime(-20.0) == "mildly-brl-favorable"
    assert classify_regime(-10.0) == "mildly-brl-favorable"
    assert classify_regime(0.0) == "neutral"
    assert classify_regime(10.0) == "neutral"
    assert classify_regime(20.0) == "mildly-brl-adverse"
    assert classify_regime(30.0) == "mildly-brl-adverse"
    assert classify_regime(50.0) == "brl-adverse"


def test_score_result_serialization() -> None:
    histories = {
        "reer_120_br": _make_flat_history(100.0),
        "reer_51_br": _make_flat_history(95.0),
        "broad_usd_index": _make_flat_history(120.0),
        "cds_brazil_5y": _make_flat_history(150.0),
        "commodity_terms_of_trade": _make_flat_history(100.0),
        "sgs_selic_target_rate": _make_flat_history(13.75),
    }
    latest = {k: v[-1] for k, v in histories.items()}
    result = compute_tactical_score(
        histories,
        latest,
        focus_exchange_values=_make_flat_history(5.5),
        focus_exchange_latest=5.5,
    )
    d = score_result_to_dict(result)
    assert d["methodology_version"] == METHODOLOGY_VERSION
    assert "weights" in d["methodology"]
    assert isinstance(d["driver_contributions"], list)
    assert len(d["driver_contributions"]) == len(FACTOR_WEIGHTS)


def test_integration_build_tactical_signal_with_score(cds_ready_session, catalog) -> None:
    """Full integration: build the signal snapshot and verify score is present."""
    from jera_fx_features.tactical_signal import build_tactical_signal_snapshot

    payload = build_tactical_signal_snapshot(cds_ready_session, catalog)

    # With test fixtures the history is very short (3 months at most)
    # so score will be degraded, which is correct behavior.
    assert payload["methodology"]["version"] in (
        METHODOLOGY_VERSION,
        "tactical-signal-foundation-v1",
    )
    # Score should be None (degraded) or a number — never missing from payload.
    assert "score" in payload
    assert "regime" in payload
    assert "driver_contributions" in payload
    assert "coverage" in payload
    assert "degraded_reasons" in payload

    # With only 3 data points per driver, we expect degraded status.
    if payload["status"] == "degraded":
        assert payload["score"] is None
        assert len(payload["degraded_reasons"]) > 0
    elif payload["status"] == "scored":
        assert isinstance(payload["score"], (int, float))
        assert payload["regime"] is not None
