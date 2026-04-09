from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from jera_fx_api.db.models import ClientSnapshot, FeatureValue, IngestionRun, Observation, SourceFile
from jera_fx_api.services import seed_series_catalog
from jera_fx_connectors.bcb_focus import backfill_focus
from jera_fx_connectors.bcb_ptax import backfill_ptax
from jera_fx_connectors.bcb_sgs import backfill_sgs
from jera_fx_connectors.fed_h10 import backfill_fed_h10
from jera_fx_connectors.manual_cds_file import ingest_manual_cds_file
from jera_fx_connectors.reer_workbook import ingest_reer_workbook
from jera_fx_features.reer_canonical import build_reer_canonical_features
from jera_fx_features.source_freshness import build_ptax_monthly_history_snapshot
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
from tests.conftest import (
    sample_focus_exchange_records,
    sample_h10_csv,
    sample_focus_ipca_records,
    sample_ptax_records,
    sample_sgs_commodity_records,
    sample_sgs_selic_records,
    write_sample_cds_csv,
)


def test_seed_and_backfill_paths_are_idempotent(session: Session, catalog, settings) -> None:
    seed_series_catalog(session, catalog)
    ingest_reer_workbook(session, catalog, settings.reer_workbook_path)
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
    backfill_sgs(
        session,
        catalog,
        series_key="commodity_terms_of_trade",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 3, 1),
        records=sample_sgs_commodity_records(),
    )
    backfill_sgs(
        session,
        catalog,
        series_key="sgs_selic_target_rate",
        start_date=date(2026, 2, 25),
        end_date=date(2026, 2, 27),
        records=sample_sgs_selic_records(),
    )
    backfill_focus(
        session,
        catalog,
        series_key="focus_exchange_rate_median_2026",
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 2),
        records=sample_focus_exchange_records(),
    )
    backfill_focus(
        session,
        catalog,
        series_key="focus_exchange_rate_median_2026",
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 2),
        records=sample_focus_exchange_records(),
    )
    backfill_ptax(
        session,
        catalog,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 2, 28),
        records=sample_ptax_records(),
    )
    backfill_focus(
        session,
        catalog,
        series_key="focus_ipca_median_2026",
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 2),
        records=sample_focus_ipca_records(2026),
    )
    backfill_fed_h10(
        session,
        catalog,
        series_key="broad_usd_index",
        start_date=date(2026, 3, 30),
        end_date=date(2026, 4, 2),
        csv_content=sample_h10_csv(),
    )
    backfill_fed_h10(
        session,
        catalog,
        series_key="broad_usd_index",
        start_date=date(2026, 3, 30),
        end_date=date(2026, 4, 2),
        csv_content=sample_h10_csv(),
    )
    build_ptax_monthly_history_snapshot(session)
    build_ptax_monthly_history_snapshot(session)
    build_domestic_macro_driver_snapshot(session, catalog)
    build_domestic_macro_driver_snapshot(session, catalog)
    build_tactical_driver_history_snapshot(session, catalog)
    build_tactical_driver_history_snapshot(session, catalog)
    build_tactical_driver_latest_snapshot(session, catalog)
    build_tactical_driver_latest_snapshot(session, catalog)
    build_tactical_driver_freshness_snapshot(session, catalog)
    build_tactical_driver_freshness_snapshot(session, catalog)
    build_tactical_signal_readiness_snapshot(session, catalog)
    build_tactical_signal_readiness_snapshot(session, catalog)
    build_tactical_signal_components_snapshot(session, catalog)
    build_tactical_signal_components_snapshot(session, catalog)
    build_tactical_signal_inputs_snapshot(session, catalog)
    build_tactical_signal_inputs_snapshot(session, catalog)

    source_files = session.execute(select(func.count()).select_from(SourceFile)).scalar_one()
    raw_observations = session.execute(select(func.count()).select_from(Observation)).scalar_one()
    ingestion_runs = session.execute(select(func.count()).select_from(IngestionRun)).scalar_one()
    feature_values = session.execute(select(func.count()).select_from(FeatureValue)).scalar_one()
    client_snapshots = session.execute(select(func.count()).select_from(ClientSnapshot)).scalar_one()

    assert source_files == 1
    assert raw_observations > 0
    assert ingestion_runs == 7
    assert feature_values > 0
    assert client_snapshots == 8


def test_manual_cds_ingest_and_signal_snapshot_are_idempotent(marts_ready_session, catalog, tmp_path) -> None:
    cds_file_path = write_sample_cds_csv(tmp_path / "BRGV5YUSAC=R_manual_batch.csv")

    ingest_manual_cds_file(marts_ready_session, catalog, file_path=cds_file_path)
    ingest_manual_cds_file(marts_ready_session, catalog, file_path=cds_file_path)
    build_tactical_driver_history_snapshot(marts_ready_session, catalog)
    build_tactical_driver_history_snapshot(marts_ready_session, catalog)
    build_tactical_driver_latest_snapshot(marts_ready_session, catalog)
    build_tactical_driver_latest_snapshot(marts_ready_session, catalog)
    build_tactical_driver_freshness_snapshot(marts_ready_session, catalog)
    build_tactical_driver_freshness_snapshot(marts_ready_session, catalog)
    build_tactical_signal_readiness_snapshot(marts_ready_session, catalog)
    build_tactical_signal_readiness_snapshot(marts_ready_session, catalog)
    build_tactical_signal_components_snapshot(marts_ready_session, catalog)
    build_tactical_signal_components_snapshot(marts_ready_session, catalog)
    build_tactical_signal_inputs_snapshot(marts_ready_session, catalog)
    build_tactical_signal_inputs_snapshot(marts_ready_session, catalog)
    build_tactical_signal_snapshot(marts_ready_session)
    build_tactical_signal_snapshot(marts_ready_session)

    cds_source_files = marts_ready_session.execute(
        select(func.count()).select_from(SourceFile).where(SourceFile.source_key == "approved_internal_cds_file_drop")
    ).scalar_one()
    cds_observations = marts_ready_session.execute(
        select(func.count()).select_from(Observation).where(Observation.series_key == "cds_brazil_5y")
    ).scalar_one()
    cds_ingestion_runs = marts_ready_session.execute(
        select(func.count()).select_from(IngestionRun).where(IngestionRun.source_key == "approved_internal_cds_file_drop")
    ).scalar_one()
    tactical_signal_snapshots = marts_ready_session.execute(
        select(func.count()).select_from(ClientSnapshot).where(ClientSnapshot.snapshot_type == "tactical_signal")
    ).scalar_one()

    assert cds_source_files == 1
    assert cds_observations == 3
    assert cds_ingestion_runs == 1
    assert tactical_signal_snapshots == 1
