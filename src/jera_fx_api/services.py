from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from jera_fx_api.db.models import (
    ClientSnapshot,
    FeatureSet,
    FeatureValue,
    IngestionRun,
    Observation,
    SeriesDefinition,
    Source,
    SourceFile,
)
from jera_fx_registry.series_catalog import SeriesCatalog


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def stable_key(prefix: str, *parts: object) -> str:
    payload = "||".join(str(part) for part in parts)
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()
    return f"{prefix}:{digest}"


def _json_default(value: Any) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Path):
        return value.as_posix()
    raise TypeError(f"Object of type {type(value)!r} is not JSON serializable")


def stable_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=_json_default).encode("utf-8")
    ).hexdigest()


def seed_series_catalog(session: Session, catalog: SeriesCatalog) -> None:
    for source_cfg in catalog.sources:
        source = session.get(Source, source_cfg.source_key)
        if source is None:
            source = Source(source_key=source_cfg.source_key)
            session.add(source)
        source_connection = {
            **source_cfg.connection,
            "source_type": source_cfg.source_type,
            "source_mode": source_cfg.source_mode,
            "automation_mode": source_cfg.automation_mode,
            "production_ingestion_approved": source_cfg.production_ingestion_approved,
            "required_configuration": source_cfg.required_configuration,
        }
        source.provider = source_cfg.provider
        source.base_url = source_cfg.base_url
        source.official = source_cfg.official
        source.release_metadata_behavior = source_cfg.release_metadata_behavior
        source.notes = source_cfg.notes
        source.connection = source_connection
        source.updated_at = utcnow()

    for series_cfg in catalog.series:
        definition = session.get(SeriesDefinition, series_cfg.series_key)
        if definition is None:
            definition = SeriesDefinition(series_key=series_cfg.series_key)
            session.add(definition)
        definition.source_key = series_cfg.source_key
        definition.source_code = series_cfg.source_code
        definition.provider = series_cfg.provider
        definition.frequency = series_cfg.frequency
        definition.units = series_cfg.units
        definition.release_metadata_behavior = series_cfg.release_metadata_behavior
        definition.transformation_rules = series_cfg.transformation_rules
        definition.display_metadata = series_cfg.display_metadata
        definition.canonical_scale_policy = series_cfg.canonical_scale_policy
        definition.is_placeholder = series_cfg.is_placeholder
        definition.updated_at = utcnow()

    session.commit()


def upsert_ingestion_run(
    session: Session,
    *,
    source_key: str,
    job_name: str,
    idempotency_key: str,
    parameters_json: dict[str, Any],
) -> IngestionRun:
    statement: Select[tuple[IngestionRun]] = select(IngestionRun).where(IngestionRun.idempotency_key == idempotency_key)
    run = session.execute(statement).scalar_one_or_none()
    if run is None:
        run = IngestionRun(
            ingestion_run_key=stable_key("ingestion-run", source_key, job_name, idempotency_key),
            source_key=source_key,
            job_name=job_name,
            status="running",
            parameters_json=parameters_json,
            idempotency_key=idempotency_key,
            started_at=utcnow(),
        )
        session.add(run)
    else:
        run.status = "running"
        run.parameters_json = parameters_json
        run.error_text = None
    return run


def upsert_source_file(
    session: Session,
    *,
    source_key: str,
    ingestion_run_key: str,
    logical_name: str,
    original_path: str,
    checksum_sha256: str,
    update_header: str | None,
    metadata_json: dict[str, Any],
    released_at: datetime | None = None,
) -> SourceFile:
    source_file_key = stable_key("source-file", source_key, checksum_sha256)
    source_file = session.get(SourceFile, source_file_key)
    if source_file is None:
        source_file = SourceFile(
            source_file_key=source_file_key,
            source_key=source_key,
            ingestion_run_key=ingestion_run_key,
            logical_name=logical_name,
            original_path=original_path,
            checksum_sha256=checksum_sha256,
            update_header=update_header,
            metadata_json=metadata_json,
            released_at=released_at,
        )
        session.add(source_file)
    else:
        source_file.ingestion_run_key = ingestion_run_key
        source_file.logical_name = logical_name
        source_file.original_path = original_path
        source_file.update_header = update_header
        source_file.metadata_json = metadata_json
        source_file.released_at = released_at
        source_file.ingested_at = utcnow()
    return source_file


