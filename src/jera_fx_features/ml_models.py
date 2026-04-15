"""ML model layer — ridge regression and gradient boosting baselines.

Methodology version: ``ml-research-v1``

This module implements two supervised models for BRL/USD forecasting:
1. Ridge regression (linear baseline with L2 regularization)
2. Gradient-boosted trees (nonlinear benchmark)

Both models:
- Train on curated monthly driver data
- Produce out-of-sample metrics via expanding-window walk-forward
- Store coefficients/feature importance in a model registry format
- Are NOT promoted to client-facing output without explicit approval

The v1 tactical signal (deterministic z-score) remains the production
baseline. ML models exist for research comparison only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np


ML_METHODOLOGY_VERSION = "ml-research-v1"

# Ridge default alpha
RIDGE_ALPHA = 1.0

# Boosting defaults (simple gradient boosting from scratch — no sklearn dependency)
BOOST_N_TREES = 50
BOOST_LEARNING_RATE = 0.1
BOOST_MAX_DEPTH = 3
BOOST_MIN_SAMPLES_LEAF = 4


# ---------------------------------------------------------------------------
# Ridge Regression
# ---------------------------------------------------------------------------

def _ridge_fit(X: np.ndarray, y: np.ndarray, alpha: float = RIDGE_ALPHA) -> np.ndarray:
    """Ridge regression via closed-form: (X'X + αI)^-1 X'y."""
    n, k = X.shape
    X_aug = np.column_stack([np.ones(n), X])
    I = np.eye(k + 1)
    I[0, 0] = 0  # don't regularize intercept
    betas = np.linalg.solve(X_aug.T @ X_aug + alpha * I, X_aug.T @ y)
    return betas


def _ridge_predict(X: np.ndarray, betas: np.ndarray) -> np.ndarray:
    X_aug = np.column_stack([np.ones(X.shape[0]), X])
    return X_aug @ betas


# ---------------------------------------------------------------------------
# Simple Decision Stump (for gradient boosting)
# ---------------------------------------------------------------------------

def _best_split(X: np.ndarray, residuals: np.ndarray, max_depth: int, min_leaf: int) -> dict:
    """Find best split for a simple regression tree (stump or shallow tree)."""
    n = len(residuals)
    if n < 2 * min_leaf or max_depth <= 0:
        return {"leaf": True, "value": float(np.mean(residuals))}

    best_loss = np.inf
    best = None
    for j in range(X.shape[1]):
        sorted_idx = np.argsort(X[:, j])
        for i in range(min_leaf, n - min_leaf):
            left = residuals[sorted_idx[:i]]
            right = residuals[sorted_idx[i:]]
            loss = np.sum(left ** 2) + np.sum(right ** 2)
            if loss < best_loss:
                best_loss = loss
                best = {"feature": j, "threshold": float(X[sorted_idx[i], j]),
                        "left_val": float(np.mean(left)), "right_val": float(np.mean(right))}

    if best is None:
        return {"leaf": True, "value": float(np.mean(residuals))}
    return {"leaf": False, **best}


def _tree_predict_one(x: np.ndarray, tree: dict) -> float:
    if tree["leaf"]:
        return tree["value"]
    return tree["left_val"] if x[tree["feature"]] < tree["threshold"] else tree["right_val"]


def _tree_predict(X: np.ndarray, tree: dict) -> np.ndarray:
    return np.array([_tree_predict_one(X[i], tree) for i in range(X.shape[0])])


# ---------------------------------------------------------------------------
# Gradient Boosting
# ---------------------------------------------------------------------------

def _gbm_fit(X: np.ndarray, y: np.ndarray, n_trees: int = BOOST_N_TREES,
             lr: float = BOOST_LEARNING_RATE, max_depth: int = BOOST_MAX_DEPTH,
             min_leaf: int = BOOST_MIN_SAMPLES_LEAF) -> list[dict]:
    """Fit gradient boosting regressor (from scratch)."""
    trees = []
    residuals = y.copy()
    for _ in range(n_trees):
        tree = _best_split(X, residuals, max_depth, min_leaf)
        pred = _tree_predict(X, tree) * lr
        residuals = residuals - pred
        trees.append(tree)
    return trees


def _gbm_predict(X: np.ndarray, trees: list[dict], y_mean: float,
                 lr: float = BOOST_LEARNING_RATE) -> np.ndarray:
    pred = np.full(X.shape[0], y_mean)
    for tree in trees:
        pred += _tree_predict(X, tree) * lr
    return pred


# ---------------------------------------------------------------------------
# Walk-forward backtesting
# ---------------------------------------------------------------------------

@dataclass
class BacktestResult:
    model_name: str
    n_train_start: int
    n_test_steps: int
    rmse: float
    mae: float
    r_squared_oos: float
    predictions: list[dict[str, Any]]


def _metrics(y_true: np.ndarray, y_pred: np.ndarray) -> tuple[float, float, float]:
    residuals = y_true - y_pred
    rmse = float(np.sqrt(np.mean(residuals ** 2)))
    mae = float(np.mean(np.abs(residuals)))
    ss_res = float(np.sum(residuals ** 2))
    ss_tot = float(np.sum((y_true - np.mean(y_true)) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    return rmse, mae, r2


def walk_forward_backtest(
    X: np.ndarray,
    y: np.ndarray,
    dates: list[str],
    *,
    model: str = "ridge",
    min_train: int = 24,
    alpha: float = RIDGE_ALPHA,
) -> BacktestResult:
    """Expanding-window walk-forward out-of-sample backtest."""
    n = len(y)
    if n < min_train + 1:
        return BacktestResult(model_name=model, n_train_start=min_train,
                              n_test_steps=0, rmse=0, mae=0, r_squared_oos=0, predictions=[])

    actuals, preds, pred_dates = [], [], []
    for t in range(min_train, n):
        X_train, y_train = X[:t], y[:t]
        X_test = X[t:t+1]

        if model == "ridge":
            betas = _ridge_fit(X_train, y_train, alpha)
            y_hat = float(_ridge_predict(X_test, betas)[0])
        elif model == "gbm":
            y_mean = float(np.mean(y_train))
            trees = _gbm_fit(X_train, y_train - y_mean)
            y_hat = float(_gbm_predict(X_test, trees, y_mean)[0])
        else:
            raise ValueError(f"Unknown model: {model}")

        actuals.append(float(y[t]))
        preds.append(y_hat)
        pred_dates.append(dates[t] if t < len(dates) else f"t+{t}")

    actuals_arr = np.array(actuals)
    preds_arr = np.array(preds)
    rmse, mae, r2 = _metrics(actuals_arr, preds_arr)

    predictions = [
        {"date": pred_dates[i], "actual": round(actuals[i], 4), "predicted": round(preds[i], 4),
         "error": round(actuals[i] - preds[i], 4)}
        for i in range(len(actuals))
    ]

    return BacktestResult(
        model_name=model,
        n_train_start=min_train,
        n_test_steps=len(actuals),
        rmse=round(rmse, 6),
        mae=round(mae, 6),
        r_squared_oos=round(r2, 4),
        predictions=predictions,
    )


# ---------------------------------------------------------------------------
# Model Registry Entry
# ---------------------------------------------------------------------------

@dataclass
class ModelRegistryEntry:
    model_name: str
    methodology_version: str
    status: str  # "research" | "candidate" | "approved" | "retired"
    hyperparameters: dict[str, Any]
    feature_importance: dict[str, float]
    backtest: BacktestResult
    approval_state: str  # "not-approved" | "pending" | "approved"


def build_model_registry(
    X: np.ndarray,
    y: np.ndarray,
    dates: list[str],
    driver_keys: list[str],
    *,
    min_train: int = 24,
) -> list[dict[str, Any]]:
    """Train both models and return registry entries."""
    entries = []

    # Ridge
    ridge_bt = walk_forward_backtest(X, y, dates, model="ridge", min_train=min_train)
    if len(y) > min_train:
        betas = _ridge_fit(X, y)
        ridge_importance = {dk: round(abs(float(betas[i+1])), 6) for i, dk in enumerate(driver_keys)}
    else:
        ridge_importance = {dk: 0.0 for dk in driver_keys}

    entries.append({
        "model_name": "ridge",
        "methodology_version": ML_METHODOLOGY_VERSION,
        "status": "research",
        "approval_state": "not-approved",
        "hyperparameters": {"alpha": RIDGE_ALPHA},
        "feature_importance": ridge_importance,
        "backtest": {
            "n_train_start": ridge_bt.n_train_start,
            "n_test_steps": ridge_bt.n_test_steps,
            "rmse": ridge_bt.rmse,
            "mae": ridge_bt.mae,
            "r_squared_oos": ridge_bt.r_squared_oos,
            "predictions": ridge_bt.predictions,
        },
    })

    # GBM
    gbm_bt = walk_forward_backtest(X, y, dates, model="gbm", min_train=min_train)
    entries.append({
        "model_name": "gbm",
        "methodology_version": ML_METHODOLOGY_VERSION,
        "status": "research",
        "approval_state": "not-approved",
        "hyperparameters": {
            "n_trees": BOOST_N_TREES,
            "learning_rate": BOOST_LEARNING_RATE,
            "max_depth": BOOST_MAX_DEPTH,
            "min_samples_leaf": BOOST_MIN_SAMPLES_LEAF,
        },
        "feature_importance": {},  # tree importance requires more complex extraction
        "backtest": {
            "n_train_start": gbm_bt.n_train_start,
            "n_test_steps": gbm_bt.n_test_steps,
            "rmse": gbm_bt.rmse,
            "mae": gbm_bt.mae,
            "r_squared_oos": gbm_bt.r_squared_oos,
            "predictions": gbm_bt.predictions,
        },
    })

    return entries
