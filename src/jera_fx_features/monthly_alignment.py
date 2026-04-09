from __future__ import annotations

from datetime import date

import pandas as pd


def to_reference_month_end(value: date | pd.Timestamp | str) -> date:
    timestamp = pd.Timestamp(value)
    return timestamp.to_period("M").to_timestamp("M").date()


def assert_month_end(value: date | pd.Timestamp | str) -> None:
    timestamp = pd.Timestamp(value)
    expected = timestamp.to_period("M").to_timestamp("M")
    if timestamp.normalize() != expected.normalize():
        raise ValueError(f"Expected month-end timestamp, received {timestamp.date().isoformat()}")


def align_monthly_frame(frame: pd.DataFrame, date_column: str) -> pd.DataFrame:
    aligned = frame.copy()
    aligned["reference_month_end"] = aligned[date_column].map(to_reference_month_end)
    return aligned

