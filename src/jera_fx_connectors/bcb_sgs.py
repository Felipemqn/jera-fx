from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from typing import Any, Iterable

import httpx
import pandas as pd
from sqlalchemy.orm import Session

from jera_fx_api.services import stable_hash, upsert_ingestion_run, upsert_observation, utcnow
from jera_fx_features.monthly_alignment import to_reference_month_end
from jera_fx_features.reer_normalization import RAW_SCALE_POLICY
from jera_fx_registry.series_catalog import SeriesCatalog


@dataclass
class BcbSgsConnector:
    catalog: SeriesCatalog
    timeout_seconds: float = 30.0

    def fetch_series(
        self,
        series_key: str,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[dict[str, Any]]:
        series_definition = self.catalog.get_series(series_key)
        source = self.catalog.get_source(series_definition.source_key)
        endpoint_template = source.connection["endpoint_template"]
        endpoint = endpoint_template.format(source_code=series_definition.source_code)
        url = f"{source.base_url.rstrip('/')}/{endpoint}"
        params: dict[str, str] = {"formato": "json"}
        if start_date is not None:
            params["dataInicial"] = start_date.strftime("%d/%m/%Y")
        if end_date is not None:
            params["dataFinal"] = end_date.strftime("%d/%m/%Y")

        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.get(url, params=params)
            response.raise_for_status()
        return response.json()


def _released_at_from_date(observation_date: date) -> datetime:
    return datetime.combine(observation_date, time.min, tzinfo=timezone.utc)


def normalize_sgs_payload(
    records: Iterable[dict[str, Any]],
    *,
    frequency: str,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for record in records:
        observation_date = pd.to_datetime(record["data"], dayfirst=True).date()
        normalized.append(
            {
                "observation_date": observation_date,
                "reference_month_end": to_reference_month_end(observation_date),
                "value_numeric": float(record["valor"]),
                "released_at": _released_at_from_date(observation_date) if frequency == "daily" else None,
                "attributes_json": {"source_date_value": record["data"]},
            }
        )
    return normalized


def backfill_sgs(
    session: Session,
    catalog: SeriesCatalog,
    *,
    series_key: str,
    start_date: date | None = None,
    end_date: date | None = None,
    connector: BcbSgsConnector | None = None,
    records: Iterable[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    connector = connector or BcbSgsConnector(catalog)
    series_definition = catalog.get_series(series_key)
    payload_records = list(records) if records is not None else connector.fetch_series(
        series_key,
        start_date=start_date,
        end_date=end_date,
    )
    normalized_rows = normalize_sgs_payload(payload_records, frequency=series_definition.frequency)
    idempotency_key = (
        f"sgs:{series_key}:{start_date.isoformat() if start_date else 'none'}:"
        f"{end_date.isoformat() if end_date else 'none'}:{stable_hash({'rows': normalized_rows})}"
    )
    ingestion_run = upsert_ingestion_run(
        session,
        source_key=series_definition.source_key,
        job_name="sgs_backfill",
        idempotency_key=idempotency_key,
        parameters_json={
            "series_key": series_key,
            "start_date": start_date.isoformat() if start_date else None,
            "end_date": end_date.isoformat() if end_date else None,
        },
    )

    row_count = 0
    for row in normalized_rows:
        attributes_json = dict(row["attributes_json"])
        attributes_json["source_code"] = series_definition.source_code
        upsert_observation(
            session,
            source_key=series_definition.source_key,
            series_key=series_key,
            ingestion_run_key=ingestion_run.ingestion_run_key,
            source_file_key=None,
            observation_date=row["observation_date"],
            reference_month_end=row["reference_month_end"],
            value_numeric=row["value_numeric"],
            units=series_definition.units,
            scale_policy=RAW_SCALE_POLICY,
            released_at=row["released_at"],
            attributes_json=attributes_json,
        )
        row_count += 1

    ingestion_run.row_count = row_count
    ingestion_run.status = "completed"
    ingestion_run.completed_at = utcnow()
    session.commit()
    return {"series_key": series_key, "row_count": row_count}
