from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from jera_fx_features.monthly_alignment import align_monthly_frame, assert_month_end, to_reference_month_end


def test_reference_month_end_normalizes_month_start_and_month_end_to_same_key() -> None:
    reer_frame = pd.DataFrame({"observation_date": [date(2026, 2, 1)], "value": [1.0]})
    ptax_frame = pd.DataFrame({"observation_date": [date(2026, 2, 28)], "value": [2.0]})

    naive_join = reer_frame.merge(ptax_frame, on="observation_date", how="inner")
    aligned_reer = align_monthly_frame(reer_frame, "observation_date")
    aligned_ptax = align_monthly_frame(ptax_frame, "observation_date")
    aligned_join = aligned_reer.merge(aligned_ptax, on="reference_month_end", how="inner")

    assert naive_join.empty
    assert aligned_join.shape[0] == 1
    assert aligned_join.iloc[0]["reference_month_end"].isoformat() == "2026-02-28"


def test_assert_month_end_rejects_month_start_timestamp() -> None:
    with pytest.raises(ValueError):
        assert_month_end(date(2026, 2, 1))


def test_to_reference_month_end_uses_month_end_convention() -> None:
    assert to_reference_month_end("2026-02-05").isoformat() == "2026-02-28"
