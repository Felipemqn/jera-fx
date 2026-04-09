from __future__ import annotations

from jera_fx_features.reer_bands import get_latest_reer_bands_snapshot
from jera_fx_features.source_freshness import (
    get_latest_ptax_monthly_history_snapshot,
    get_latest_source_freshness_snapshot,
)
from jera_fx_features.tactical_drivers import (
    get_latest_tactical_driver_freshness_snapshot,
    get_latest_tactical_driver_history_snapshot,
    get_latest_tactical_driver_latest_snapshot,
)
from jera_fx_features.tactical_signal import (
    get_latest_domestic_macro_driver_snapshot,
    get_latest_tactical_signal_snapshot,
    get_latest_tactical_signal_components_snapshot,
    get_latest_tactical_signal_inputs_snapshot,
    get_latest_tactical_signal_readiness_snapshot,
)


def test_reer_bands_snapshot_is_curated_and_canonical(marts_ready_session) -> None:
    snapshot = get_latest_reer_bands_snapshot(marts_ready_session)
    assert snapshot is not None
    payload = snapshot.payload_json
    assert payload["snapshot_type"] == "reer_bands"
    assert payload["client_default_scale_policy"] == "canonical-2020avg100"
    assert payload["broad"]["canonical"]["scale_policy"] == "canonical-2020avg100"
    assert payload["broad"]["distribution"]["p25"] <= payload["broad"]["distribution"]["p75"]


def test_source_freshness_snapshot_contains_spot_and_sources(marts_ready_session) -> None:
    snapshot = get_latest_source_freshness_snapshot(marts_ready_session)
    assert snapshot is not None
    payload = snapshot.payload_json
    source_keys = {entry["source_key"] for entry in payload["sources"]}
    assert payload["snapshot_type"] == "source_freshness"
    assert "bis_reer_local_seed" in source_keys
    assert "bcb_ptax_odata" in source_keys
    assert "bcb_sgs_api" in source_keys
    assert "bcb_expectativas_odata" in source_keys
    assert "fed_h10_datadownload" in source_keys
    assert payload["spot_freshness"]["latest_spot"]["observation_date"] == "2026-02-27"
    assert payload["spot_freshness"]["latest_monthly_close"]["reference_month_end"] == "2026-02-28"


def test_ptax_monthly_history_snapshot_contains_latest_points(marts_ready_session) -> None:
    snapshot = get_latest_ptax_monthly_history_snapshot(marts_ready_session)
    assert snapshot is not None
    payload = snapshot.payload_json
    sell_series = next(item for item in payload["series"] if item["series_key"] == "ptax_usd_brl_sell")

    assert payload["snapshot_type"] == "ptax_monthly_history"
    assert sell_series["latest_monthly_close"]["reference_month_end"] == "2026-02-28"
    assert sell_series["latest_observation"]["observation_date"] == "2026-02-27"


def test_domestic_macro_snapshot_contains_selic_and_focus_curves(marts_ready_session) -> None:
    snapshot = get_latest_domestic_macro_driver_snapshot(marts_ready_session)
    assert snapshot is not None
    payload = snapshot.payload_json

    assert payload["snapshot_type"] == "domestic_macro_driver_snapshot"
    assert payload["selic_target_rate"]["series_key"] == "sgs_selic_target_rate"
    assert len(payload["focus_exchange_rate"]) == 4
    assert len(payload["focus_ipca"]) == 4


