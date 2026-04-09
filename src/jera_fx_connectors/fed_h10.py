from __future__ import annotations

from csv import reader
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from io import StringIO
from typing import Any

import httpx
import pandas as pd
from sqlalchemy.orm import Session

from jera_fx_api.services import stable_hash, upsert_ingestion_run, upsert_observation, utcnow
from jera_fx_features.monthly_alignment import to_reference_month_end
from jera_fx_features.reer_normalization import RAW_SCALE_POLICY
from jera_fx_registry.series_catalog import SeriesCatalog


def _released_at_from_date(observation_date: date) -> datetime:
    return datetime.combine(observation_date, time.min, tzinfo=timezone.utc)


@dataclass
class FederalReserveH10Connector:
    catalog: SeriesCatalog
    timeout_seconds: float = 30.0

    def fetch_series(
        self,
        series_key: str,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> str:
        del start_date, end_date
        series_definition = self.catalog.get_series(series_key)
        source = self.catalog.get_source(series_definition.source_key)
        connection = source.connection
        params = {
            "rel": connection["rel"],
            "series": connection["package_series"],
            "lastobs": str(connection.get("lastobs", 10000)),
            "from": "",
            "to": "",
            "filetype": connection["filetype"],
            "label": connection["label"],
            "layout": connection["layout"],
            "type": connection["package_type"],
        }
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.get(source.base_url, params=params)
            response.raise_for_status()
            payload = response.text
            if not payload.strip() and params["lastobs"] != "10000":
                retry_params = dict(params)
                retry_params["lastobs"] = "10000"
                response = client.get(source.base_url, params=retry_params)
                response.raise_for_status()
                payload = response.text
        if not payload.strip():
            raise ValueError("Received an empty H.10 package response")
        return payload


def normalize_h10_csv(
    csv_content: str,
    *,
    series_definition,
) -> list[dict[str, Any]]:
    rows = list(reader(StringIO(csv_content)))
    if len(rows) < 6:
        raise ValueError("Unexpected H.10 CSV format")

    header_rows = rows[:5]
    data_frame = pd.read_csv(StringIO(csv_content), skiprows=5)
    value_field = series_definition.transformation_rules["ingestion"]["value_field"]
    if value_field not in data_frame.columns:
        raise ValueError(f"Expected H.10 column {value_field} not found in package")

    data_columns = list(data_frame.columns)[1:]
    description_map = {
        identifier: description
        for identifier, description in zip(data_columns, header_rows[0][1:], strict=False)
    }
    unique_identifier_map = {
        identifier: unique_identifier
        for identifier, unique_identifier in zip(data_columns, header_rows[4][1:], strict=False)
    }

    normalized: list[dict[str, Any]] = []
    for row in data_frame.to_dict(orient="records"):
        observation_date = pd.to_datetime(row["Time Period"]).date()
        value_numeric = pd.to_numeric(row[value_field], errors="coerce")
        if pd.isna(value_numeric):
            continue
        normalized.append(
            {
                "observation_date": observation_date,
                "reference_month_end": to_reference_month_end(observation_date),
                "value_numeric": float(value_numeric),
                "released_at": _released_at_from_date(observation_date),
                "attributes_json": {
                    "package_series": series_definition.transformation_rules["ingestion"]["package_series"],
                    "package_label": series_definition.transformation_rules["ingestion"]["package_label"],
                    "series_description": description_map.get(value_field),
                    "unique_identifier": unique_identifier_map.get(value_field),
                },
            }
        )
    return normalized


def backfill_fed_h10(
    session: Session,
    catalog: SeriesCatalog,
    *,
    series_key: str,
    start_date: date | None = None,
    end_date: date | None = None,
    connector: FederalReserveH10Connector | None = None,
    csv_content: str | None = None,
) -> dict[str, Any]:
    connector = connector or FederalReserveH10Connector(catalog)
    series_definition = catalog.get_series(series_key)
    payload = csv_content if csv_content is not None else connector.fetch_series(series_key, start_date=start_date, end_date=end_date)
    normalized_rows = normalize_h10_csv(payload, series_definition=series_definition)
    if start_date is not None:
        normalized_rows = [row for row in normalized_rows if row["observation_date"] >= start_date]
    if end_date is not None:
        normalized_rows = [row for row in normalized_rows if row["observation_date"] <= end_date]

    idempotency_key = (
        f"fed_h10:{series_key}:{start_date.isoformat() if start_date else 'none'}:"
        f"{end_date.isoformat() if end_date else 'none'}:{stable_hash({'rows': normalized_rows})}"
    )
    ingestion_run = upsert_ingestion_run(
        session,
        source_key=series_definition.source_key,
        job_name="fed_h10_backfill",
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
