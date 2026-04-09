from __future__ import annotations

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from jera_fx_api.db.models import Observation
from jera_fx_api.services import stable_hash, upsert_feature_set, upsert_feature_value
from jera_fx_features.reer_normalization import CANONICAL_SCALE_POLICY, normalize_reer_to_2020_average_100
from jera_fx_registry.series_catalog import SeriesCatalog

REER_CANONICAL_FEATURE_SET_KEY = "reer_canonical_2020avg100_v1"


def build_reer_canonical_features(
    session: Session,
    catalog: SeriesCatalog,
    series_keys: tuple[str, ...] = ("reer_120_br", "reer_51_br"),
) -> None:
    feature_set = upsert_feature_set(
        session,
        feature_set_key=REER_CANONICAL_FEATURE_SET_KEY,
        name="REER canonical normalization",
        version="v1",
        description="Canonical REER normalization using 2020 calendar-year average = 100.",
        scale_policy=CANONICAL_SCALE_POLICY,
        definition_hash=stable_hash({"feature_set_key": REER_CANONICAL_FEATURE_SET_KEY, "anchor_year": 2020}),
    )

    for series_key in series_keys:
        series_definition = catalog.get_series(series_key)
        statement = (
            select(Observation)
            .where(Observation.series_key == series_key)
            .order_by(Observation.observation_date.asc())
        )
        observations = session.execute(statement).scalars().all()
        if not observations:
            continue

        native_series = pd.Series(
            data=[item.value_numeric for item in observations],
            index=pd.to_datetime([item.observation_date for item in observations]),
            name=series_key,
        )
        normalization = normalize_reer_to_2020_average_100(native_series, anchor_year=2020)
        for observation, normalized_value in zip(observations, normalization.normalized.tolist(), strict=True):
            upsert_feature_value(
                session,
                feature_set_key=feature_set.feature_set_key,
                series_key=series_key,
                feature_name="canonical_value",
                reference_month_end=observation.reference_month_end,
                observation_date=observation.observation_date,
                value_numeric=float(normalized_value),
                units=series_definition.units,
                scale_policy=CANONICAL_SCALE_POLICY,
                provenance_json={
                    "source_scale_policy": observation.scale_policy,
                    "scale_factor": normalization.scale_factor,
                    "anchor_year": normalization.anchor_year,
                },
            )

    session.commit()

