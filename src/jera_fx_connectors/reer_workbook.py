from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path

import pandas as pd
from sqlalchemy.orm import Session

from jera_fx_api.services import upsert_ingestion_run, upsert_observation, upsert_source_file, utcnow
from jera_fx_features.monthly_alignment import to_reference_month_end
from jera_fx_features.reer_normalization import RAW_SCALE_POLICY
from jera_fx_registry.series_catalog import SeriesCatalog, SeriesConfig


def compute_sha256(path: Path | str) -> str:
    file_path = Path(path)
    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_update_header(value: str | None) -> datetime | None:
    if not value:
        return None
    candidate = value.replace("Updated:", "").strip()
    parsed = pd.to_datetime(candidate, dayfirst=True, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.to_pydatetime()


def parse_reer_series(workbook_path: Path | str, series_definition: SeriesConfig) -> dict:
    workbook = Path(workbook_path)
    rules = series_definition.transformation_rules["ingestion"]
    sheet_name = rules["workbook_sheet"]
    dataframe = pd.read_excel(workbook, sheet_name=sheet_name)
    update_header = str(dataframe.columns[0])
    source_code = series_definition.source_code
    if source_code not in dataframe.columns:
        raise KeyError(f"{source_code} not found in {sheet_name}")

    date_tokens = dataframe.iloc[:, 0].astype(str).str.extract(r"(\d{4})M(\d{2})")
    values = dataframe[source_code]
    rows: list[dict] = []
    for year_token, month_token, raw_value in zip(date_tokens[0], date_tokens[1], values, strict=False):
        if pd.isna(year_token) or pd.isna(month_token) or pd.isna(raw_value):
            continue
        period_start = pd.Timestamp(year=int(year_token), month=int(month_token), day=1)
        rows.append(
            {
                "observation_date": to_reference_month_end(period_start),
                "reference_month_end": to_reference_month_end(period_start),
                "value_numeric": float(raw_value),
            }
        )

    return {
        "source_code": source_code,
        "sheet_name": sheet_name,
        "update_header": update_header,
        "released_at": parse_update_header(update_header),
        "checksum_sha256": compute_sha256(workbook),
        "rows": rows,
    }


def ingest_reer_workbook(
    session: Session,
    catalog: SeriesCatalog,
    workbook_path: Path | str,
    series_keys: tuple[str, ...] = ("reer_120_br", "reer_51_br"),
) -> dict:
    workbook = Path(workbook_path)
    checksum_sha256 = compute_sha256(workbook)
    source_key = catalog.get_series(series_keys[0]).source_key
    idempotency_key = f"reer-workbook:{checksum_sha256}"
    ingestion_run = upsert_ingestion_run(
        session,
        source_key=source_key,
        job_name="reer_workbook_seed",
        idempotency_key=idempotency_key,
        parameters_json={"workbook_path": workbook.as_posix(), "series_keys": list(series_keys)},
    )

    parsed_series = [parse_reer_series(workbook, catalog.get_series(series_key)) for series_key in series_keys]
    update_headers = {item["sheet_name"]: item["update_header"] for item in parsed_series}
    released_at = max((item["released_at"] for item in parsed_series if item["released_at"] is not None), default=None)
    source_file = upsert_source_file(
        session,
        source_key=source_key,
        ingestion_run_key=ingestion_run.ingestion_run_key,
        logical_name=workbook.name,
        original_path=workbook.as_posix(),
        checksum_sha256=checksum_sha256,
        update_header="; ".join(sorted(update_headers.values())),
        metadata_json={"sheet_headers": update_headers},
        released_at=released_at,
    )

    row_count = 0
    for series_key, parsed in zip(series_keys, parsed_series, strict=True):
        series_definition = catalog.get_series(series_key)
        for row in parsed["rows"]:
            upsert_observation(
                session,
                source_key=source_key,
                series_key=series_key,
                ingestion_run_key=ingestion_run.ingestion_run_key,
                source_file_key=source_file.source_file_key,
                observation_date=row["observation_date"],
                reference_month_end=row["reference_month_end"],
                value_numeric=row["value_numeric"],
                units=series_definition.units,
                scale_policy=RAW_SCALE_POLICY,
                released_at=parsed["released_at"],
                attributes_json={
                    "sheet_name": parsed["sheet_name"],
                    "source_code": parsed["source_code"],
                    "update_header": parsed["update_header"],
                },
            )
            row_count += 1

    ingestion_run.row_count = row_count
    ingestion_run.status = "completed"
    ingestion_run.completed_at = utcnow()
    session.commit()

    return {
        "source_key": source_key,
        "row_count": row_count,
        "checksum_sha256": checksum_sha256,
        "update_headers": update_headers,
    }

