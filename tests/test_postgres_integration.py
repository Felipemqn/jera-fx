from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from alembic import command
from alembic.config import Config
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from jera_fx_api.config import Settings, get_settings
from jera_fx_api.db.session import build_session_factory, get_db_session
from jera_fx_api.main import app
from jera_fx_api.services import seed_series_catalog
from jera_fx_connectors.bcb_focus import backfill_focus
from jera_fx_connectors.bcb_ptax import backfill_ptax
from jera_fx_connectors.bcb_sgs import backfill_sgs
from jera_fx_connectors.fed_h10 import backfill_fed_h10
from jera_fx_connectors.manual_cds_file import ingest_manual_cds_file
from jera_fx_connectors.reer_workbook import ingest_reer_workbook
from jera_fx_features.client_overview import build_client_overview_snapshot
from jera_fx_features.reer_bands import build_reer_bands_snapshot
from jera_fx_features.reer_canonical import build_reer_canonical_features
from jera_fx_features.source_freshness import build_ptax_monthly_history_snapshot, build_source_freshness_snapshot
from jera_fx_features.tactical_drivers import (
    build_tactical_driver_freshness_snapshot,
    build_tactical_driver_history_snapshot,
    build_tactical_driver_latest_snapshot,
)
from jera_fx_features.tactical_signal import (
    build_domestic_macro_driver_snapshot,
    build_tactical_signal_snapshot,
    build_tactical_signal_components_snapshot,
    build_tactical_signal_inputs_snapshot,
    build_tactical_signal_readiness_snapshot,
)
from jera_fx_registry.series_catalog import load_series_catalog
from tests.conftest import (
    sample_focus_exchange_records,
    sample_focus_ipca_records,
    sample_h10_csv,
    sample_ptax_records,
    sample_sgs_commodity_records,
    sample_sgs_selic_records,
)

POSTGRES_TEST_URL_ENV = "JERA_PG_TEST_DATABASE_URL"
REAL_MANUAL_CDS_FILE = Path("data/raw/cds/BRGV5YUSAC=R_2026-04-07.csv")


def _postgres_test_url() -> str:
    database_url = os.environ.get(POSTGRES_TEST_URL_ENV)
    if not database_url:
        pytest.skip(f"{POSTGRES_TEST_URL_ENV} is not configured")
    return database_url


def _alembic_config(root: Path, database_url: str) -> Config:
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def _real_manual_cds_file(root: Path) -> Path:
    file_path = root / REAL_MANUAL_CDS_FILE
    if not file_path.exists():
        pytest.skip(
            "Real manual CDS file is not present at "
            f"{REAL_MANUAL_CDS_FILE.as_posix()}; PostgreSQL CDS validation requires the "
            "approved internal batch file."
        )
    return file_path


@pytest.mark.postgres_integration
def test_postgres_validation_smoke_path(monkeypatch) -> None:
    root = Path(__file__).resolve().parents[1]
    database_url = _postgres_test_url()

    admin_engine = create_engine(database_url, future=True)
    try:
        with admin_engine.begin() as connection:
            connection.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")
            connection.exec_driver_sql("DROP SCHEMA IF EXISTS curated CASCADE")
            connection.exec_driver_sql("DROP SCHEMA IF EXISTS raw CASCADE")
            connection.exec_driver_sql("DROP SCHEMA IF EXISTS meta CASCADE")
    finally:
        admin_engine.dispose()

    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()
    command.upgrade(_alembic_config(root, database_url), "head")

    settings = Settings(
        APP_ENV="test-postgres",
        DATABASE_URL=database_url,
        SERIES_CATALOG_PATH="config/series_catalog.yml",
        REER_WORKBOOK_PATH="data/raw/reer/REER_database_ver11Mar2026.xlsx",
    )
    catalog = load_series_catalog(settings.series_catalog_path)
    session_factory = build_session_factory(settings)
    engine = session_factory.kw["bind"]
    cds_file_path = _real_manual_cds_file(root)

    try:
        with session_factory() as session:
            seed_series_catalog(session, catalog)
            ingest_reer_workbook(session, catalog, settings.reer_workbook_path)
            build_reer_canonical_features(session, catalog)
            backfill_ptax(
                session,
                catalog,
                start_date=date(2026, 1, 1),
                end_date=date(2026, 2, 28),
                records=sample_ptax_records(),
            )
            backfill_sgs(
                session,
                catalog,
                series_key="sgs_selic_target_rate",
                start_date=date(2026, 2, 25),
                end_date=date(2026, 2, 27),
                records=sample_sgs_selic_records(),
            )
            backfill_sgs(
                session,
                catalog,
                series_key="commodity_terms_of_trade",
                start_date=date(2026, 1, 1),
                end_date=date(2026, 3, 1),
                records=sample_sgs_commodity_records(),
            )
            for year in (2026, 2027, 2028, 2029):
                backfill_focus(
                    session,
                    catalog,
                    series_key=f"focus_exchange_rate_median_{year}",
                    start_date=date(2026, 4, 1),
                    end_date=date(2026, 4, 2),
                    records=sample_focus_exchange_records(year),
                )
                backfill_focus(
                    session,
                    catalog,
                    series_key=f"focus_ipca_median_{year}",
                    start_date=date(2026, 4, 1),
                    end_date=date(2026, 4, 2),
                    records=sample_focus_ipca_records(year),
                )
            backfill_fed_h10(
                session,
                catalog,
                series_key="broad_usd_index",
                start_date=date(2026, 3, 30),
                end_date=date(2026, 4, 2),
                csv_content=sample_h10_csv(),
            )
            ingest_manual_cds_file(
                session,
                catalog,
                file_path=cds_file_path,
            )
            build_client_overview_snapshot(session, catalog)
            build_reer_bands_snapshot(session, catalog)
            build_ptax_monthly_history_snapshot(session)
            build_source_freshness_snapshot(session, catalog)
            build_domestic_macro_driver_snapshot(session, catalog)
            build_tactical_driver_history_snapshot(session, catalog)
            build_tactical_driver_latest_snapshot(session, catalog)
            build_tactical_driver_freshness_snapshot(session, catalog)
            build_tactical_signal_readiness_snapshot(session, catalog)
            build_tactical_signal_components_snapshot(session, catalog)
            build_tactical_signal_inputs_snapshot(session, catalog)
            build_tactical_signal_snapshot(session)

        with session_factory() as session:
            def override_get_db_session():
                yield session

            app.dependency_overrides[get_db_session] = override_get_db_session
            client = TestClient(app)
            try:
                response = client.get("/v1/client/tactical-signal")
                assert response.status_code == 200
                payload = response.json()
                assert payload["status"] == "ready-no-score-published"
                assert payload["signal_computable"] is True
                assert payload["source_coverage"]["missing_driver_keys"] == []
                cds_mode = next(item for item in payload["automation_modes"] if item["driver_key"] == "cds_brazil_5y")
                assert cds_mode["source_mode"] == "approved_internal_file_drop"
                assert cds_mode["automation_mode"] == "manual_batch"
            finally:
                app.dependency_overrides.clear()
    finally:
        engine.dispose()
        get_settings.cache_clear()
