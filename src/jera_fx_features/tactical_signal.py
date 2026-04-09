from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from jera_fx_api.db.models import ClientSnapshot, FeatureValue, Observation
from jera_fx_api.services import stable_hash, upsert_client_snapshot, upsert_feature_set, utcnow
from jera_fx_connectors.bcb_ptax import PTAX_MONTHLY_FEATURE_SET_KEY
from jera_fx_features.reer_bands import canonical_history
from jera_fx_features.reer_normalization import CANONICAL_SCALE_POLICY, RAW_SCALE_POLICY
from jera_fx_registry.series_catalog import SeriesCatalog, SeriesConfig

DOMESTIC_MACRO_DRIVER_SNAPSHOT_FEATURE_SET_KEY = "domestic_macro_driver_snapshot_v1"
TACTICAL_SIGNAL_COMPONENTS_FEATURE_SET_KEY = "tactical_signal_components_snapshot_v1"
TACTICAL_SIGNAL_INPUTS_FEATURE_SET_KEY = "tactical_signal_inputs_snapshot_v1"
TACTICAL_SIGNAL_READINESS_FEATURE_SET_KEY = "tactical_signal_readiness_snapshot_v1"
TACTICAL_SIGNAL_FEATURE_SET_KEY = "tactical_signal_snapshot_v1"


def _latest_observation(session: Session, series_key: str) -> Observation | None:
    statement = (
        select(Observation)
        .where(Observation.series_key == series_key)
        .order_by(Observation.observation_date.desc())
    )
    return session.execute(statement).scalars().first()


def _latest_feature_value(
    session: Session,
    *,
    feature_set_key: str,
    series_key: str,
    feature_name: str,
) -> FeatureValue | None:
    statement = (
        select(FeatureValue)
        .where(
            FeatureValue.feature_set_key == feature_set_key,
            FeatureValue.series_key == series_key,
            FeatureValue.feature_name == feature_name,
        )
        .order_by(FeatureValue.reference_month_end.desc(), FeatureValue.observation_date.desc())
    )
    return session.execute(statement).scalars().first()


def _series_point_payload(
    observation: Observation,
    series_definition: SeriesConfig,
    *,
    source_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "series_key": series_definition.series_key,
        "source_key": series_definition.source_key,
        "source_code": series_definition.source_code,
        "observation_date": observation.observation_date.isoformat(),
        "reference_month_end": observation.reference_month_end.isoformat(),
        "value": observation.value_numeric,
        "units": observation.units,
        "scale_policy": observation.scale_policy,
        "released_at": observation.released_at.isoformat() if observation.released_at else None,
        "ingested_at": observation.ingested_at.isoformat(),
    }
    target_reference = observation.attributes_json.get("target_reference")
    if target_reference is not None:
        payload["target_reference"] = str(target_reference)
    if source_metadata:
        payload.update(source_metadata)
    return payload


def _ptax_monthly_close_payload(session: Session, catalog: SeriesCatalog, series_key: str) -> dict[str, Any]:
    feature_value = _latest_feature_value(
        session,
        feature_set_key=PTAX_MONTHLY_FEATURE_SET_KEY,
        series_key=series_key,
        feature_name="monthly_close",
    )
    if feature_value is None:
        raise ValueError(f"No PTAX monthly close feature found for {series_key}")
    series_definition = catalog.get_series(series_key)
    raw_observation = session.execute(
        select(Observation).where(
            Observation.series_key == series_key,
            Observation.observation_date == feature_value.observation_date,
        )
    ).scalars().first()
    return {
        "series_key": series_definition.series_key,
        "source_key": series_definition.source_key,
        "source_code": series_definition.source_code,
        "observation_date": feature_value.observation_date.isoformat() if feature_value.observation_date else None,
        "reference_month_end": feature_value.reference_month_end.isoformat(),
        "value": feature_value.value_numeric,
        "units": feature_value.units,
        "scale_policy": feature_value.scale_policy,
        "released_at": raw_observation.released_at.isoformat() if raw_observation and raw_observation.released_at else None,
        "ingested_at": raw_observation.ingested_at.isoformat() if raw_observation else feature_value.created_at.isoformat(),
    }


