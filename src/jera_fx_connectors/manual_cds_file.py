from __future__ import annotations

import csv
import hashlib
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from jera_fx_api.db.models import SourceFile
from jera_fx_api.services import (
    stable_hash,
    upsert_ingestion_run,
    upsert_observation,
    upsert_source_file,
    utcnow,
)
from jera_fx_features.monthly_alignment import to_reference_month_end
from jera_fx_features.reer_normalization import RAW_SCALE_POLICY
from jera_fx_registry.series_catalog import SeriesCatalog


MANUAL_CDS_FILENAME_PATTERN = re.compile(
    r"^(?P<symbol>[A-Z0-9=]+)_(?P<date>\d{4}-\d{2}-\d{2})\.csv$"
)


def _normalize_numeric(value: str) -> float:
    normalized = value.strip().replace(" ", "")
    if not normalized:
        raise ValueError("Numeric field is empty")
    if normalized.endswith("%"):
        normalized = normalized[:-1]
    if "," in normalized and "." in normalized:
        if normalized.rfind(",") > normalized.rfind("."):
            normalized = normalized.replace(".", "").replace(",", ".")
        else:
            normalized = normalized.replace(",", "")
    elif "," in normalized:
        normalized = normalized.replace(",", ".")
    return float(normalized)


def _parse_observation_date(value: str) -> date:
    raw_value = value.strip()
    for kwargs in (
        {"format": "%Y-%m-%d"},
        {"format": "%m/%d/%Y"},
        {"format": "%d/%m/%Y"},
        {"dayfirst": False},
        {"dayfirst": True},
    ):
        try:
            return pd.to_datetime(raw_value, **kwargs).date()
        except (TypeError, ValueError):
            continue
    raise ValueError(f"Unsupported CDS observation date format: {value!r}")


def _file_checksum_sha256(file_path: Path) -> str:
    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_manual_cds_csv(file_path: Path | str) -> tuple[list[dict[str, str]], list[str]]:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Manual CDS file not found: {path.as_posix()}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError("Manual CDS CSV has no header row")
        rows = [dict(row) for row in reader]
        return rows, list(reader.fieldnames)


def normalize_manual_cds_payload(
    records: Iterable[dict[str, str]],
    *,
    canonical_value_field: str,
) -> list[dict[str, Any]]:
    normalized_rows: list[dict[str, Any]] = []
    for record in records:
        observation_date = _parse_observation_date(record["Date"])
        normalized_rows.append(
            {
                "observation_date": observation_date,
                "reference_month_end": to_reference_month_end(observation_date),
                "value_numeric": _normalize_numeric(record[canonical_value_field]),
                "open_numeric": _normalize_numeric(record["Open"]),
                "high_numeric": _normalize_numeric(record["High"]),
                "low_numeric": _normalize_numeric(record["Low"]),
                "change_percent": _normalize_numeric(record["Change %"]),
                "raw_row": record,
            }
        )
    normalized_rows.sort(key=lambda item: item["observation_date"])
    return normalized_rows


def _match_filename_convention(filename: str) -> dict[str, str] | None:
    match = MANUAL_CDS_FILENAME_PATTERN.match(filename)
    if match is None:
        return None
    return {"symbol": match.group("symbol"), "file_date": match.group("date")}


