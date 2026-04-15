"""Rolling regression engine for the investment mode.

Computes rolling OLS regressions of BRL/USD (PTAX monthly close) against
tactical drivers over configurable windows (3Y, 2Y, 1Y, quarter).

Each window produces:
- coefficients (betas) per driver
- R-squared (explanatory power)
- factor contributions (beta × delta driver) explaining the recent BRL move
- residual (unexplained portion)

All computation uses curated monthly data from the tactical driver history
snapshot — no raw data access, no external calls.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

REGRESSION_METHODOLOGY_VERSION = "rolling-regression-v1"

#: Standard windows in months.
WINDOWS: dict[str, int] = {
    "3Y": 36,
    "2Y": 24,
    "1Y": 12,
    "Q": 3,
}

#: Drivers used as independent variables.
#: Must match driver_keys in the tactical driver history snapshot.
REGRESSION_DRIVERS: list[str] = [
    "reer_120_br",
    "broad_usd_index",
    "cds_brazil_5y",
    "commodity_terms_of_trade",
    "sgs_selic_target_rate",
]

#: Dependent variable.
DEPENDENT_VARIABLE = "ptax_usd_brl_sell"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class WindowResult:
    window_label: str
    window_months: int
    n_obs: int
    r_squared: float
    adj_r_squared: float
    coefficients: dict[str, float]
    intercept: float
    factor_contributions: list[dict[str, Any]]
    residual: float
    dependent_latest: float
    dependent_first: float
    total_move: float


@dataclass
class RollingRegressionResult:
    methodology_version: str
    dependent_variable: str
    driver_keys: list[str]
    windows: list[WindowResult]


# ---------------------------------------------------------------------------
# OLS computation (no sklearn dependency — pure numpy)
# ---------------------------------------------------------------------------

def _ols(X: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, float, float, float]:
    """Ordinary least squares via normal equation.

    Returns (betas_with_intercept, r_squared, adj_r_squared, intercept).
    """
    n, k = X.shape
    X_aug = np.column_stack([np.ones(n), X])
    try:
        betas = np.linalg.lstsq(X_aug, y, rcond=None)[0]
    except np.linalg.LinAlgError:
        betas = np.zeros(k + 1)

    y_hat = X_aug @ betas
    ss_res = float(np.sum((y - y_hat) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    r_sq = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    adj_r_sq = 1.0 - (1.0 - r_sq) * (n - 1) / max(n - k - 1, 1) if n > k + 1 else r_sq

    return betas, r_sq, adj_r_sq, float(betas[0])


# ---------------------------------------------------------------------------
# Main computation
# ---------------------------------------------------------------------------

def compute_rolling_regressions(
    dependent_values: list[float],
    driver_histories: dict[str, list[float]],
    *,
    windows: dict[str, int] | None = None,
    driver_keys: list[str] | None = None,
) -> RollingRegressionResult:
    """Compute rolling regressions for all windows.

    Parameters
    ----------
    dependent_values
        Monthly values of the dependent variable (ascending).
    driver_histories
        ``{driver_key: [monthly_values_ascending]}`` for each driver.
    windows
        ``{label: months}`` windows. Defaults to ``WINDOWS``.
    driver_keys
        Ordered list of drivers to use. Defaults to ``REGRESSION_DRIVERS``.
    """
    if windows is None:
        windows = dict(WINDOWS)
    if driver_keys is None:
        driver_keys = list(REGRESSION_DRIVERS)

    results: list[WindowResult] = []

    for label, months in windows.items():
        # Trim all series to the window length.
        n = min(months, len(dependent_values))
        for dk in driver_keys:
            n = min(n, len(driver_histories.get(dk, [])))

        if n < max(len(driver_keys) + 2, 4):
            # Not enough observations for regression.
            results.append(WindowResult(
                window_label=label,
                window_months=months,
                n_obs=n,
                r_squared=0.0,
                adj_r_squared=0.0,
                coefficients={dk: 0.0 for dk in driver_keys},
                intercept=0.0,
                factor_contributions=[],
                residual=0.0,
                dependent_latest=dependent_values[-1] if dependent_values else 0.0,
                dependent_first=dependent_values[-n] if n > 0 and dependent_values else 0.0,
                total_move=0.0,
            ))
            continue

        y = np.array(dependent_values[-n:])
        X = np.column_stack([
            np.array(driver_histories[dk][-n:])
            for dk in driver_keys
        ])

        betas, r_sq, adj_r_sq, intercept = _ols(X, y)
        coefficients = {dk: round(float(betas[i + 1]), 6) for i, dk in enumerate(driver_keys)}

        # Factor contributions: beta_k × (driver_latest - driver_first)
        contributions: list[dict[str, Any]] = []
        explained_sum = 0.0
        for i, dk in enumerate(driver_keys):
            driver_vals = driver_histories[dk][-n:]
            delta_driver = driver_vals[-1] - driver_vals[0]
            beta_k = float(betas[i + 1])
            contribution = beta_k * delta_driver
            explained_sum += contribution
            contributions.append({
                "driver_key": dk,
                "beta": round(beta_k, 6),
                "delta_driver": round(delta_driver, 4),
                "contribution": round(contribution, 4),
            })

        total_move = float(y[-1] - y[0])
        residual = total_move - explained_sum

        results.append(WindowResult(
            window_label=label,
            window_months=months,
            n_obs=n,
            r_squared=round(r_sq, 4),
            adj_r_squared=round(adj_r_sq, 4),
            coefficients=coefficients,
            intercept=round(intercept, 6),
            factor_contributions=contributions,
            residual=round(residual, 4),
            dependent_latest=round(float(y[-1]), 4),
            dependent_first=round(float(y[0]), 4),
            total_move=round(total_move, 4),
        ))

    return RollingRegressionResult(
        methodology_version=REGRESSION_METHODOLOGY_VERSION,
        dependent_variable=DEPENDENT_VARIABLE,
        driver_keys=driver_keys,
        windows=results,
    )


def regression_result_to_dict(result: RollingRegressionResult) -> dict[str, Any]:
    """Serialize to JSON-safe dict."""
    return {
        "methodology_version": result.methodology_version,
        "dependent_variable": result.dependent_variable,
        "driver_keys": result.driver_keys,
        "windows": [
            {
                "window_label": w.window_label,
                "window_months": w.window_months,
                "n_obs": w.n_obs,
                "r_squared": w.r_squared,
                "adj_r_squared": w.adj_r_squared,
                "coefficients": w.coefficients,
                "intercept": w.intercept,
                "factor_contributions": w.factor_contributions,
                "residual": w.residual,
                "dependent_latest": w.dependent_latest,
                "dependent_first": w.dependent_first,
                "total_move": w.total_move,
            }
            for w in result.windows
        ],
    }