def _latest_reer_payload(session: Session, catalog: SeriesCatalog, series_key: str) -> dict[str, Any]:
    raw_observation = _latest_observation(session, series_key)
    if raw_observation is None:
        raise ValueError(f"No REER observation found for {series_key}")
    canonical_frame = canonical_history(session, series_key)
    latest_canonical = canonical_frame.iloc[-1]
    series_definition = catalog.get_series(series_key)
    source_definition = catalog.get_source(series_definition.source_key)
    return {
        "series_key": series_definition.series_key,
        "source_key": series_definition.source_key,
        "source_code": series_definition.source_code,
        "provider": source_definition.provider,
        "source_type": source_definition.source_type,
        "source_mode": source_definition.source_mode,
        "automation_mode": source_definition.automation_mode,
        "production_ingestion_approved": source_definition.production_ingestion_approved,
        "observation_date": raw_observation.observation_date.isoformat(),
        "reference_month_end": raw_observation.reference_month_end.isoformat(),
        "released_at": raw_observation.released_at.isoformat() if raw_observation.released_at else None,
        "ingested_at": raw_observation.ingested_at.isoformat(),
        "native": {
            "value": raw_observation.value_numeric,
            "units": raw_observation.units,
            "scale_policy": raw_observation.scale_policy,
        },
        "canonical": {
            "value": float(latest_canonical["value_numeric"]),
            "units": series_definition.units,
            "scale_policy": CANONICAL_SCALE_POLICY,
        },
        "normalization_factor": float(latest_canonical["provenance_json"]["scale_factor"]),
    }


def _focus_series(catalog: SeriesCatalog, *, prefix: str) -> list[SeriesConfig]:
    series = [item for item in catalog.series if item.series_key.startswith(prefix)]
    return sorted(
        series,
        key=lambda item: int(item.transformation_rules["ingestion"]["filters"]["DataReferencia"]),
    )


def _latest_focus_payloads(catalog: SeriesCatalog, session: Session, *, prefix: str) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for series_definition in _focus_series(catalog, prefix=prefix):
        observation = _latest_observation(session, series_definition.series_key)
        if observation is None:
            continue
        source_definition = catalog.get_source(series_definition.source_key)
        payloads.append(
            _series_point_payload(
                observation,
                series_definition,
                source_metadata={
                    "provider": source_definition.provider,
                    "source_type": source_definition.source_type,
                    "source_mode": source_definition.source_mode,
                    "automation_mode": source_definition.automation_mode,
                    "production_ingestion_approved": source_definition.production_ingestion_approved,
                },
            )
        )
    return payloads


def _snapshot_reference_month_end(payloads: list[dict[str, Any]]) -> date:
    if not payloads:
        raise ValueError("Cannot determine snapshot reference month without payloads")
    return max(pd.to_datetime(payload["reference_month_end"]).date() for payload in payloads)


