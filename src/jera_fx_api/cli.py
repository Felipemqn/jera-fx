from __future__ import annotations

import argparse
from datetime import date

from jera_fx_api.config import get_settings
from jera_fx_api.db.session import build_session_factory
from jera_fx_api.services import seed_series_catalog
from jera_fx_connectors.bcb_focus import backfill_focus
from jera_fx_connectors.bcb_ptax import backfill_ptax
from jera_fx_connectors.bcb_sgs import backfill_sgs
from jera_fx_connectors.fed_h10 import backfill_fed_h10
from jera_fx_connectors.manual_cds_file import ingest_manual_cds_file, validate_manual_cds_file
from jera_fx_connectors.reer_workbook import ingest_reer_workbook
from jera_fx_features.client_overview import build_client_overview_snapshot
from jera_fx_features.investment_builder import build_driver_variations_snapshot, build_rolling_regression_snapshot
from jera_fx_features.ml_builder import build_ml_registry_snapshot
from jera_fx_features.scenario_builder import build_scenario_set_snapshot
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


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="JERA FX foundation CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    seed_parser = subparsers.add_parser("seed", help="Seed the series catalog and REER workbook")
    seed_parser.add_argument("--workbook", default=None, help="Path to the REER workbook seed file")

    cds_parser = subparsers.add_parser("ingest-cds-file", help="Ingest the approved internal manual CDS file drop")
    cds_parser.add_argument("--path", default=None, help="Path to the manual CDS CSV file")
    cds_parser.add_argument("--series-key", default="cds_brazil_5y", help="Series key to ingest from the manual CDS file")
    cds_parser.add_argument("--operator", required=True, help="Operator identifier (email or username) responsible for this ingestion")
    cds_parser.add_argument("--source-note", default=None, help="Optional free-text note describing the source/export (e.g. 'Reuters Eikon manual export 2026-04-07')")

    cds_validate = subparsers.add_parser(
        "validate-cds-file",
        help="Validate a manual CDS file without persisting data (dry-run)",
    )
    cds_validate.add_argument("--path", default=None, help="Path to the manual CDS CSV file")
    cds_validate.add_argument("--series-key", default="cds_brazil_5y", help="Series key to validate against the catalog")
    cds_validate.add_argument("--check-db", action="store_true", help="Also check whether this file checksum was already ingested")

    backfill_parser = subparsers.add_parser("backfill", help="Backfill a supported source")
    backfill_parser.add_argument("--source", choices=["ptax", "sgs", "focus", "h10"], required=True)
    backfill_parser.add_argument("--start", required=True)
    backfill_parser.add_argument("--end", required=True)
    backfill_parser.add_argument("--series-key", action="append", default=[], help="Series key for SGS or Focus backfills; can be repeated")

    scenario_parser = subparsers.add_parser("build-scenario-set", help="Build the scenario set snapshot with fan chart and paths")
    scenario_parser.add_argument("--anchor", type=float, default=None, help="Override the auto-resolved REER anchor (BRL/USD)")

    subparsers.add_parser("build-rolling-regression", help="Build the rolling regression snapshot for investment mode")
    subparsers.add_parser("build-driver-variations", help="Build the 1Y driver variations dashboard snapshot")
    subparsers.add_parser("build-ml-registry", help="Train ML models (ridge + GBM), run backtests, persist registry")

    subparsers.add_parser("build-client-overview", help="Build the curated client overview snapshot")
    subparsers.add_parser("build-reer-bands", help="Build the curated REER bands snapshot")
    subparsers.add_parser("build-source-freshness", help="Build the curated source freshness and spot freshness snapshots")
    subparsers.add_parser("build-ptax-history", help="Build the curated PTAX monthly history snapshot")
    subparsers.add_parser("build-domestic-macro", help="Build the curated domestic macro driver snapshot")
    subparsers.add_parser("build-tactical-driver-history", help="Build the curated tactical driver history snapshot")
    subparsers.add_parser("build-tactical-driver-latest", help="Build the curated tactical driver latest snapshot")
    subparsers.add_parser("build-tactical-driver-freshness", help="Build the curated tactical driver freshness snapshot")
    subparsers.add_parser("build-tactical-signal-components", help="Build the curated tactical signal components snapshot")
    subparsers.add_parser("build-tactical-inputs", help="Build the curated tactical signal input snapshot")
    subparsers.add_parser("build-tactical-signal", help="Build the curated tactical signal status snapshot")
    subparsers.add_parser(
        "build-tactical-signal-readiness",
        help="Build the curated tactical signal readiness snapshot",
    )
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    settings = get_settings()
    catalog = load_series_catalog(settings.series_catalog_path)
    session_factory = build_session_factory(settings)

    with session_factory() as session:
        if args.command == "seed":
            workbook_path = args.workbook or settings.reer_workbook_path
            seed_series_catalog(session, catalog)
            ingest_reer_workbook(session, catalog, workbook_path)
            build_reer_canonical_features(session, catalog)
            print(f"Seeded catalog and REER workbook from {workbook_path}")
            return

        if args.command == "ingest-cds-file":
            file_path = args.path or settings.cds_brazil_5y_file_path
            payload = ingest_manual_cds_file(
                session,
                catalog,
                file_path=file_path,
                series_key=args.series_key,
                operator=args.operator,
                source_note=args.source_note,
            )
            print(
                "Ingested manual CDS file "
                f"{payload['file_path']} for {payload['series_key']} "
                f"({payload['row_count']} rows, checksum {payload['checksum_sha256']}, "
                f"operator={args.operator})"
            )
            return

        if args.command == "validate-cds-file":
            file_path = args.path or settings.cds_brazil_5y_file_path
            report = validate_manual_cds_file(
                catalog,
                file_path=file_path,
                series_key=args.series_key,
                session=session if args.check_db else None,
            )
            import json as _json
            print(_json.dumps(report, indent=2, sort_keys=True, default=str))
            if report["errors"]:
                raise SystemExit(1)
            return

        if args.command == "build-scenario-set":
            payload = build_scenario_set_snapshot(
                session,
                anchor_override=args.anchor,
            )
            expected_1y = next(
                (p["expected_fair_value"] for p in payload["expected_path"] if p["horizon_years"] == 1), None
            )
            expected_10y = next(
                (p["expected_fair_value"] for p in payload["expected_path"] if p["horizon_years"] == 10), None
            )
            print(
                f"Built scenario set snapshot for {payload['reference_date']} "
                f"(anchor={payload['anchor_value']:.2f}, "
                f"expected 1Y={expected_1y}, 10Y={expected_10y}, "
                f"{payload['scenario_count']} scenarios)"
            )
            return

        if args.command == "build-rolling-regression":
            payload = build_rolling_regression_snapshot(session)
            windows_summary = ", ".join(
                f"{w['window_label']}(R2={w['r_squared']})" for w in payload.get("windows", [])
            )
            print(f"Built rolling regression snapshot: {windows_summary}")
            return

        if args.command == "build-driver-variations":
            payload = build_driver_variations_snapshot(session)
            n = len(payload.get("variations", []))
            print(f"Built driver variations snapshot with {n} drivers")
            return

        if args.command == "build-ml-registry":
            payload = build_ml_registry_snapshot(session)
            for m in payload.get("models", []):
                bt = m.get("backtest", {})
                print(f"  {m['model_name']}: RMSE={bt.get('rmse')}, R2_oos={bt.get('r_squared_oos')}, status={m['status']}")
            print(f"ML registry built with {len(payload.get('models', []))} models ({payload['n_observations']} obs)")
            return

        if args.command == "backfill":
            start_date = date.fromisoformat(args.start)
            end_date = date.fromisoformat(args.end)
            if args.source == "ptax":
                backfill_ptax(session, catalog, start_date=start_date, end_date=end_date)
                print(f"Backfilled PTAX from {start_date.isoformat()} to {end_date.isoformat()}")
                return
            if not args.series_key:
                raise ValueError(f"--series-key is required for source {args.source}")
            if args.source == "sgs":
                for series_key in args.series_key:
                    backfill_sgs(session, catalog, series_key=series_key, start_date=start_date, end_date=end_date)
                print(f"Backfilled SGS series {', '.join(args.series_key)} from {start_date.isoformat()} to {end_date.isoformat()}")
                return
            if args.source == "focus":
                for series_key in args.series_key:
                    backfill_focus(session, catalog, series_key=series_key, start_date=start_date, end_date=end_date)
                print(f"Backfilled Focus series {', '.join(args.series_key)} from {start_date.isoformat()} to {end_date.isoformat()}")
                return
            if args.source == "h10":
                for series_key in args.series_key:
                    backfill_fed_h10(session, catalog, series_key=series_key, start_date=start_date, end_date=end_date)
                print(f"Backfilled H10 series {', '.join(args.series_key)} from {start_date.isoformat()} to {end_date.isoformat()}")
                return
            raise ValueError(f"Unsupported source: {args.source}")

        if args.command == "build-client-overview":
            payload = build_client_overview_snapshot(session, catalog)
            print(f"Built client overview snapshot for {payload['reference_month_end']}")
            return

        if args.command == "build-reer-bands":
            payload = build_reer_bands_snapshot(session, catalog)
            print(f"Built REER bands snapshot for {payload['reference_month_end']}")
            return

        if args.command == "build-source-freshness":
            payload = build_source_freshness_snapshot(session, catalog)
            print(f"Built source freshness snapshot for {payload['reference_month_end']}")
            return

        if args.command == "build-ptax-history":
            payload = build_ptax_monthly_history_snapshot(session)
            print(f"Built PTAX monthly history snapshot for {payload['reference_month_end']}")
            return

        if args.command == "build-domestic-macro":
            payload = build_domestic_macro_driver_snapshot(session, catalog)
            print(f"Built domestic macro driver snapshot for {payload['reference_month_end']}")
            return

        if args.command == "build-tactical-driver-history":
            payload = build_tactical_driver_history_snapshot(session, catalog)
            print(f"Built tactical driver history snapshot for {payload['reference_month_end']}")
            return

        if args.command == "build-tactical-driver-latest":
            payload = build_tactical_driver_latest_snapshot(session, catalog)
            print(f"Built tactical driver latest snapshot for {payload['reference_month_end']}")
            return

        if args.command == "build-tactical-driver-freshness":
            payload = build_tactical_driver_freshness_snapshot(session, catalog)
            print(f"Built tactical driver freshness snapshot for {payload['reference_month_end']}")
            return

        if args.command == "build-tactical-signal-components":
            payload = build_tactical_signal_components_snapshot(session, catalog)
            print(f"Built tactical signal components snapshot for {payload['reference_month_end']}")
            return

        if args.command == "build-tactical-inputs":
            payload = build_tactical_signal_inputs_snapshot(session, catalog)
            print(f"Built tactical signal inputs snapshot for {payload['reference_month_end']}")
            return

        if args.command == "build-tactical-signal":
            payload = build_tactical_signal_snapshot(session, catalog)
            print(f"Built tactical signal snapshot for {payload['reference_month_end']} with status {payload['status']}")
            if payload.get("score") is not None:
                print(f"  score={payload['score']}  regime={payload['regime']}")
            return

        if args.command == "build-tactical-signal-readiness":
            payload = build_tactical_signal_readiness_snapshot(session, catalog)
            print(f"Built tactical signal readiness snapshot for {payload['reference_month_end']}")
            return

        raise ValueError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    main()
