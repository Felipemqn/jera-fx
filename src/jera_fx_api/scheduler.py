"""Daily refresh scheduler.

Runs the full ingestion → feature → snapshot pipeline in the correct
dependency order. Designed to be invoked by cron, systemd timer, or
any external scheduler.

Usage:
    python -m jera_fx_api.scheduler

Exit codes:
    0 — all steps completed successfully
    1 — one or more steps failed (details in stderr)
"""

from __future__ import annotations

import sys
import traceback
from datetime import date, timedelta
from typing import Any

from jera_fx_api.config import get_settings
from jera_fx_api.db.session import build_session_factory
from jera_fx_api.services import seed_series_catalog
from jera_fx_connectors.bcb_ptax import backfill_ptax
from jera_fx_connectors.bcb_sgs import backfill_sgs
from jera_fx_connectors.fed_h10 import backfill_fed_h10
from jera_fx_features.client_overview import build_client_overview_snapshot
from jera_fx_features.investment_builder import build_driver_variations_snapshot, build_rolling_regression_snapshot
from jera_fx_features.reer_bands import build_reer_bands_snapshot
from jera_fx_features.reer_canonical import build_reer_canonical_features
from jera_fx_features.scenario_builder import build_scenario_set_snapshot
from jera_fx_features.source_freshness import build_ptax_monthly_history_snapshot, build_source_freshness_snapshot
from jera_fx_features.tactical_drivers import (
    build_tactical_driver_freshness_snapshot,
    build_tactical_driver_history_snapshot,
    build_tactical_driver_latest_snapshot,
)
from jera_fx_features.tactical_signal import (
    build_domestic_macro_driver_snapshot,
    build_tactical_signal_components_snapshot,
    build_tactical_signal_inputs_snapshot,
    build_tactical_signal_readiness_snapshot,
    build_tactical_signal_snapshot,
)
from jera_fx_registry.series_catalog import load_series_catalog


def _log(msg: str) -> None:
    print(f"[scheduler] {msg}", flush=True)


def _err(msg: str) -> None:
    print(f"[scheduler] ERROR: {msg}", file=sys.stderr, flush=True)


def run_daily_refresh() -> dict[str, Any]:
    """Execute the full daily refresh pipeline.

    Returns a summary dict with step results.
    """
    settings = get_settings()
    catalog = load_series_catalog(settings.series_catalog_path)
    session_factory = build_session_factory(settings)

    today = date.today()
    lookback_start = today - timedelta(days=7)  # re-ingest last 7 days

    results: dict[str, str] = {}
    errors: list[str] = []

    with session_factory() as session:
        # Step 1: Seed catalog (idempotent)
        try:
            seed_series_catalog(session, catalog)
            results["seed_catalog"] = "ok"
            _log("Seeded catalog")
        except Exception as e:
            results["seed_catalog"] = f"error: {e}"
            errors.append(f"seed_catalog: {e}")
            _err(f"seed_catalog: {e}")

        # Step 2: Backfill PTAX (last 7 days)
        try:
            backfill_ptax(session, catalog, start_date=lookback_start, end_date=today)
            results["backfill_ptax"] = "ok"
            _log("Backfilled PTAX")
        except Exception as e:
            results["backfill_ptax"] = f"error: {e}"
            errors.append(f"backfill_ptax: {e}")
            _err(f"backfill_ptax: {e}")

        # Step 3: Backfill SGS series
        sgs_series = ["sgs_selic_target_rate", "sgs_ipca_12m", "commodity_terms_of_trade"]
        for sk in sgs_series:
            try:
                backfill_sgs(session, catalog, series_key=sk, start_date=lookback_start, end_date=today)
                results[f"backfill_sgs_{sk}"] = "ok"
            except Exception as e:
                results[f"backfill_sgs_{sk}"] = f"error: {e}"
                errors.append(f"backfill_sgs_{sk}: {e}")

        # Step 4: Backfill H10 (DXY)
        try:
            backfill_fed_h10(session, catalog, series_key="broad_usd_index", start_date=lookback_start, end_date=today)
            results["backfill_h10"] = "ok"
            _log("Backfilled H10")
        except Exception as e:
            results["backfill_h10"] = f"error: {e}"
            errors.append(f"backfill_h10: {e}")

        # Step 5: Build curated features (dependency order)
        build_steps = [
            ("build_reer_canonical", lambda: build_reer_canonical_features(session, catalog)),
            ("build_client_overview", lambda: build_client_overview_snapshot(session, catalog)),
            ("build_reer_bands", lambda: build_reer_bands_snapshot(session, catalog)),
            ("build_source_freshness", lambda: build_source_freshness_snapshot(session, catalog)),
            ("build_ptax_history", lambda: build_ptax_monthly_history_snapshot(session)),
            ("build_domestic_macro", lambda: build_domestic_macro_driver_snapshot(session, catalog)),
            ("build_driver_history", lambda: build_tactical_driver_history_snapshot(session, catalog)),
            ("build_driver_latest", lambda: build_tactical_driver_latest_snapshot(session, catalog)),
            ("build_driver_freshness", lambda: build_tactical_driver_freshness_snapshot(session, catalog)),
            ("build_signal_readiness", lambda: build_tactical_signal_readiness_snapshot(session, catalog)),
            ("build_signal_components", lambda: build_tactical_signal_components_snapshot(session, catalog)),
            ("build_signal_inputs", lambda: build_tactical_signal_inputs_snapshot(session, catalog)),
            ("build_tactical_signal", lambda: build_tactical_signal_snapshot(session, catalog)),
            ("build_scenario_set", lambda: build_scenario_set_snapshot(session)),
            ("build_rolling_regression", lambda: build_rolling_regression_snapshot(session)),
            ("build_driver_variations", lambda: build_driver_variations_snapshot(session)),
        ]

        for step_name, step_fn in build_steps:
            try:
                step_fn()
                results[step_name] = "ok"
                _log(f"Completed {step_name}")
            except Exception as e:
                results[step_name] = f"error: {e}"
                errors.append(f"{step_name}: {e}")
                _err(f"{step_name}: {e}")

    summary = {
        "date": today.isoformat(),
        "total_steps": len(results),
        "ok_steps": sum(1 for v in results.values() if v == "ok"),
        "error_steps": len(errors),
        "results": results,
        "errors": errors,
    }

    _log(f"Refresh complete: {summary['ok_steps']}/{summary['total_steps']} OK, {summary['error_steps']} errors")
    return summary


def main() -> None:
    summary = run_daily_refresh()
    if summary["error_steps"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
