from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Iterable

import httpx
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from jera_fx_api.db.models import Observation
from jera_fx_api.services import (
    stable_hash,
    upsert_feature_set,
    upsert_feature_value,
    upsert_ingestion_run,
    upsert_observation,
    utcnow,
)
from jera_fx_features.monthly_alignment import to_reference_month_end
from jera_fx_features.reer_normalization import RAW_SCALE_POLICY
from jera_fx_registry.series_catalog import SeriesCatalog

PTAX_MONTHLY_FEATURE_SET_KEY = "ptax_monthly_close_v1"


@dataclass
class BcbPtaxConnector:
    catalog: SeriesCatalog
    timeout_seconds: float = 30.0

    def fetch_period(self, start_date: date, end_date: date) -> list[dict[str, Any]]:
        source = self.catalog.get_source("bcb_ptax_odata")
        endpoint = source.connection["endpoint"]
        base_url = source.base_url.rstrip("/")
        url = f"{base_url}/{endpoint}(dataInicial=@dataInicial,dataFinalCotacao=@dataFinalCotacao)"
        params = {
            "@dataInicial": f"'{start_date.strftime('%m-%d-%Y')}'",
            "@dataFinalCotacao": f"'{end_date.strftime('%m-%d-%Y')}'",
            "$top": "10000",
            "$format": "json",
            "$select": "cotacaoCompra,cotacaoVenda,dataHoraCotacao",
        }
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.get(url, params=params)
            response.raise_for_status()
        payload = response.json()
        return payload.get("value", [])


def normalize_ptax_payload(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for record in records:
        timestamp = pd.Timestamp(record["dataHoraCotacao"])
        observation_date = timestamp.date()
        normalized.append(
            {
                "observation_date": observation_date,
                "reference_month_end": to_reference_month_end(observation_date),
                "buy": float(record["cotacaoCompra"]),
                "sell": float(record["cotacaoVenda"]),
                "released_at": timestamp.to_pydatetime(),
            }
        )
    return normalized


def backfill_ptax(
    session: Session,
    catalog: SeriesCatalog,
    *,
    start_date: date,
    end_date: date,
    connector: BcbPtaxConnector | None = None,
    records: Iterable[dict[str, Any]] | None = None,
) -> dict:
    connector = connector or BcbPtaxConnector(catalog)
    payload_records = list(records) if records is not None else connector.fetch_period(start_date, end_date)
    normalized_rows = normalize_ptax_payload(payload_records)
    source_key = catalog.get_series("ptax_usd_brl_sell").source_key
    idempotency_key = f"ptax:{start_date.isoformat()}:{end_date.isoformat()}:{stable_hash({'rows': normalized_rows})}"
    ingestion_run = upsert_ingestion_run(
        session,
        source_key=source_key,
        job_name="ptax_backfill",
        idempotency_key=idempotency_key,
        parameters_json={"start_date": start_date.isoformat(), "end_date": end_date.isoformat()},
    )

    buy_definition = catalog.get_series("ptax_usd_brl_buy")
    sell_definition = catalog.get_series("ptax_usd_brl_sell")
    row_count = 0
    for row in normalized_rows:
        upsert_observation(
            session,
            source_key=source_key,
            series_key=buy_definition.series_key,
            ingestion_run_key=ingestion_run.ingestion_run_key,
            source_file_key=None,
            observation_date=row["observation_date"],
            reference_month_end=row["reference_month_end"],
            value_numeric=row["buy"],
            units=buy_definition.units,
            scale_policy=RAW_SCALE_POLICY,
            released_at=row["released_at"],
            attributes_json={"source_code": buy_definition.source_code},
        )
        upsert_observation(
            session,
            source_key=source_key,
            series_key=sell_definition.series_key,
            ingestion_run_key=ingestion_run.ingestion_run_key,
            source_file_key=None,
            observation_date=row["observation_date"],
            reference_month_end=row["reference_month_end"],
            value_numeric=row["sell"],
            units=sell_definition.units,
            scale_policy=RAW_SCALE_POLICY,
            released_at=row["released_at"],
            attributes_json={"source_code": sell_definition.source_code},
        )
        row_count += 2

    ingestion_run.row_count = row_count
    ingestion_run.status = "completed"
    ingestion_run.completed_at = utcnow()
    session.commit()

    build_ptax_monthly_close_features(session, catalog)
    return {"row_count": row_count}


def build_ptax_monthly_close_features(session: Session, catalog: SeriesCatalog) -> None:
    feature_set = upsert_feature_set(
        session,
        feature_set_key=PTAX_MONTHLY_FEATURE_SET_KEY,
        name="PTAX monthly close",
        version="v1",
        description="Last available PTAX buy and sell observation in each calendar month.",
        scale_policy=RAW_SCALE_POLICY,
        definition_hash=stable_hash({"feature_set_key": PTAX_MONTHLY_FEATURE_SET_KEY, "policy": "last-available-daily-close"}),
    )

    for series_key in ("ptax_usd_brl_buy", "ptax_usd_brl_sell"):
        series_definition = catalog.get_series(series_key)
        statement = (
            select(Observation)
            .where(Observation.series_key == series_key)
            .order_by(Observation.observation_date.asc())
        )
        observations = session.execute(statement).scalars().all()
        if not observations:
            continue
        frame = pd.DataFrame(
            {
                "observation_date": [item.observation_date for item in observations],
                "reference_month_end": [item.reference_month_end for item in observations],
                "value_numeric": [item.value_numeric for item in observations],
            }
        )
        frame = frame.sort_values("observation_date")
        grouped = frame.groupby("reference_month_end", as_index=False).tail(1)
        for row in grouped.itertuples(index=False):
            upsert_feature_value(
                session,
                feature_set_key=feature_set.feature_set_key,
                series_key=series_key,
                feature_name="monthly_close",
                reference_month_end=row.reference_month_end,
                observation_date=row.observation_date,
                value_numeric=float(row.value_numeric),
                units=series_definition.units,
                scale_policy=RAW_SCALE_POLICY,
                provenance_json={"aggregation_policy": "last-available-daily-close"},
            )

    session.commit()