def _driver_status_rows(session: Session, catalog: SeriesCatalog) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    available_rows: list[dict[str, Any]] = []
    missing_rows: list[dict[str, Any]] = []
    for requirement in catalog.tactical_signal.required_drivers:
        source_definition = catalog.get_source(requirement.source_key) if requirement.source_key else None
        if requirement.series_key is None:
            missing_rows.append(
                {
                    "driver_key": requirement.driver_key,
                    "label": requirement.label,
                    "category": requirement.category,
                    "status": "missing",
                    "series_key": None,
                    "source_key": requirement.source_key,
                    "provider": source_definition.provider if source_definition else None,
                    "source_type": requirement.source_type or (source_definition.source_type if source_definition else None),
                    "source_mode": requirement.source_mode or (source_definition.source_mode if source_definition else None),
                    "automation_mode": requirement.automation_mode or (source_definition.automation_mode if source_definition else None),
                    "production_ingestion_approved": (
                        requirement.production_ingestion_approved
                        if requirement.production_ingestion_approved is not None
                        else source_definition.production_ingestion_approved if source_definition else None
                    ),
                    "configured_for_runtime": False,
                    "required_configuration": (
                        requirement.required_configuration
                        or (source_definition.required_configuration if source_definition else [])
                    ),
                    "latest_observation_date": None,
                    "latest_reference_month_end": None,
                    "reason": requirement.missing_reason or "series-not-registered",
                    "notes": requirement.notes,
                }
            )
            continue

        series_definition = catalog.get_series(requirement.series_key)
        source_definition = catalog.get_source(series_definition.source_key)
        observation = _latest_observation(session, requirement.series_key)
        if observation is None or series_definition.is_placeholder:
            missing_rows.append(
                {
                    "driver_key": requirement.driver_key,
                    "label": requirement.label,
                    "category": requirement.category,
                    "status": "missing",
                    "series_key": requirement.series_key,
                    "source_key": series_definition.source_key,
                    "provider": source_definition.provider,
                    "source_type": requirement.source_type or source_definition.source_type,
                    "source_mode": requirement.source_mode or source_definition.source_mode,
                    "automation_mode": requirement.automation_mode or source_definition.automation_mode,
                    "production_ingestion_approved": (
                        requirement.production_ingestion_approved
                        if requirement.production_ingestion_approved is not None
                        else source_definition.production_ingestion_approved
                    ),
                    "configured_for_runtime": not series_definition.is_placeholder,
                    "required_configuration": requirement.required_configuration or source_definition.required_configuration,
                    "latest_observation_date": observation.observation_date.isoformat() if observation else None,
                    "latest_reference_month_end": observation.reference_month_end.isoformat() if observation else None,
                    "reason": requirement.missing_reason or "no-observations-ingested",
                    "notes": requirement.notes,
                }
            )
            continue

        available_rows.append(
            {
                "driver_key": requirement.driver_key,
                "label": requirement.label,
                "category": requirement.category,
                "status": "available",
                "series_key": requirement.series_key,
                "source_key": series_definition.source_key,
                "provider": source_definition.provider,
                "source_type": requirement.source_type or source_definition.source_type,
                "source_mode": requirement.source_mode or source_definition.source_mode,
                "automation_mode": requirement.automation_mode or source_definition.automation_mode,
                "production_ingestion_approved": (
                    requirement.production_ingestion_approved
                    if requirement.production_ingestion_approved is not None
                    else source_definition.production_ingestion_approved
                ),
                "configured_for_runtime": True,
                "required_configuration": requirement.required_configuration or source_definition.required_configuration,
                "latest_observation_date": observation.observation_date.isoformat(),
                "latest_reference_month_end": observation.reference_month_end.isoformat(),
                "reason": None,
                "notes": requirement.notes,
            }
        )
    return available_rows, missing_rows


def _domestic_macro_payload(session: Session, catalog: SeriesCatalog) -> dict[str, Any]:
    selic_definition = catalog.get_series("sgs_selic_target_rate")
    selic_observation = _latest_observation(session, selic_definition.series_key)
    if selic_observation is None:
        raise ValueError("No SGS Selic observations found")
    selic_source = catalog.get_source(selic_definition.source_key)

    focus_exchange = _latest_focus_payloads(catalog, session, prefix="focus_exchange_rate_median_")
    focus_ipca = _latest_focus_payloads(catalog, session, prefix="focus_ipca_median_")
    if not focus_exchange or not focus_ipca:
        raise ValueError("No Focus observations found for domestic macro snapshot")

    component_rows = [
        _series_point_payload(selic_observation, selic_definition),
        *focus_exchange,
        *focus_ipca,
    ]
    reference_month_end = _snapshot_reference_month_end(component_rows)
    return {
        "snapshot_type": "domestic_macro_driver_snapshot",
        "reference_month_end": reference_month_end.isoformat(),
        "snapshot_created_at": utcnow().isoformat(),
        "selic_target_rate": _series_point_payload(
            selic_observation,
            selic_definition,
            source_metadata={
                "provider": selic_source.provider,
                "source_type": selic_source.source_type,
                "source_mode": selic_source.source_mode,
                "automation_mode": selic_source.automation_mode,
                "production_ingestion_approved": selic_source.production_ingestion_approved,
            },
        ),
        "focus_exchange_rate": focus_exchange,
        "focus_ipca": focus_ipca,
    }


