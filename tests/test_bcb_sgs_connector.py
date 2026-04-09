from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from jera_fx_api.db.models import Observation
from jera_fx_api.services import seed_series_catalog
from jera_fx_connectors.bcb_sgs import backfill_sgs, normalize_sgs_payload
from tests.conftest import sample_sgs_commodity_records, sample_sgs_ipca_records, sample_sgs_selic_records


def test_normalize_sgs_payload_keeps_month_end_join_key_for_daily_and_monthly_series() -> None:
    daily = normalize_sgs_payload(sample_sgs_selic_records(), frequency="daily")
    monthly = normalize_sgs_payload(sample_sgs_ipca_records(), frequency="monthly")

    assert daily[-1]["observation_date"].isoformat() == "2026-02-27"
    assert daily[-1]["reference_month_end"].isoformat() == "2026-02-28"
    assert daily[-1]["released_at"] is not None
    assert monthly[-1]["observation_date"].isoformat() == "2026-02-01"
    assert monthly[-1]["reference_month_end"].isoformat() == "2026-02-28"
    assert monthly[-1]["released_at"] is None


def test_backfill_sgs_persists_registry_defined_series(session: Session, catalog) -> None:
    seed_series_catalog(session, catalog)
    backfill_sgs(
        session,
        catalog,
        series_key="sgs_selic_target_rate",
        start_date=date(2026, 2, 25),
        end_date=date(2026, 2, 27),
        records=sample_sgs_selic_records(),
    )

    rows = session.execute(
        select(Observation)
        .where(Observation.series_key == "sgs_selic_target_rate")
        .order_by(Observation.observation_date.asc())
    ).scalars().all()
    assert len(rows) == 3
    assert rows[-1].value_numeric == 20.0
    assert rows[-1].reference_month_end.isoformat() == "2026-02-28"


def test_backfill_sgs_supports_approved_commodity_driver(session: Session, catalog) -> None:
    seed_series_catalog(session, catalog)
    backfill_sgs(
        session,
        catalog,
        series_key="commodity_terms_of_trade",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 3, 1),
        records=sample_sgs_commodity_records(),
    )

    rows = session.execute(
        select(Observation)
        .where(Observation.series_key == "commodity_terms_of_trade")
        .order_by(Observation.observation_date.asc())
    ).scalars().all()

    assert len(rows) == 3
    assert rows[-1].value_numeric == 102.25
    assert rows[-1].reference_month_end.isoformat() == "2026-03-31"
    assert rows[-1].released_at is None
