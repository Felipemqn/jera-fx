from __future__ import annotations

from fastapi.testclient import TestClient

from jera_fx_api.db.session import get_db_session
from jera_fx_api.main import app


def test_client_overview_api_reads_curated_snapshot(overview_ready_session) -> None:
    def override_get_db_session():
        yield overview_ready_session

    app.dependency_overrides[get_db_session] = override_get_db_session
    client = TestClient(app)
    try:
        response = client.get("/v1/client/overview")
        assert response.status_code == 200
        payload = response.json()
        assert payload["snapshot_type"] == "client_overview"
        assert payload["reer"]["client_default_scale_policy"] == "canonical-2020avg100"
        assert payload["reer"]["broad"]["native"]["scale_policy"] == "source-native"
        assert payload["reer"]["broad"]["canonical"]["scale_policy"] == "canonical-2020avg100"
        assert "history" not in payload
    finally:
        app.dependency_overrides.clear()


def test_last_updated_api_returns_snapshot_freshness(overview_ready_session) -> None:
    def override_get_db_session():
        yield overview_ready_session

    app.dependency_overrides[get_db_session] = override_get_db_session
    client = TestClient(app)
    try:
        response = client.get("/v1/meta/last-updated")
        assert response.status_code == 200
        payload = response.json()
        assert payload["reference_month_end"] == "2026-02-28"
        assert payload["latest_reer_reference_month_end"] == "2026-02-28"
        assert payload["latest_ptax_observation_date"] == "2026-02-27"
        assert payload["sources"]
    finally:
        app.dependency_overrides.clear()


def test_reer_bands_api_reads_curated_snapshot(marts_ready_session) -> None:
    def override_get_db_session():
        yield marts_ready_session

    app.dependency_overrides[get_db_session] = override_get_db_session
    client = TestClient(app)
    try:
        response = client.get("/v1/client/reer-bands")
        assert response.status_code == 200
        payload = response.json()
        assert payload["snapshot_type"] == "reer_bands"
        assert payload["client_default_scale_policy"] == "canonical-2020avg100"
        assert payload["broad"]["canonical"]["scale_policy"] == "canonical-2020avg100"
    finally:
        app.dependency_overrides.clear()


def test_source_freshness_api_reads_curated_snapshot(marts_ready_session) -> None:
    def override_get_db_session():
        yield marts_ready_session

    app.dependency_overrides[get_db_session] = override_get_db_session
    client = TestClient(app)
    try:
        response = client.get("/v1/client/source-freshness")
        assert response.status_code == 200
        payload = response.json()
        assert payload["snapshot_type"] == "source_freshness"
        assert payload["spot_freshness"]["latest_spot"]["observation_date"] == "2026-02-27"
        assert len(payload["sources"]) >= 4
    finally:
        app.dependency_overrides.clear()


def test_ptax_history_api_reads_curated_snapshot(marts_ready_session) -> None:
    def override_get_db_session():
        yield marts_ready_session

    app.dependency_overrides[get_db_session] = override_get_db_session
    client = TestClient(app)
    try:
        response = client.get("/v1/client/ptax-history")
        assert response.status_code == 200
        payload = response.json()
        assert payload["snapshot_type"] == "ptax_monthly_history"
        assert len(payload["series"]) == 2
        sell_series = next(item for item in payload["series"] if item["series_key"] == "ptax_usd_brl_sell")
        assert sell_series["latest_monthly_close"]["reference_month_end"] == "2026-02-28"
        assert sell_series["latest_observation"]["observation_date"] == "2026-02-27"
    finally:
        app.dependency_overrides.clear()


def test_tactical_inputs_api_reads_curated_snapshot(marts_ready_session) -> None:
    def override_get_db_session():
        yield marts_ready_session

    app.dependency_overrides[get_db_session] = override_get_db_session
    client = TestClient(app)
    try:
        response = client.get("/v1/client/tactical-inputs")
        assert response.status_code == 200
        payload = response.json()
        assert payload["snapshot_type"] == "tactical_signal_inputs"
        assert payload["signal_computable"] is False
        assert payload["client_default_reer_scale_policy"] == "canonical-2020avg100"
        assert len(payload["domestic_macro"]["focus_exchange_rate"]) == 4
        assert payload["market"]["broad_usd_index"]["series_key"] == "broad_usd_index"
        assert payload["market"]["commodity_terms_of_trade"]["series_key"] == "commodity_terms_of_trade"
        assert payload["missing_driver_keys"] == ["cds_brazil_5y"]
        assert payload["market"]["cds_brazil_5y"]["source_type"] == "approved internal"
        assert payload["market"]["cds_brazil_5y"]["source_mode"] == "approved_internal_file_drop"
        assert payload["market"]["cds_brazil_5y"]["automation_mode"] == "manual_batch"
        assert payload["market"]["cds_brazil_5y"]["production_ingestion_approved"] is True
        assert payload["market"]["cds_brazil_5y"]["configured_for_runtime"] is True
        assert payload["reer"]["broad"]["canonical"]["scale_policy"] == "canonical-2020avg100"
    finally:
        app.dependency_overrides.clear()