def _tactical_readiness_payload(session: Session, catalog: SeriesCatalog) -> dict[str, Any]:
    available_rows, missing_rows = _driver_status_rows(session, catalog)
    all_dates = [
        pd.to_datetime(row["latest_reference_month_end"]).date()
        for row in available_rows
        if row["latest_reference_month_end"] is not None
    ]
    if not all_dates:
        raise ValueError("No available drivers found for tactical signal readiness")
    reference_month_end = max(all_dates)
    missing_driver_policy = (
        "No tactical score is emitted until every required driver has an approved source "
        "or approved internal manual-batch source with ingested observations."
    )
    cds_missing = next((row for row in missing_rows if row["driver_key"] == "cds_brazil_5y"), None)
    if cds_missing is not None:
        missing_driver_policy = (
            f"{missing_driver_policy} cds_brazil_5y remains unavailable because "
            f"{cds_missing['reason']}."
        )
    return {
        "snapshot_type": "tactical_signal_readiness",
        "reference_month_end": reference_month_end.isoformat(),
        "snapshot_created_at": utcnow().isoformat(),
        "signal_computable": not missing_rows,
        "available_driver_keys": [row["driver_key"] for row in available_rows],
        "missing_driver_keys": [row["driver_key"] for row in missing_rows],
        "available_drivers": available_rows,
        "missing_drivers": missing_rows,
        "missing_driver_policy": missing_driver_policy,
    }


def _market_driver_payloads(session: Session, catalog: SeriesCatalog) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for series_key in ("broad_usd_index", "commodity_terms_of_trade", "cds_brazil_5y"):
        observation = _latest_observation(session, series_key)
        if observation is None:
            payload[series_key] = None
            continue
        series_definition = catalog.get_series(series_key)
        source_definition = catalog.get_source(series_definition.source_key)
        payload[series_key] = _series_point_payload(
            observation,
            series_definition,
            source_metadata={
                "provider": source_definition.provider,
                "source_type": source_definition.source_type,
                "source_mode": source_definition.source_mode,
                "automation_mode": source_definition.automation_mode,
                "production_ingestion_approved": source_definition.production_ingestion_approved,
            },
        )

    readiness_payload = _tactical_readiness_payload(session, catalog)
    missing_map = {row["driver_key"]: row for row in readiness_payload["missing_drivers"]}
    if "cds_brazil_5y" in missing_map:
        payload["cds_brazil_5y"] = {
            "driver_key": "cds_brazil_5y",
            "status": "missing",
            "source_key": missing_map["cds_brazil_5y"]["source_key"],
            "provider": missing_map["cds_brazil_5y"]["provider"],
            "source_type": missing_map["cds_brazil_5y"]["source_type"],
            "source_mode": missing_map["cds_brazil_5y"]["source_mode"],
            "automation_mode": missing_map["cds_brazil_5y"]["automation_mode"],
            "production_ingestion_approved": missing_map["cds_brazil_5y"]["production_ingestion_approved"],
            "configured_for_runtime": missing_map["cds_brazil_5y"]["configured_for_runtime"],
            "required_configuration": missing_map["cds_brazil_5y"]["required_configuration"],
            "reason": missing_map["cds_brazil_5y"]["reason"],
            "notes": missing_map["cds_brazil_5y"]["notes"],
        }
    return payload