def upsert_observation(
    session: Session,
    *,
    source_key: str,
    series_key: str,
    ingestion_run_key: str,
    source_file_key: str | None,
    observation_date,
    reference_month_end,
    value_numeric: float,
    units: str,
    scale_policy: str,
    released_at=None,
    vintage_timestamp=None,
    attributes_json: dict[str, Any] | None = None,
) -> Observation:
    observation_key = stable_key("observation", series_key, observation_date.isoformat(), scale_policy)
    observation = session.get(Observation, observation_key)
    if observation is None:
        observation = Observation(
            observation_key=observation_key,
            source_key=source_key,
            series_key=series_key,
            ingestion_run_key=ingestion_run_key,
            source_file_key=source_file_key,
            observation_date=observation_date,
            reference_month_end=reference_month_end,
            value_numeric=value_numeric,
            units=units,
            scale_policy=scale_policy,
            released_at=released_at,
            vintage_timestamp=vintage_timestamp,
            attributes_json=attributes_json or {},
        )
        session.add(observation)
    else:
        observation.ingestion_run_key = ingestion_run_key
        observation.source_file_key = source_file_key
        observation.reference_month_end = reference_month_end
        observation.value_numeric = value_numeric
        observation.units = units
        observation.released_at = released_at
        observation.vintage_timestamp = vintage_timestamp
        observation.attributes_json = attributes_json or {}
        observation.ingested_at = utcnow()
    return observation


def upsert_feature_set(
    session: Session,
    *,
    feature_set_key: str,
    name: str,
    version: str,
    description: str,
    scale_policy: str,
    definition_hash: str,
) -> FeatureSet:
    feature_set = session.get(FeatureSet, feature_set_key)
    if feature_set is None:
        feature_set = FeatureSet(
            feature_set_key=feature_set_key,
            name=name,
            version=version,
            description=description,
            scale_policy=scale_policy,
            definition_hash=definition_hash,
        )
        session.add(feature_set)
    else:
        feature_set.name = name
        feature_set.version = version
        feature_set.description = description
        feature_set.scale_policy = scale_policy
        feature_set.definition_hash = definition_hash
    return feature_set


def upsert_feature_value(
    session: Session,
    *,
    feature_set_key: str,
    series_key: str,
    feature_name: str,
    reference_month_end,
    observation_date,
    value_numeric: float,
    units: str,
    scale_policy: str,
    provenance_json: dict[str, Any],
) -> FeatureValue:
    feature_value_key = stable_key(
        "feature-value",
        feature_set_key,
        series_key,
        feature_name,
        reference_month_end.isoformat(),
        scale_policy,
    )
    feature_value = session.get(FeatureValue, feature_value_key)
    if feature_value is None:
        feature_value = FeatureValue(
            feature_value_key=feature_value_key,
            feature_set_key=feature_set_key,
            series_key=series_key,
            feature_name=feature_name,
            reference_month_end=reference_month_end,
            observation_date=observation_date,
            value_numeric=value_numeric,
            units=units,
            scale_policy=scale_policy,
            provenance_json=provenance_json,
        )
        session.add(feature_value)
    else:
        feature_value.observation_date = observation_date
        feature_value.value_numeric = value_numeric
        feature_value.units = units
        feature_value.scale_policy = scale_policy
        feature_value.provenance_json = provenance_json
    return feature_value


def upsert_client_snapshot(
    session: Session,
    *,
    snapshot_type: str,
    reference_month_end,
    feature_set_key: str,
    payload_json: dict[str, Any],
) -> ClientSnapshot:
    snapshot_key = stable_key("snapshot", snapshot_type, reference_month_end.isoformat())
    snapshot = session.get(ClientSnapshot, snapshot_key)
    if snapshot is None:
        snapshot = ClientSnapshot(
            snapshot_key=snapshot_key,
            snapshot_type=snapshot_type,
            reference_month_end=reference_month_end,
            feature_set_key=feature_set_key,
            payload_json=payload_json,
        )
        session.add(snapshot)
    else:
        snapshot.feature_set_key = feature_set_key
        snapshot.payload_json = payload_json
        snapshot.created_at = utcnow()
    return snapshot
