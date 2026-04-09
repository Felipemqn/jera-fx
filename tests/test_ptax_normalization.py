from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from jera_fx_api.db.models import FeatureValue, Observation
from jera_fx_api.services import seed_series_catalog
from jera_fx_connectors.bcb_ptax import PTAX_MONTHLY_FEATURE_SET_KEY, backfill_ptax, normalize_ptax_payload
from jera_fx_features.monthly_alignment import to_reference_month_end
from tests.conftest import sample_ptax_records


def test_normalize_ptax_payload_maps_to_reference_month_end() -> None:
    normalized = normalize_ptax_payload(sample_ptax_records())
    assert normalized[0]["observation_date"].isoformat() == "2026-01-29"
    assert normalized[0]["reference_month_end"] == to_reference_month_end(date(2026, 1, 29))
    assert normalized[-1]["reference_month_end"].isoformat() == "2026-02-28"


def test_backfill_ptax_builds_raw_and_monthly_close_features(
    session: Session,
    catalog,
) -> None:
    seed_series_catalog(session, catalog)
    backfill_ptax(
        session,
        catalog,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 2, 28),
        records=sample_ptax_records(),
    )

    raw_sell = session.execute(
        select(Observation)
        .where(Observation.series_key == "ptax_usd_brl_sell")
        .order_by(Observation.observation_date.asc())
    ).scalars().all()
    monthly_sell = session.execute(
        select(FeatureValue)
        .where(
            FeatureValue.feature_set_key == PTAX_MONTHLY_FEATURE_SET_KEY,
            FeatureValue.series_key == "ptax_usd_brl_sell",
        )
        .order_by(FeatureValue.reference_month_end.asc())
    ).scalars().all()

    assert len(raw_sell) == 3
    assert [row.reference_month_end.isoformat() for row in monthly_sell] == ["2026-01-31", "2026-02-28"]
    assert [row.value_numeric for row in monthly_sell] == [10.21, 10.4]