def _tactical_signal_components_payload(
    session: Session,
    catalog: SeriesCatalog,
    *,
    snapshot_type: str,
) -> tuple[dict[str, Any], date]:
    domestic_macro_payload = _domestic_macro_payload(session, catalog)
    readiness_payload = _tactical_readiness_payload(session, catalog)
    market_payload = _market_driver_payloads(session, catalog)
    ptax_spot_observation = _latest_observation(session, "ptax_usd_brl_sell")
    if ptax_spot_observation is None:
        raise ValueError("No PTAX sell observations found")
    ptax_definition = catalog.get_series("ptax_usd_brl_sell")
    ptax_source = catalog.get_source(ptax_definition.source_key)
    ptax_spot_payload = _series_point_payload(
        ptax_spot_observation,
        ptax_definition,
        source_metadata={
            "provider": ptax_source.provider,
            "source_type": ptax_source.source_type,
            "source_mode": ptax_source.source_mode,
            "automation_mode": ptax_source.automation_mode,
            "production_ingestion_approved": ptax_source.production_ingestion_approved,
        },
    )
    ptax_monthly_close_payload = _ptax_monthly_close_payload(session, catalog, "ptax_usd_brl_sell")
    broad_reer_payload = _latest_reer_payload(session, catalog, "reer_120_br")
    narrow_reer_payload = _latest_reer_payload(session, catalog, "reer_51_br")
    reference_month_end = _snapshot_reference_month_end(
        [
            ptax_spot_payload,
            ptax_monthly_close_payload,
            broad_reer_payload,
            narrow_reer_payload,
            domestic_macro_payload["selic_target_rate"],
            *domestic_macro_payload["focus_exchange_rate"],
            *domestic_macro_payload["focus_ipca"],
            *[
                item
                for item in (
                    market_payload["broad_usd_index"],
                    market_payload["commodity_terms_of_trade"],
                    market_payload["cds_brazil_5y"],
                )
                if item is not None
                and item.get("reference_month_end") is not None
            ],
        ]
    )
    payload = {
        "snapshot_type": snapshot_type,
        "reference_month_end": reference_month_end.isoformat(),
        "snapshot_created_at": utcnow().isoformat(),
        "client_default_reer_scale_policy": CANONICAL_SCALE_POLICY,
        "signal_computable": readiness_payload["signal_computable"],
        "missing_driver_keys": readiness_payload["missing_driver_keys"],
        "driver_coverage": {
            "available_driver_keys": readiness_payload["available_driver_keys"],
            "missing_driver_keys": readiness_payload["missing_driver_keys"],
        },
        "methodology": {
            "version": "tactical-signal-components-v1",
            "status": "components-only",
            "readiness_snapshot_type": "tactical_signal_readiness",
        },
        "spot": ptax_spot_payload,
        "ptax_monthly_close": ptax_monthly_close_payload,
        "reer": {
            "broad": broad_reer_payload,
            "narrow": narrow_reer_payload,
        },
        "domestic_macro": {
            "selic_target_rate": domestic_macro_payload["selic_target_rate"],
            "focus_exchange_rate": domestic_macro_payload["focus_exchange_rate"],
            "focus_ipca": domestic_macro_payload["focus_ipca"],
        },
        "market": market_payload,
    }
    return payload, reference_month_end


def build_domestic_macro_driver_snapshot(session: Session, catalog: SeriesCatalog) -> dict[str, Any]:
    feature_set = upsert_feature_set(
        session,
        feature_set_key=DOMESTIC_MACRO_DRIVER_SNAPSHOT_FEATURE_SET_KEY,
        name="Domestic macro driver snapshot",
        version="v1",
        description="Latest available domestic macro and Focus expectation inputs for the tactical signal foundation.",
        scale_policy=RAW_SCALE_POLICY,
        definition_hash=stable_hash({"feature_set_key": DOMESTIC_MACRO_DRIVER_SNAPSHOT_FEATURE_SET_KEY}),
    )
    payload = _domestic_macro_payload(session, catalog)
    upsert_client_snapshot(
        session,
        snapshot_type="domestic_macro_driver_snapshot",
        reference_month_end=pd.to_datetime(payload["reference_month_end"]).date(),
        feature_set_key=feature_set.feature_set_key,
        payload_json=payload,
    )
    session.commit()
    return payload


