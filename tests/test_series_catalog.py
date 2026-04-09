from __future__ import annotations

from jera_fx_registry.series_catalog import load_series_catalog


def test_series_catalog_contains_phase2_series() -> None:
    catalog = load_series_catalog("config/series_catalog.yml")
    series_keys = {item.series_key for item in catalog.series}
    assert {
        "reer_120_br",
        "reer_51_br",
        "ptax_usd_brl_buy",
        "ptax_usd_brl_sell",
        "cds_brazil_5y",
        "broad_usd_index",
        "commodity_terms_of_trade",
        "sgs_selic_target_rate",
        "sgs_ipca_12m",
        "focus_exchange_rate_median_2026",
        "focus_exchange_rate_median_2027",
        "focus_exchange_rate_median_2028",
        "focus_exchange_rate_median_2029",
        "focus_ipca_median_2026",
        "focus_ipca_median_2027",
        "focus_ipca_median_2028",
        "focus_ipca_median_2029",
    } <= series_keys


def test_series_catalog_defines_required_metadata() -> None:
    catalog = load_series_catalog("config/series_catalog.yml")
    cds_source = catalog.get_source("approved_internal_cds_file_drop")
    assert cds_source.provider == "internal_manual_upload"
    assert cds_source.source_type == "approved internal"
    assert cds_source.source_mode == "approved_internal_file_drop"
    assert cds_source.automation_mode == "manual_batch"
    assert cds_source.production_ingestion_approved is True
    assert cds_source.connection["canonical_value_field"] == "Price"

    broad_reer = catalog.get_series("reer_120_br")
    assert broad_reer.provider
    assert broad_reer.source_code == "REER_120_BR"
    assert broad_reer.frequency == "monthly"
    assert broad_reer.units == "index"
    assert broad_reer.release_metadata_behavior == "workbook update header"
    assert broad_reer.transformation_rules["ingestion"]["reference_month_end"] is True
    assert broad_reer.display_metadata["client_default_scale"] == "canonical-2020avg100"
    assert broad_reer.canonical_scale_policy["default_display"] == "canonical-2020avg100"

    focus_exchange = catalog.get_series("focus_exchange_rate_median_2026")
    assert focus_exchange.transformation_rules["ingestion"]["entity_set"] == "ExpectativasMercadoAnuais"
    assert focus_exchange.transformation_rules["ingestion"]["filters"]["Indicador"] == "C\u00E2mbio"
    assert focus_exchange.transformation_rules["ingestion"]["filters"]["DataReferencia"] == "2026"
    assert focus_exchange.transformation_rules["ingestion"]["filters"]["baseCalculo"] == 0

    broad_usd = catalog.get_series("broad_usd_index")
    assert broad_usd.source_key == "fed_h10_datadownload"
    assert broad_usd.source_code == "JRXWTFB_N.B"
    assert broad_usd.transformation_rules["ingestion"]["reference_month_end"] is True

    cds_driver = catalog.get_series("cds_brazil_5y")
    assert cds_driver.source_key == "approved_internal_cds_file_drop"
    assert cds_driver.source_code == "BRGV5YUSAC=R"
    assert cds_driver.provider == "internal_manual_upload"
    assert cds_driver.frequency == "daily"
    assert cds_driver.units == "basis_points"
    assert cds_driver.transformation_rules["ingestion"]["value_field"] == "Price"

    commodity_driver = catalog.get_series("commodity_terms_of_trade")
    assert commodity_driver.source_key == "bcb_sgs_api"
    assert commodity_driver.source_code == "29042"
    assert commodity_driver.frequency == "monthly"


def test_series_catalog_defines_tactical_signal_requirements() -> None:
    catalog = load_series_catalog("config/series_catalog.yml")
    drivers = catalog.tactical_driver_map()

    assert drivers["broad_usd_index"].required_for_signal is True
    assert drivers["broad_usd_index"].missing_reason is None
    assert drivers["commodity_terms_of_trade"].required_for_signal is True
    assert drivers["commodity_terms_of_trade"].missing_reason is None
    assert drivers["cds_brazil_5y"].required_for_signal is True
    assert drivers["cds_brazil_5y"].source_type == "approved internal"
    assert drivers["cds_brazil_5y"].source_mode == "approved_internal_file_drop"
    assert drivers["cds_brazil_5y"].automation_mode == "manual_batch"
    assert drivers["cds_brazil_5y"].production_ingestion_approved is True
    assert drivers["cds_brazil_5y"].required_configuration == []
    assert drivers["cds_brazil_5y"].missing_reason == "approved-internal-file-not-ingested"