def test_tactical_signal_snapshots_report_missing_drivers_without_scoring(marts_ready_session) -> None:
    driver_history_snapshot = get_latest_tactical_driver_history_snapshot(marts_ready_session)
    driver_latest_snapshot = get_latest_tactical_driver_latest_snapshot(marts_ready_session)
    driver_freshness_snapshot = get_latest_tactical_driver_freshness_snapshot(marts_ready_session)
    components_snapshot = get_latest_tactical_signal_components_snapshot(marts_ready_session)
    inputs_snapshot = get_latest_tactical_signal_inputs_snapshot(marts_ready_session)
    readiness_snapshot = get_latest_tactical_signal_readiness_snapshot(marts_ready_session)

    assert driver_history_snapshot is not None
    assert driver_latest_snapshot is not None
    assert driver_freshness_snapshot is not None
    assert components_snapshot is not None
    assert inputs_snapshot is not None
    assert readiness_snapshot is not None
    assert driver_latest_snapshot.payload_json["snapshot_type"] == "tactical_driver_latest"
    assert any(
        driver["driver_key"] == "broad_usd_index" and driver["status"] == "available"
        for driver in driver_latest_snapshot.payload_json["drivers"]
    )
    assert any(
        driver["driver_key"] == "commodity_terms_of_trade" and driver["status"] == "available"
        for driver in driver_history_snapshot.payload_json["drivers"]
    )
    assert any(
        driver["driver_key"] == "cds_brazil_5y" and driver["status"] == "missing"
        for driver in driver_freshness_snapshot.payload_json["drivers"]
    )
    cds_driver = next(
        driver for driver in driver_freshness_snapshot.payload_json["drivers"] if driver["driver_key"] == "cds_brazil_5y"
    )
    assert cds_driver["source_type"] == "approved internal"
    assert cds_driver["source_mode"] == "approved_internal_file_drop"
    assert cds_driver["automation_mode"] == "manual_batch"
    assert cds_driver["production_ingestion_approved"] is True
    assert cds_driver["configured_for_runtime"] is True
    assert cds_driver["required_configuration"] == []
    assert components_snapshot.payload_json["snapshot_type"] == "tactical_signal_components"
    assert components_snapshot.payload_json["market"]["broad_usd_index"] is not None
    assert components_snapshot.payload_json["market"]["commodity_terms_of_trade"] is not None
    assert components_snapshot.payload_json["market"]["cds_brazil_5y"]["configured_for_runtime"] is True
    assert inputs_snapshot.payload_json["signal_computable"] is False
    assert inputs_snapshot.payload_json["missing_driver_keys"] == ["cds_brazil_5y"]
    assert inputs_snapshot.payload_json["market"]["broad_usd_index"]["series_key"] == "broad_usd_index"
    assert readiness_snapshot.payload_json["signal_computable"] is False
    assert readiness_snapshot.payload_json["missing_driver_keys"] == ["cds_brazil_5y"]
    assert "approved-internal-file-not-ingested" in readiness_snapshot.payload_json["missing_driver_policy"]


def test_manual_cds_ingestion_completes_tactical_driver_and_signal_snapshots(cds_ready_session) -> None:
    source_freshness_snapshot = get_latest_source_freshness_snapshot(cds_ready_session)
    driver_history_snapshot = get_latest_tactical_driver_history_snapshot(cds_ready_session)
    driver_latest_snapshot = get_latest_tactical_driver_latest_snapshot(cds_ready_session)
    driver_freshness_snapshot = get_latest_tactical_driver_freshness_snapshot(cds_ready_session)
    components_snapshot = get_latest_tactical_signal_components_snapshot(cds_ready_session)
    inputs_snapshot = get_latest_tactical_signal_inputs_snapshot(cds_ready_session)
    readiness_snapshot = get_latest_tactical_signal_readiness_snapshot(cds_ready_session)
    tactical_signal_snapshot = get_latest_tactical_signal_snapshot(cds_ready_session)

    assert driver_history_snapshot is not None
    assert driver_latest_snapshot is not None
    assert driver_freshness_snapshot is not None
    assert components_snapshot is not None
    assert inputs_snapshot is not None
    assert readiness_snapshot is not None
    assert tactical_signal_snapshot is not None

    source_keys = {entry["source_key"] for entry in source_freshness_snapshot.payload_json["sources"]}
    assert "approved_internal_cds_file_drop" in source_keys
    cds_history = next(
        driver for driver in driver_history_snapshot.payload_json["drivers"] if driver["driver_key"] == "cds_brazil_5y"
    )
    cds_latest = next(
        driver for driver in driver_latest_snapshot.payload_json["drivers"] if driver["driver_key"] == "cds_brazil_5y"
    )
    cds_freshness = next(
        driver for driver in driver_freshness_snapshot.payload_json["drivers"] if driver["driver_key"] == "cds_brazil_5y"
    )

    assert cds_history["status"] == "available"
    assert cds_history["points"]
    assert cds_latest["status"] == "available"
    assert cds_latest["latest"]["series_key"] == "cds_brazil_5y"
    assert cds_freshness["status"] == "available"
    assert cds_freshness["source_mode"] == "approved_internal_file_drop"
    assert cds_freshness["automation_mode"] == "manual_batch"
    assert cds_freshness["latest_released_at"] is None
    assert components_snapshot.payload_json["market"]["cds_brazil_5y"]["series_key"] == "cds_brazil_5y"
    assert inputs_snapshot.payload_json["signal_computable"] is True
    assert inputs_snapshot.payload_json["missing_driver_keys"] == []
    assert readiness_snapshot.payload_json["signal_computable"] is True
    assert readiness_snapshot.payload_json["missing_driver_keys"] == []
    assert tactical_signal_snapshot.payload_json["status"] == "ready-no-score-published"
    assert tactical_signal_snapshot.payload_json["methodology"]["score_published"] is False
