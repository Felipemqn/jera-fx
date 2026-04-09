from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from typing import Any, Iterable
from urllib.parse import urlencode, quote

import httpx
import pandas as pd
from sqlalchemy.orm import Session

from jera_fx_api.services import stable_hash, upsert_ingestion_run, upsert_observation, utcnow
from jera_fx_features.monthly_alignment import to_reference_month_end
from jera_fx_features.reer_normalization import RAW_SCALE_POLICY
from jera_fx_registry.series_catalog import SeriesCatalog


@dataclass
class BcbFocusConnector:
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
        rules = series_definition.transformation_rules["ingestion"]
        entity_set = rules["entity_set"]
        query_params = {
            "$format": "json",
            "$top": "100000",
            "$orderby": f"{rules['observation_date_field']} asc",
        }
        filters = [
            f"{field} eq {value}" if isinstance(value, (int, float)) else f"{field} eq '{value}'"
            for field, value in rules.get("filters", {}).items()
        ]
        if filters:
            query_params["$filter"] = " and ".join(filters)

        url = f"{source.base_url.rstrip('/')}/{entity_set}"
        rows: list[dict[str, Any]] = []
        query_string = urlencode(query_params, quote_via=quote)
        with httpx.Client(timeout=self.timeout_seconds) as client:
            next_url: str | None = f"{url}?{query_string}"
            while next_url is not None:
                response = client.get(next_url)
                response.raise_for_status()
                payload = response.json()
                rows.extend(payload.get("value", []))
                next_url = payload.get("@odata.nextLink")
        return rows


def _date_to_release_timestamp(value: str) -> datetime:
    parsed = pd.to_datetime(value).date()
    return datetime.combine(parsed, time.min, tzinfo=timezone.utc)


def normalize_focus_payload(
    records: Iterable[dict[str, Any]],
    *,
    series_definition,
) -> list[dict[str, Any]]:
    rules = series_definition.transformation_rules["ingestion"]
    observation_field = rules["observation_date_field"]
    target_reference_field = rules["target_reference_field"]
    value_field = rules["value_field"]

    normalized: list[dict[str, Any]] = []
    for record in records:
        observation_date = pd.to_datetime(record[observation_field]).date()
        released_at = _date_to_release_timestamp(record[observation_field])
        normalized.append(
            {
                "observation_date": observation_date,
                "reference_month_end": to_reference_month_end(observation_date),
                "value_numeric": float(record[value_field]),
                "released_at": released_at,
                "vintage_timestamp": released_at,
                "attributes_json": {
                    "entity_set": rules["entity_set"],
                    "indicator": record.get("Indicador"),
                    "indicator_detail": record.get("IndicadorDetalhe"),
                    "target_reference": record.get(target_reference_field),
                    "value_field": value_field,
                    "numeroRespondentes": record.get("numeroRespondentes"),
                    "baseCalculo": record.get("baseCalculo"),
                },
            }
        )
    return normalized


def backfill_focus(
    session: Session,
    catalog: SeriesCatalog,
    *,
    series_key: str,
    start_date: date | None = None,
    end_date: date | None = None,
    connector: BcbFocusConnector | None = None,
    records: Iterable[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    connector = connector or BcbFocusConnector(catalog)
    series_definition = catalog.get_series(series_key)
    payload_records = list(records) if records is not None else connector.fetch_series(
        series_key,
        start_date=start_date,
        end_date=end_date,
    )
    normalized_rows = normalize_focus_payload(payload_records, series_definition=series_definition)
    if start_date is not None:
        normalized_rows = [row for row in normalized_rows if row["observation_date"] >= start_date]
    if end_date is not None:
        normalized_rows = [row for row in normalized_rows if row["observation_date"] <= end_date]
    idempotency_key = (
        f"focus:{series_key}:{start_date.isoformat() if start_date else 'none'}:"
        f"{end_date.isoformat() if end_date else 'none'}:{stable_hash({'rows': normalized_rows})}"
    )
    ingestion_run = upsert_ingestion_run(
        session,
        source_key=series_definition.source_key,
        job_name="focus_backfill",
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
            vintage_timestamp=row["vintage_timestamp"],
            attributes_json=attributes_json,
        )
        row_count += 1

    ingestion_run.row_count = row_count
    ingestion_run.status = "completed"
    ingestion_run.completed_at = utcnow()
    session.commit()
    return {"series_key": series_key, "row_count": row_count}
