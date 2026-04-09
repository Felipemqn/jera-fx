from __future__ import annotations

from datetime import date
from pathlib import Path
import shutil
import tempfile
from typing import Iterator

import pytest
from sqlalchemy.orm import Session, sessionmaker

from jera_fx_api.config import Settings
from jera_fx_api.db.base import Base
from jera_fx_api.db.session import build_engine
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
from jera_fx_registry.series_catalog import SeriesCatalog, load_series_catalog


def sample_ptax_records() -> list[dict[str, object]]:
    return [
        {
            "cotacaoCompra": 10.10,
            "cotacaoVenda": 10.20,
            "dataHoraCotacao": "2026-01-29T13:00:00-03:00",
        },
        {
            "cotacaoCompra": 10.11,
            "cotacaoVenda": 10.21,
            "dataHoraCotacao": "2026-01-30T13:00:00-03:00",
        },
        {
            "cotacaoCompra": 10.30,
            "cotacaoVenda": 10.40,
            "dataHoraCotacao": "2026-02-27T13:00:00-03:00",
        },
    ]


def sample_sgs_selic_records() -> list[dict[str, object]]:
    return [
        {"data": "25/02/2026", "valor": "20.00"},
        {"data": "26/02/2026", "valor": "20.00"},
        {"data": "27/02/2026", "valor": "20.00"},
    ]


def sample_sgs_ipca_records() -> list[dict[str, object]]:
    return [
        {"data": "01/12/2025", "valor": "101.00"},
        {"data": "01/01/2026", "valor": "102.00"},
        {"data": "01/02/2026", "valor": "103.00"},
    ]


def sample_sgs_commodity_records() -> list[dict[str, object]]:
    return [
        {"data": "01/01/2026", "valor": "99.10"},
        {"data": "01/02/2026", "valor": "101.40"},
        {"data": "01/03/2026", "valor": "102.25"},
    ]


def sample_focus_exchange_records(year: int = 2026) -> list[dict[str, object]]:
    year_offset = year - 2026
    median = 10.0 + year_offset
    return [
        {
            "Indicador": "C\u00E2mbio",
            "IndicadorDetalhe": None,
            "Data": "2026-04-01",
            "DataReferencia": str(year),
            "Media": median - 0.10,
            "Mediana": median,
            "DesvioPadrao": 0.25,
            "Minimo": median - 1.00,
            "Maximo": median + 1.00,
            "numeroRespondentes": 100 + year_offset,
            "baseCalculo": 0,
        },
        {
            "Indicador": "C\u00E2mbio",
            "IndicadorDetalhe": None,
            "Data": "2026-04-02",
            "DataReferencia": str(year),
            "Media": median - 0.05,
            "Mediana": median + 0.25,
            "DesvioPadrao": 0.20,
            "Minimo": median - 1.00,
            "Maximo": median + 1.00,
            "numeroRespondentes": 100 + year_offset,
            "baseCalculo": 0,
        },
    ]


def sample_focus_ipca_records(year: int = 2026) -> list[dict[str, object]]:
    year_offset = year - 2026
    median = 20.0 + year_offset
    return [
        {
            "Indicador": "IPCA",
            "IndicadorDetalhe": None,
            "Data": "2026-04-01",
            "DataReferencia": str(year),
            "Media": median - 0.10,
            "Mediana": median,
            "DesvioPadrao": 0.30,
            "Minimo": median - 1.00,
            "Maximo": median + 1.00,
            "numeroRespondentes": 200 + year_offset,
            "baseCalculo": 0,
        },
        {
            "Indicador": "IPCA",
            "IndicadorDetalhe": None,
            "Data": "2026-04-02",
            "DataReferencia": str(year),
            "Media": median - 0.05,
            "Mediana": median + 0.25,
            "DesvioPadrao": 0.28,
            "Minimo": median - 1.00,
            "Maximo": median + 1.00,
            "numeroRespondentes": 200 + year_offset,
            "baseCalculo": 0,
        },
    ]


def sample_h10_csv() -> str:
    return "\n".join(
        [
            "Series Description,Nominal Broad Dollar Index",
            "Unit:,Index",
            "Mult:,1",
            "Currency:,NA",
            "Unique Identifier:,H10/H10/JRXWTFB_N.B",
            "Time Period,JRXWTFB_N.B",
            "2026-03-30,119.10",
            "2026-03-31,119.35",
            "2026-04-01,119.80",
            "2026-04-02,120.25",
        ]
    )


def sample_cds_csv_text() -> str:
    return "\n".join(
        [
            "Date,Price,Open,High,Low,Change %",
            "2026-04-01,101.25,100.80,102.10,100.55,0.45%",
            "2026-04-02,102.40,101.90,102.75,101.10,1.14%",
            "2026-04-03,100.95,101.80,102.05,100.60,-1.42%",
        ]
    )


def write_sample_cds_csv(file_path: Path) -> Path:
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(sample_cds_csv_text(), encoding="utf-8")
    return file_path