def build_tactical_signal_readiness_snapshot(session: Session, catalog: SeriesCatalog) -> dict[str, Any]:
    feature_set = upsert_feature_set(
        session,
        feature_set_key=TACTICAL_SIGNAL_READINESS_FEATURE_SET_KEY,
        name="Tactical signal readiness snapshot",
        version="v1",
        description="Availability and missing-driver status for the tactical signal foundation.",
        scale_policy="status-only",
        definition_hash=stable_hash({"feature_set_key": TACTICAL_SIGNAL_READINESS_FEATURE_SET_KEY}),
    )
    payload = _tactical_readiness_payload(session, catalog)
    upsert_client_snapshot(
        session,
        snapshot_type="tactical_signal_readiness",
        reference_month_end=pd.to_datetime(payload["reference_month_end"]).date(),
        feature_set_key=feature_set.feature_set_key,
        payload_json=payload,
    )
    session.commit()
    return payload


def build_tactical_signal_components_snapshot(session: Session, catalog: SeriesCatalog) -> dict[str, Any]:
    feature_set = upsert_feature_set(
        session,
        feature_set_key=TACTICAL_SIGNAL_COMPONENTS_FEATURE_SET_KEY,
        name="Tactical signal components snapshot",
        version="v1",
        description="Signal-ready structural, market, and domestic inputs without computing a tactical score.",
        scale_policy=CANONICAL_SCALE_POLICY,
        definition_hash=stable_hash({"feature_set_key": TACTICAL_SIGNAL_COMPONENTS_FEATURE_SET_KEY}),
    )
    payload, reference_month_end = _tactical_signal_components_payload(
        session,
        catalog,
        snapshot_type="tactical_signal_components",
    )
    upsert_client_snapshot(
        session,
        snapshot_type="tactical_signal_components",
        reference_month_end=reference_month_end,
        feature_set_key=feature_set.feature_set_key,
        payload_json=payload,
    )
    session.commit()
    return payload


def build_tactical_signal_inputs_snapshot(session: Session, catalog: SeriesCatalog) -> dict[str, Any]:
    feature_set = upsert_feature_set(
        session,
        feature_set_key=TACTICAL_SIGNAL_INPUTS_FEATURE_SET_KEY,
        name="Tactical signal inputs snapshot",
        version="v1",
        description="Signal-ready structural, market, and domestic inputs without computing a tactical score.",
        scale_policy=CANONICAL_SCALE_POLICY,
        definition_hash=stable_hash({"feature_set_key": TACTICAL_SIGNAL_INPUTS_FEATURE_SET_KEY}),
    )
    payload, reference_month_end = _tactical_signal_components_payload(
        session,
        catalog,
        snapshot_type="tactical_signal_inputs",
    )
    upsert_client_snapshot(
        session,
        snapshot_type="tactical_signal_inputs",
        reference_month_end=reference_month_end,
        feature_set_key=feature_set.feature_set_key,
        payload_json=payload,
    )
    session.commit()
    return payload


