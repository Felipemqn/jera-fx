from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from jera_fx_api.db.models import Observation
from jera_fx_api.services import seed_series_catalog
from jera_fx_connectors.bcb_focus import backfill_focus, normalize_focus_payload
from tests.conftest import sample_focus_exchange_records, sample_focus_ipca_records


def test_normalize_focus_payload_uses_vintage_date_month_end_and_value_field(catalog) -> None:
    series_definition = catalog.get_series("focus_exchange_rate_median_2026")
    normalized = normalize_focus_payload(sample_focus_exchange_records(2026), series_definition=series_definition)

    assert normalized[-1]["observation_date"].isoformat() == "2026-04-02"
    assert normalized[-1]["reference_month_end"].isoformat() == "2026-04-30"
    assert normalized[-1]["value_numeric"] == 10.25
    assert normalized[-1]["vintage_timestamp"] is not None
    assert normalized[-1]["attributes_json"]["target_reference"] == "2026"


def test_backfill_focus_persists_registry_defined_series(session: Session, catalog) -> None:
    seed_series_catalog(session, catalog)
    backfill_focus(
        session,
        catalog,
        series_key="focus_ipca_median_2026",
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 2),
        records=sample_focus_ipca_records(2026),
    )

    rows = session.execute(
        select(Observation)
        .where(Observation.series_key == "focus_ipca_median_2026")
        .order_by(Observation.observation_date.asc())
    ).scalars().all()
    assert len(rows) == 2
    assert rows[-1].value_numeric == 20.25
    assert rows[-1].reference_month_end.isoformat() == "2026-04-30"


def test_backfill_focus_supports_expanded_year_catalog(session: Session, catalog) -> None:
    seed_series_catalog(session, catalog)
    backfill_focus(
        session,
        catalog,
        series_key="focus_exchange_rate_median_2029",
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 2),
        records=sample_focus_exchange_records(2029),
    )

    row = session.execute(
        select(Observation)
        .where(Observation.series_key == "focus_exchange_rate_median_2029")
        .order_by(Observation.observation_date.desc())
    ).scalars().first()

    assert row is not None
    assert row.attributes_json["target_reference"] == "2029"
    assert row.reference_month_end.isoformat() == "2026-04-30"