@pytest.fixture()
def tmp_path() -> Iterator[Path]:
    root = Path(tempfile.gettempdir()) / "jera_fx_pytest"
    root.mkdir(parents=True, exist_ok=True)
    path = Path(tempfile.mkdtemp(dir=root))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    return Settings(
        APP_ENV="test",
        DATABASE_URL=f"sqlite+pysqlite:///{(tmp_path / 'foundation.db').as_posix()}",
        SERIES_CATALOG_PATH="config/series_catalog.yml",
        REER_WORKBOOK_PATH="data/raw/reer/REER_database_ver11Mar2026.xlsx",
    )


@pytest.fixture()
def engine(settings: Settings, tmp_path: Path):
    engine = build_engine(settings, sqlite_schema_dir=tmp_path / "sqlite_schemas")
    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture()
def session_factory(engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


@pytest.fixture()
def session(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    with session_factory() as db_session:
        yield db_session


@pytest.fixture()
def catalog(settings: Settings) -> SeriesCatalog:
    return load_series_catalog(settings.series_catalog_path)


@pytest.fixture()
def seeded_session(session: Session, catalog: SeriesCatalog, settings: Settings) -> Session:
    seed_series_catalog(session, catalog)
    ingest_reer_workbook(session, catalog, settings.reer_workbook_path)
    build_reer_canonical_features(session, catalog)
    return session


@pytest.fixture()
def overview_ready_session(seeded_session: Session, catalog: SeriesCatalog) -> Session:
    backfill_ptax(
        seeded_session,
        catalog,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 2, 28),
        records=sample_ptax_records(),
    )
    build_client_overview_snapshot(seeded_session, catalog)
    return seeded_session


@pytest.fixture()
def marts_ready_session(overview_ready_session: Session, catalog: SeriesCatalog) -> Session:
    backfill_sgs(
        overview_ready_session,
        catalog,
        series_key="sgs_selic_target_rate",
        start_date=date(2026, 2, 25),
        end_date=date(2026, 2, 27),
        records=sample_sgs_selic_records(),
    )
    backfill_sgs(
        overview_ready_session,
        catalog,
        series_key="sgs_ipca_12m",
        start_date=date(2025, 12, 1),
        end_date=date(2026, 2, 1),
        records=sample_sgs_ipca_records(),
    )
    backfill_sgs(
        overview_ready_session,
        catalog,
        series_key="commodity_terms_of_trade",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 3, 1),
        records=sample_sgs_commodity_records(),
    )
    backfill_focus(
        overview_ready_session,
        catalog,
        series_key="focus_exchange_rate_median_2026",
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 2),
        records=sample_focus_exchange_records(2026),
    )
    backfill_focus(
        overview_ready_session,
        catalog,
        series_key="focus_ipca_median_2026",
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 2),
        records=sample_focus_ipca_records(2026),
    )
    for year in (2027, 2028, 2029):
        backfill_focus(
            overview_ready_session,
            catalog,
            series_key=f"focus_exchange_rate_median_{year}",
            start_date=date(2026, 4, 1),
            end_date=date(2026, 4, 2),
            records=sample_focus_exchange_records(year),
        )
        backfill_focus(
            overview_ready_session,
            catalog,
            series_key=f"focus_ipca_median_{year}",
            start_date=date(2026, 4, 1),
            end_date=date(2026, 4, 2),
            records=sample_focus_ipca_records(year),
        )
    backfill_fed_h10(
        overview_ready_session,
        catalog,
        series_key="broad_usd_index",
        start_date=date(2026, 3, 30),
        end_date=date(2026, 4, 2),
        csv_content=sample_h10_csv(),
    )
    build_ptax_monthly_history_snapshot(overview_ready_session)
    build_reer_bands_snapshot(overview_ready_session, catalog)
    build_source_freshness_snapshot(overview_ready_session, catalog)
    build_domestic_macro_driver_snapshot(overview_ready_session, catalog)
    build_tactical_driver_history_snapshot(overview_ready_session, catalog)
    build_tactical_driver_latest_snapshot(overview_ready_session, catalog)
    build_tactical_driver_freshness_snapshot(overview_ready_session, catalog)
    build_tactical_signal_readiness_snapshot(overview_ready_session, catalog)
    build_tactical_signal_components_snapshot(overview_ready_session, catalog)
    build_tactical_signal_inputs_snapshot(overview_ready_session, catalog)
    return overview_ready_session


@pytest.fixture()
def cds_ready_session(marts_ready_session: Session, catalog: SeriesCatalog, tmp_path: Path) -> Session:
    cds_file_path = write_sample_cds_csv(tmp_path / "BRGV5YUSAC=R_manual_batch.csv")
    ingest_manual_cds_file(
        marts_ready_session,
        catalog,
        file_path=cds_file_path,
    )
    build_source_freshness_snapshot(marts_ready_session, catalog)
    build_tactical_driver_history_snapshot(marts_ready_session, catalog)
    build_tactical_driver_latest_snapshot(marts_ready_session, catalog)
    build_tactical_driver_freshness_snapshot(marts_ready_session, catalog)
    build_tactical_signal_readiness_snapshot(marts_ready_session, catalog)
    build_tactical_signal_components_snapshot(marts_ready_session, catalog)
    build_tactical_signal_inputs_snapshot(marts_ready_session, catalog)
    build_tactical_signal_snapshot(marts_ready_session)
    return marts_ready_session
