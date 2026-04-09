from __future__ import annotations

from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from jera_fx_api.db.models import IngestionRun, Observation, SourceFile
from jera_fx_api.services import seed_series_catalog
from jera_fx_connectors.reer_workbook import ingest_reer_workbook, parse_reer_series
from jera_fx_registry.series_catalog import SeriesCatalog


def test_parse_reer_series_maps_rows_to_reference_month_end(catalog: SeriesCatalog) -> None:
    parsed = parse_reer_series(
        Path("data/raw/reer/REER_database_ver11Mar2026.xlsx"),
        catalog.get_series("reer_120_br"),
    )
    assert parsed["source_code"] == "REER_120_BR"
    assert parsed["update_header"]
    assert parsed["rows"][0]["observation_date"].day >= 28
    assert parsed["rows"][-1]["reference_month_end"].isoformat() == "2026-02-28"


def test_reer_workbook_seed_is_idempotent(
    session: Session,
    catalog: SeriesCatalog,
) -> None:
    seed_series_catalog(session, catalog)
    workbook_path = Path("data/raw/reer/REER_database_ver11Mar2026.xlsx")

    first = ingest_reer_workbook(session, catalog, workbook_path)
    second = ingest_reer_workbook(session, catalog, workbook_path)

    observation_count = session.execute(select(func.count()).select_from(Observation)).scalar_one()
    source_file_count = session.execute(select(func.count()).select_from(SourceFile)).scalar_one()
    ingestion_run_count = session.execute(select(func.count()).select_from(IngestionRun)).scalar_one()

    assert first["checksum_sha256"] == second["checksum_sha256"]
    assert observation_count == first["row_count"]
    assert source_file_count == 1
    assert ingestion_run_count == 1