def validate_manual_cds_file(
    catalog: SeriesCatalog,
    *,
    file_path: Path | str,
    series_key: str = "cds_brazil_5y",
    session: Session | None = None,
) -> dict[str, Any]:
    """Inspect a manual CDS file without persisting any data.

    Returns a structured report with checksum, row count, date range,
    column/naming compliance, and (if a session is provided) whether the
    file has already been ingested.
    """
    series_definition = catalog.get_series(series_key)
    source_definition = catalog.get_source(series_definition.source_key)
    source_connection = source_definition.connection
    expected_columns: list[str] = list(source_connection["expected_columns"])
    canonical_value_field: str = source_connection["canonical_value_field"]
    expected_symbol: str = source_connection["source_symbol"]

    path = Path(file_path)
    report: dict[str, Any] = {
        "series_key": series_key,
        "source_key": source_definition.source_key,
        "file_path": path.as_posix(),
        "file_exists": path.exists(),
        "expected_columns": expected_columns,
        "expected_symbol": expected_symbol,
        "naming_convention_ok": False,
        "naming_convention_warnings": [],
        "columns_ok": False,
        "missing_columns": [],
        "row_count": 0,
        "checksum_sha256": None,
        "observation_date_range": None,
        "already_ingested": None,
        "errors": [],
    }

    if not path.exists():
        report["errors"].append(f"file not found: {path.as_posix()}")
        return report

    # Filename convention check (warning only, does not block ingestion).
    filename_parts = _match_filename_convention(path.name)
    if filename_parts is None:
        report["naming_convention_warnings"].append(
            f"filename {path.name!r} does not match expected pattern "
            f"'<SYMBOL>_YYYY-MM-DD.csv' (e.g. 'BRGV5YUSAC=R_2026-04-07.csv')"
        )
    else:
        report["naming_convention_ok"] = True
        report["filename_symbol"] = filename_parts["symbol"]
        report["filename_file_date"] = filename_parts["file_date"]
        if filename_parts["symbol"] != expected_symbol:
            report["naming_convention_warnings"].append(
                f"filename symbol {filename_parts['symbol']!r} differs from catalog symbol "
                f"{expected_symbol!r}"
            )

    try:
        raw_records, field_names = read_manual_cds_csv(path)
    except Exception as exc:  # pragma: no cover - defensive
        report["errors"].append(f"failed to read CSV: {exc}")
        return report

    missing_columns = [column for column in expected_columns if column not in field_names]
    report["columns_ok"] = not missing_columns
    report["missing_columns"] = missing_columns
    if missing_columns:
        report["errors"].append(
            f"missing expected columns: {', '.join(missing_columns)}"
        )

    try:
        normalized = normalize_manual_cds_payload(
            raw_records, canonical_value_field=canonical_value_field
        )
    except Exception as exc:
        report["errors"].append(f"failed to normalize rows: {exc}")
        return report

    report["row_count"] = len(normalized)
    report["checksum_sha256"] = _file_checksum_sha256(path)
    if normalized:
        report["observation_date_range"] = {
            "min": normalized[0]["observation_date"].isoformat(),
            "max": normalized[-1]["observation_date"].isoformat(),
        }

    if session is not None and report["checksum_sha256"] is not None:
        statement = select(SourceFile).where(
            SourceFile.source_key == source_definition.source_key,
            SourceFile.checksum_sha256 == report["checksum_sha256"],
        )
        existing = session.execute(statement).scalar_one_or_none()
        report["already_ingested"] = existing is not None
        if existing is not None:
            report["existing_source_file_key"] = existing.source_file_key

    return report


