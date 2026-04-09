from __future__ import annotations

import math

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from jera_fx_api.db.models import FeatureValue, Observation
from jera_fx_features.reer_canonical import REER_CANONICAL_FEATURE_SET_KEY
from jera_fx_features.reer_normalization import CANONICAL_SCALE_POLICY, normalize_reer_to_2020_average_100


def test_reer_latest_value_proof(seeded_session: Session) -> None:
    broad = seeded_session.execute(
        select(Observation)
        .where(Observation.series_key == "reer_120_br")
        .order_by(Observation.observation_date.desc())
    ).scalars().first()
    narrow = seeded_session.execute(
        select(Observation)
        .where(Observation.series_key == "reer_51_br")
        .order_by(Observation.observation_date.desc())
    ).scalars().first()

    assert broad is not None
    assert narrow is not None
    assert broad.observation_date.isoformat() == "2026-02-28"
    assert narrow.observation_date.isoformat() == "2026-02-28"
    assert broad.value_numeric == 76.06819061
    assert narrow.value_numeric == 73.81400196


def test_reer_canonical_normalization_uses_2020_average(seeded_session: Session) -> None:
    broad_raw_rows = seeded_session.execute(
        select(Observation)
        .where(Observation.series_key == "reer_120_br")
        .order_by(Observation.observation_date.asc())
    ).scalars().all()
    broad_raw_series = pd.Series(
        [row.value_numeric for row in broad_raw_rows],
        index=pd.to_datetime([row.observation_date for row in broad_raw_rows]),
    )
    normalization = normalize_reer_to_2020_average_100(broad_raw_series, anchor_year=2020)

    broad_feature = seeded_session.execute(
        select(FeatureValue)
        .where(
            FeatureValue.feature_set_key == REER_CANONICAL_FEATURE_SET_KEY,
            FeatureValue.series_key == "reer_120_br",
        )
        .order_by(FeatureValue.reference_month_end.desc())
    ).scalars().first()

    assert broad_feature is not None
    assert broad_feature.scale_policy == CANONICAL_SCALE_POLICY
    assert math.isclose(
        broad_feature.value_numeric,
        float(normalization.normalized.iloc[-1]),
        rel_tol=1e-12,
    )
    assert math.isclose(
        broad_feature.provenance_json["scale_factor"],
        normalization.scale_factor,
        rel_tol=1e-12,
    )