def test_tactical_signal_readiness_api_reads_curated_snapshot(marts_ready_session) -> None:
    def override_get_db_session():
        yield marts_ready_session

    app.dependency_overrides[get_db_session] = override_get_db_session
    client = TestClient(app)
    try:
        response = client.get("/v1/client/tactical-signal-readiness")
        assert response.status_code == 200
        payload = response.json()
        assert payload["snapshot_type"] == "tactical_signal_readiness"
        assert payload["signal_computable"] is False
        assert payload["missing_driver_keys"] == ["cds_brazil_5y"]
        cds = next(item for item in payload["missing_drivers"] if item["driver_key"] == "cds_brazil_5y")
        assert cds["source_type"] == "approved internal"
        assert cds["source_mode"] == "approved_internal_file_drop"
        assert cds["automation_mode"] == "manual_batch"
        assert cds["production_ingestion_approved"] is True
        assert cds["configured_for_runtime"] is True
        assert "approved-internal-file-not-ingested" in payload["missing_driver_policy"]
        assert payload["available_driver_keys"]
    finally:
        app.dependency_overrides.clear()


def test_tactical_drivers_api_reads_curated_snapshot(marts_ready_session) -> None:
    def override_get_db_session():
        yield marts_ready_session

    app.dependency_overrides[get_db_session] = override_get_db_session
    client = TestClient(app)
    try:
        response = client.get("/v1/client/tactical-drivers")
        assert response.status_code == 200
        payload = response.json()
        assert payload["snapshot_type"] == "tactical_drivers"
        assert payload["signal_computable"] is False
        assert payload["missing_driver_keys"] == ["cds_brazil_5y"]
        broad_usd = next(item for item in payload["drivers"] if item["driver_key"] == "broad_usd_index")
        commodity = next(item for item in payload["drivers"] if item["driver_key"] == "commodity_terms_of_trade")
        cds = next(item for item in payload["drivers"] if item["driver_key"] == "cds_brazil_5y")
        assert broad_usd["status"] == "available"
        assert broad_usd["points"]
        assert commodity["status"] == "available"
        assert commodity["points"]
        assert cds["status"] == "missing"
        assert cds["configured_for_runtime"] is True
        assert cds["source_mode"] == "approved_internal_file_drop"
    finally:
        app.dependency_overrides.clear()


def test_tactical_driver_freshness_api_reads_curated_snapshot(marts_ready_session) -> None:
    def override_get_db_session():
        yield marts_ready_session

    app.dependency_overrides[get_db_session] = override_get_db_session
    client = TestClient(app)
    try:
        response = client.get("/v1/client/tactical-driver-freshness")
        assert response.status_code == 200
        payload = response.json()
        assert payload["snapshot_type"] == "tactical_driver_freshness"
        assert payload["signal_computable"] is False
        assert payload["missing_driver_keys"] == ["cds_brazil_5y"]
        broad_usd = next(item for item in payload["drivers"] if item["driver_key"] == "broad_usd_index")
        cds = next(item for item in payload["drivers"] if item["driver_key"] == "cds_brazil_5y")
        assert broad_usd["status"] == "available"
        assert broad_usd["latest_released_at"] is not None
        assert cds["status"] == "missing"
        assert cds["source_type"] == "approved internal"
        assert cds["source_mode"] == "approved_internal_file_drop"
        assert cds["automation_mode"] == "manual_batch"
        assert cds["production_ingestion_approved"] is True
        assert cds["configured_for_runtime"] is True
        assert cds["reason"] == "approved-internal-file-not-ingested"
    finally:
        app.dependency_overrides.clear()


def test_tactical_signal_endpoint_remains_absent_until_full_driver_set_is_available(marts_ready_session) -> None:
    def override_get_db_session():
        yield marts_ready_session

    app.dependency_overrides[get_db_session] = override_get_db_session
    client = TestClient(app)
    try:
        response = client.get("/v1/client/tactical-signal")
        assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_tactical_signal_endpoint_reads_curated_snapshot_when_manual_cds_is_ingested(cds_ready_session) -> None:
    def override_get_db_session():
        yield cds_ready_session

    app.dependency_overrides[get_db_session] = override_get_db_session
    client = TestClient(app)
    try:
        response = client.get("/v1/client/tactical-signal")
        assert response.status_code == 200
        payload = response.json()
        assert payload["snapshot_type"] == "tactical_signal"
        assert payload["status"] == "ready-no-score-published"
        assert payload["signal_computable"] is True
        assert payload["source_coverage"]["missing_driver_keys"] == []
        assert payload["methodology"]["score_published"] is False
        cds_mode = next(item for item in payload["automation_modes"] if item["driver_key"] == "cds_brazil_5y")
        assert cds_mode["source_mode"] == "approved_internal_file_drop"
        assert cds_mode["automation_mode"] == "manual_batch"
        cds_freshness = next(item for item in payload["freshness_metadata"] if item["driver_key"] == "cds_brazil_5y")
        assert cds_freshness["status"] == "available"
    finally:
        app.dependency_overrides.clear()
