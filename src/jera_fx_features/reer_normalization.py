from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


CANONICAL_SCALE_POLICY = "canonical-2020avg100"
RAW_SCALE_POLICY = "source-native"


@dataclass(frozen=True)
class ReerNormalizationResult:
    scale_factor: float
    anchor_year: int
    normalized: pd.Series


def normalize_reer_to_2020_average_100(series: pd.Series, anchor_year: int = 2020) -> ReerNormalizationResult:
    if series.empty:
        raise ValueError("REER series is empty")
    anchor_slice = series[series.index.year == anchor_year]
    if anchor_slice.empty:
        raise ValueError(f"REER series does not contain anchor year {anchor_year}")
    anchor_mean = float(anchor_slice.mean())
    if anchor_mean == 0:
        raise ValueError("Anchor-year mean is zero; cannot normalize")
    scale_factor = 100.0 / anchor_mean
    normalized = series.astype(float) * scale_factor
    normalized.name = series.name
    return ReerNormalizationResult(
        scale_factor=scale_factor,
        anchor_year=anchor_year,
        normalized=normalized,
    )


def percentile_rank(series: pd.Series, current_value: float) -> float:
    return float(series.rank(pct=True).loc[series[series == current_value].index[-1]] * 100.0) if current_value in set(series.tolist()) else float((series <= current_value).mean() * 100.0)

