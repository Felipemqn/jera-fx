"""Tactical signal score v1 — deterministic factor z-score methodology.

This module owns the entire computation of the tactical signal score.
It is invoked by the snapshot builder (``build_tactical_signal_snapshot``)
and NEVER by the API layer directly.

Methodology version: ``tactical-signal-score-v1``

Design principles
-----------------
* Transparent — every weight, threshold, and z-score window is a named
  constant exported in ``METHODOLOGY_V1``.
* Deterministic — given the same curated driver history, the score is
  always identical. No random state.
* Governed — the API response always includes ``methodology_version``,
  ``weights``, ``regime``, ``driver_contributions``, and ``coverage``.
* Fail-safe — if any ``required_for_signal`` driver lacks sufficient
  history, the score is ``None`` and the status is ``degraded``.

Score semantics
---------------
* Range: -100 to +100.
* Negative = BRL looks *cheap* (favorable for long BRL / short USD).
* Positive = BRL looks *expensive* or under stress (adverse for BRL).
* Zero = neutral reading across factors.

Regime labels
-------------
* ``brl-favorable``:         score <= -30
* ``mildly-brl-favorable``:  -30 < score <= -10
* ``neutral``:               -10 < score <=  10
* ``mildly-brl-adverse``:     10 < score <=  30
* ``brl-adverse``:            score >  30
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


# ---------------------------------------------------------------------------
# Methodology definition — v1 constants
# ---------------------------------------------------------------------------

METHODOLOGY_VERSION = "tactical-signal-score-v1"

#: Minimum number of monthly observations required to compute a z-score.
MIN_HISTORY_POINTS = 12

#: Factor weights (must sum to 1.0).
#: Sign convention per driver:
#:   positive weight + z > 0 → pushes score toward BRL-adverse
#:   REER: high REER = BRL expensive → positive contribution
#:   DXY:  high DXY  = USD strong   → positive contribution
#:   CDS:  high CDS  = risk up      → positive contribution
#:   Commodity: high commodity = BRL supportive → NEGATIVE contribution (inverted sign)
#:   Selic: high Selic = attracting flows → NEGATIVE contribution (inverted sign)
#:   Focus FX: high Focus FX median = expected depreciation → positive contribution
FACTOR_WEIGHTS: dict[str, float] = {
    "reer_120_br": 0.20,
    "reer_51_br": 0.10,
    "broad_usd_index": 0.20,
    "cds_brazil_5y": 0.15,
    "commodity_terms_of_trade": 0.15,
    "sgs_selic_target_rate": 0.10,
    "focus_exchange_rate": 0.10,
}

#: Drivers where higher value is BRL-supportive (z-score sign is inverted).
INVERTED_DRIVERS: frozenset[str] = frozenset({
    "commodity_terms_of_trade",
    "sgs_selic_target_rate",
})

#: Regime thresholds — tuples of (upper_bound_exclusive, label).
REGIME_THRESHOLDS: list[tuple[float, str]] = [
    (-30.0, "brl-favorable"),
    (-10.0, "mildly-brl-favorable"),
    (10.0, "neutral"),
    (30.0, "mildly-brl-adverse"),
]
REGIME_FALLBACK = "brl-adverse"

#: Score is clamped to this range.
SCORE_MIN = -100.0
SCORE_MAX = 100.0


def _methodology_dict() -> dict[str, Any]:
    """Return the full methodology definition as a serializable dict."""
    return {
        "version": METHODOLOGY_VERSION,
        "score_range": [SCORE_MIN, SCORE_MAX],
        "min_history_points": MIN_HISTORY_POINTS,
        "weights": dict(FACTOR_WEIGHTS),
        "inverted_drivers": sorted(INVERTED_DRIVERS),
        "regime_thresholds": [
            {"upper_bound_exclusive": t, "label": l}
            for t, l in REGIME_THRESHOLDS
        ] + [{"upper_bound_exclusive": None, "label": REGIME_FALLBACK}],
    }


METHODOLOGY_V1 = _methodology_dict()


# ---------------------------------------------------------------------------
# Z-score helpers
# ---------------------------------------------------------------------------

def _zscore(value: float, mean: float, std: float) -> float:
    """Standard z-score, capped at +/-4 to avoid outlier explosion."""
    if std == 0.0 or std != std:  # std is zero or NaN
        return 0.0
    z = (value - mean) / std
    return max(-4.0, min(4.0, z))


# ---------------------------------------------------------------------------
# Score computation
# ---------------------------------------------------------------------------

@dataclass
class DriverContribution:
    driver_key: str
    weight: float
    z_score: float
    weighted_contribution: float
    inverted: bool
    value: float
    mean: float
    std: float
    history_points: int


@dataclass
class TacticalScoreResult:
    score: float | None
    regime: str | None
    status: str  # "scored" | "degraded"
    methodology_version: str
    driver_contributions: list[DriverContribution]
    coverage: dict[str, Any]
    degraded_reasons: list[str]
    methodology: dict[str, Any]


def classify_regime(score: float) -> str:
    """Map a numeric score to a regime label."""
    for threshold, label in REGIME_THRESHOLDS:
        if score <= threshold:
            return label
    return REGIME_FALLBACK


def compute_tactical_score(
    driver_histories: dict[str, list[float]],
    driver_latest: dict[str, float],
    *,
    focus_exchange_values: list[float] | None = None,
    focus_exchange_latest: float | None = None,
) -> TacticalScoreResult:
    """Compute the tactical signal score from curated driver data.

    Parameters
    ----------
    driver_histories
        ``{driver_key: [monthly_values_ascending]}`` for each factor
        listed in ``FACTOR_WEIGHTS`` (except ``focus_exchange_rate``).
    driver_latest
        ``{driver_key: latest_value}`` for each factor.
    focus_exchange_values
        Aggregated Focus FX median history (e.g. average of all horizon years).
    focus_exchange_latest
        Latest aggregated Focus FX median value.

    Returns
    -------
    TacticalScoreResult
        Full result with score, regime, contributions, and methodology.
    """
    contributions: list[DriverContribution] = []
    degraded_reasons: list[str] = []
    coverage: dict[str, Any] = {"available": [], "insufficient": [], "missing": []}

    # Merge focus_exchange into the standard maps for uniform processing.
    all_histories = dict(driver_histories)
    all_latest = dict(driver_latest)
    if focus_exchange_values is not None:
        all_histories["focus_exchange_rate"] = focus_exchange_values
    if focus_exchange_latest is not None:
        all_latest["focus_exchange_rate"] = focus_exchange_latest

    for driver_key, weight in FACTOR_WEIGHTS.items():
        history = all_histories.get(driver_key)
        latest = all_latest.get(driver_key)

        if history is None or latest is None or len(history) == 0:
            coverage["missing"].append(driver_key)
            degraded_reasons.append(f"{driver_key}: no data available")
            continue

        if len(history) < MIN_HISTORY_POINTS:
            coverage["insufficient"].append(driver_key)
            degraded_reasons.append(
                f"{driver_key}: only {len(history)} points "
                f"(need {MIN_HISTORY_POINTS})"
            )
            continue

        coverage["available"].append(driver_key)
        mean = sum(history) / len(history)
        variance = sum((v - mean) ** 2 for v in history) / len(history)
        std = variance ** 0.5

        raw_z = _zscore(latest, mean, std)
        inverted = driver_key in INVERTED_DRIVERS
        z = -raw_z if inverted else raw_z
        weighted = z * weight * 25.0  # scale so that z=4 at weight=1 ≈ 100

        contributions.append(DriverContribution(
            driver_key=driver_key,
            weight=weight,
            z_score=round(z, 4),
            weighted_contribution=round(weighted, 4),
            inverted=inverted,
            value=round(latest, 6),
            mean=round(mean, 6),
            std=round(std, 6),
            history_points=len(history),
        ))

    # Determine if we can score.
    if degraded_reasons:
        return TacticalScoreResult(
            score=None,
            regime=None,
            status="degraded",
            methodology_version=METHODOLOGY_VERSION,
            driver_contributions=contributions,
            coverage=coverage,
            degraded_reasons=degraded_reasons,
            methodology=METHODOLOGY_V1,
        )

    raw_score = sum(c.weighted_contribution for c in contributions)
    clamped = max(SCORE_MIN, min(SCORE_MAX, raw_score))
    regime = classify_regime(clamped)

    return TacticalScoreResult(
        score=round(clamped, 2),
        regime=regime,
        status="scored",
        methodology_version=METHODOLOGY_VERSION,
        driver_contributions=contributions,
        coverage=coverage,
        degraded_reasons=[],
        methodology=METHODOLOGY_V1,
    )


def score_result_to_dict(result: TacticalScoreResult) -> dict[str, Any]:
    """Serialize a ``TacticalScoreResult`` to a JSON-safe dict."""
    return {
        "score": result.score,
        "regime": result.regime,
        "status": result.status,
        "methodology_version": result.methodology_version,
        "methodology": result.methodology,
        "coverage": result.coverage,
        "degraded_reasons": result.degraded_reasons,
        "driver_contributions": [
            {
                "driver_key": c.driver_key,
                "weight": c.weight,
                "z_score": c.z_score,
                "weighted_contribution": c.weighted_contribution,
                "inverted": c.inverted,
                "value": c.value,
                "mean": c.mean,
                "std": c.std,
                "history_points": c.history_points,
            }
            for c in result.driver_contributions
        ],
    }
