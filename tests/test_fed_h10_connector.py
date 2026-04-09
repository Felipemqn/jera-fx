from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from jera_fx_api.db.models import Observation
from jera_fx_api.services import seed_series_catalog
from jera_fx_connectors.fed_h10 import backfill_fed_h10, normalize_h10_csv
from tests.conftest import sample_h10_csv


def test_normalize_h10_csv_uses_month_end_and_package_metadata(catalog) -> None:
    series_definition = catalog.get_series("broad_usd_index")
    normalized = normalize_h10_csv(sample_h10_csv(), series_definition=series_definition)

    assert normalized[-1]["observation_date"].isoformat() == "2026-04-02"
    assert normalized[-1]["reference_month_end"].isoformat() == "2026-04-30"
    assert normalized[-1]["value_numeric"] == 120.25
    assert normalized[-1]["attributes_json"]["series_description"] == "Nominal Broad Dollar Index"
    assert normalized[-1]["attributes_json"]["unique_identifier"] == "H10/H10/JRXWTFB_N.B"


def test_backfill_h10_persists_approved_broad_usd_series(session: Session, catalog) -> None:
    seed_series_catalog(session, catalog)
    backfill_fed_h10(
        session,
        catalog,
        series_key="broad_usd_index",
        start_date=date(2026, 3, 30),
        end_date=date(2026, 4, 2),
        csv_content=sample_h10_csv(),
    )

    rows = session.execute(
        select(Observation)
        .where(Observation.series_key == "broad_usd_index")
        .order_by(Observation.observation_date.asc())
    ).scalars().all()

    assert len(rows) == 4
    assert rows[-1].value_numeric == 120.25
    assert rows[-1].reference_month_end.isoformat() == "2026-04-30"
    assert rows[-1].attributes_json["source_code"] == "JRXWTFB_N.B"