@dataclass
class ManualCdsFileConnector:
    catalog: SeriesCatalog

    def ingest_file(
        self,
        session: Session,
        *,
        file_path: Path | str,
        series_key: str = "cds_brazil_5y",
        operator: str | None = None,
        source_note: str | None = None,
    ) -> dict[str, Any]:
        series_definition = self.catalog.get_series(series_key)
        source_definition = self.catalog.get_source(series_definition.source_key)
        source_connection = source_definition.connection
        expected_columns = source_connection["expected_columns"]
        canonical_value_field = source_connection["canonical_value_field"]

        path = Path(file_path)
        raw_records, field_names = read_manual_cds_csv(path)
        missing_columns = [column for column in expected_columns if column not in field_names]
        if missing_columns:
            raise ValueError(
                f"Manual CDS CSV is missing expected columns: {', '.join(missing_columns)}"
            )
        checksum_sha256 = _file_checksum_sha256(path)
        normalized_rows = normalize_manual_cds_payload(
            raw_records,
            canonical_value_field=canonical_value_field,
        )
        filename_parts = _match_filename_convention(path.name)
        idempotency_key = f"manual-cds-file:{series_key}:{checksum_sha256}"
        parameters_json: dict[str, Any] = {
            "series_key": series_key,
            "file_path": path.as_posix(),
            "checksum_sha256": checksum_sha256,
            "source_mode": source_definition.source_mode,
            "automation_mode": source_definition.automation_mode,
            "source_symbol": source_connection["source_symbol"],
        }
        if operator is not None:
            parameters_json["operator"] = operator
        if source_note is not None:
            parameters_json["source_note"] = source_note
        if filename_parts is not None:
            parameters_json["filename_file_date"] = filename_parts["file_date"]
        ingestion_run = upsert_ingestion_run(
            session,
            source_key=source_definition.source_key,
            job_name="manual_cds_file_ingest",
            idempotency_key=idempotency_key,
            parameters_json=parameters_json,
        )
        metadata_json: dict[str, Any] = {
            "source_mode": source_definition.source_mode,
            "automation_mode": source_definition.automation_mode,
            "source_symbol": source_connection["source_symbol"],
            "file_format": source_connection["file_format"],
            "canonical_value_field": canonical_value_field,
            "expected_columns": expected_columns,
            "row_count": len(normalized_rows),
            "ingested_via": "manual_cds_file_connector",
            "operator": operator,
            "source_note": source_note,
            "filename_convention_ok": filename_parts is not None,
        }
        if filename_parts is not None:
            metadata_json["filename_symbol"] = filename_parts["symbol"]
            metadata_json["filename_file_date"] = filename_parts["file_date"]
        source_file = upsert_source_file(
            session,
            source_key=source_definition.source_key,
            ingestion_run_key=ingestion_run.ingestion_run_key,
            logical_name=path.name,
            original_path=path.as_posix(),
            checksum_sha256=checksum_sha256,
            update_header=None,
            released_at=None,
            metadata_json=metadata_json,
        )

        for row in normalized_rows:
            upsert_observation(
                session,
                source_key=source_definition.source_key,
                series_key=series_definition.series_key,
                ingestion_run_key=ingestion_run.ingestion_run_key,
                source_file_key=source_file.source_file_key,
                observation_date=row["observation_date"],
                reference_month_end=row["reference_month_end"],
                value_numeric=row["value_numeric"],
                units=series_definition.units,
                scale_policy=RAW_SCALE_POLICY,
                released_at=None,
                attributes_json={
                    "source_code": series_definition.source_code,
                    "source_symbol": source_connection["source_symbol"],
                    "source_mode": source_definition.source_mode,
                    "automation_mode": source_definition.automation_mode,
                    "canonical_value_field": canonical_value_field,
                    "raw_row": row["raw_row"],
                    "parsed_fields": {
                        "open": row["open_numeric"],
                        "high": row["high_numeric"],
                        "low": row["low_numeric"],
                        "change_percent": row["change_percent"],
                    },
                },
            )

        ingestion_run.row_count = len(normalized_rows)
        ingestion_run.status = "completed"
        ingestion_run.completed_at = utcnow()
        session.commit()
        return {
            "series_key": series_key,
            "source_key": source_definition.source_key,
            "file_path": path.as_posix(),
            "logical_name": path.name,
            "checksum_sha256": checksum_sha256,
            "row_count": len(normalized_rows),
            "latest_observation_date": normalized_rows[-1]["observation_date"].isoformat()
            if normalized_rows
            else None,
        }


def ingest_manual_cds_file(
    session: Session,
    catalog: SeriesCatalog,
    *,
    file_path: Path | str,
    series_key: str = "cds_brazil_5y",
    operator: str | None = None,
    source_note: str | None = None,
) -> dict[str, Any]:
    connector = ManualCdsFileConnector(catalog)
    return connector.ingest_file(
        session,
        file_path=file_path,
        series_key=series_key,
        operator=operator,
        source_note=source_note,
    )