def build_tactical_signal_snapshot(session: Session) -> dict[str, Any]:
    from jera_fx_features.tactical_drivers import get_latest_tactical_driver_freshness_snapshot

    feature_set = upsert_feature_set(
        session,
        feature_set_key=TACTICAL_SIGNAL_FEATURE_SET_KEY,
        name="Tactical signal snapshot",
        version="v1",
        description="Read-only tactical signal status snapshot backed entirely by curated inputs and freshness metadata.",
        scale_policy="status-only",
        definition_hash=stable_hash({"feature_set_key": TACTICAL_SIGNAL_FEATURE_SET_KEY}),
    )
    readiness_snapshot = get_latest_tactical_signal_readiness_snapshot(session)
    inputs_snapshot = get_latest_tactical_signal_inputs_snapshot(session)
    freshness_snapshot = get_latest_tactical_driver_freshness_snapshot(session)
    if readiness_snapshot is None or inputs_snapshot is None or freshness_snapshot is None:
        raise ValueError("Tactical signal snapshot requires readiness, inputs, and freshness snapshots")

    readiness_payload = readiness_snapshot.payload_json
    if not readiness_payload["signal_computable"] or readiness_payload["missing_driver_keys"]:
        raise ValueError("Tactical signal snapshot cannot be built until all required drivers are available")

    freshness_payload = freshness_snapshot.payload_json
    automation_modes = [
        {
            "driver_key": driver["driver_key"],
            "source_key": driver["source_key"],
            "source_mode": driver.get("source_mode"),
            "automation_mode": driver.get("automation_mode"),
            "production_ingestion_approved": driver.get("production_ingestion_approved"),
        }
        for driver in freshness_payload["drivers"]
    ]
    reference_month_end = pd.to_datetime(readiness_payload["reference_month_end"]).date()
    payload = {
        "snapshot_type": "tactical_signal",
        "reference_month_end": reference_month_end.isoformat(),
        "snapshot_created_at": utcnow().isoformat(),
        "status": "ready-no-score-published",
        "client_default_reer_scale_policy": inputs_snapshot.payload_json["client_default_reer_scale_policy"],
        "signal_computable": readiness_payload["signal_computable"],
        "source_coverage": inputs_snapshot.payload_json["driver_coverage"],
        "methodology": {
            "version": "tactical-signal-foundation-v1",
            "status": "full-driver-coverage-no-score-published",
            "readiness_snapshot_type": "tactical_signal_readiness",
            "inputs_snapshot_type": "tactical_signal_inputs",
            "freshness_snapshot_type": "tactical_driver_freshness",
            "score_published": False,
        },
        "freshness_metadata": freshness_payload["drivers"],
        "automation_modes": automation_modes,
        "last_updated": {
            "inputs_snapshot_created_at": inputs_snapshot.payload_json["snapshot_created_at"],
            "readiness_snapshot_created_at": readiness_payload["snapshot_created_at"],
            "freshness_snapshot_created_at": freshness_payload["snapshot_created_at"],
        },
    }
    upsert_client_snapshot(
        session,
        snapshot_type="tactical_signal",
        reference_month_end=reference_month_end,
        feature_set_key=feature_set.feature_set_key,
        payload_json=payload,
    )
    session.commit()
    return payload


def get_latest_domestic_macro_driver_snapshot(session: Session) -> ClientSnapshot | None:
    statement = (
        select(ClientSnapshot)
        .where(ClientSnapshot.snapshot_type == "domestic_macro_driver_snapshot")
        .order_by(ClientSnapshot.reference_month_end.desc(), ClientSnapshot.created_at.desc())
    )
    return session.execute(statement).scalars().first()


def get_latest_tactical_signal_inputs_snapshot(session: Session) -> ClientSnapshot | None:
    statement = (
        select(ClientSnapshot)
        .where(ClientSnapshot.snapshot_type == "tactical_signal_inputs")
        .order_by(ClientSnapshot.reference_month_end.desc(), ClientSnapshot.created_at.desc())
    )
    return session.execute(statement).scalars().first()


def get_latest_tactical_signal_components_snapshot(session: Session) -> ClientSnapshot | None:
    statement = (
        select(ClientSnapshot)
        .where(ClientSnapshot.snapshot_type == "tactical_signal_components")
        .order_by(ClientSnapshot.reference_month_end.desc(), ClientSnapshot.created_at.desc())
    )
    return session.execute(statement).scalars().first()


def get_latest_tactical_signal_readiness_snapshot(session: Session) -> ClientSnapshot | None:
    statement = (
        select(ClientSnapshot)
        .where(ClientSnapshot.snapshot_type == "tactical_signal_readiness")
        .order_by(ClientSnapshot.reference_month_end.desc(), ClientSnapshot.created_at.desc())
    )
    return session.execute(statement).scalars().first()


def get_latest_tactical_signal_snapshot(session: Session) -> ClientSnapshot | None:
    statement = (
        select(ClientSnapshot)
        .where(ClientSnapshot.snapshot_type == "tactical_signal")
        .order_by(ClientSnapshot.reference_month_end.desc(), ClientSnapshot.created_at.desc())
    )
    return session.execute(statement).scalars().first()
