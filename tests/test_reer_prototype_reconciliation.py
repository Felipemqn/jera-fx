from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from jera_fx_api.db.models import FeatureValue, Observation
from jera_fx_features.reer_canonical import REER_CANONICAL_FEATURE_SET_KEY
from jera_fx_features.reer_reconciliation import reconcile_prototype_reer


def test_prototype_reer_is_reference_only(seeded_session: Session) -> None:
    broad_raw = seeded_session.execute(
        select(Observation)
        .where(Observation.series_key == "reer_120_br")
        .order_by(Observation.observation_date.desc())
    ).scalars().first()
    broad_canonical = seeded_session.execute(
        select(FeatureValue)
        .where(
            FeatureValue.feature_set_key == REER_CANONICAL_FEATURE_SET_KEY,
            FeatureValue.series_key == "reer_120_br",
        )
        .order_by(FeatureValue.reference_month_end.desc())
    ).scalars().first()

    assert broad_raw is not None
    assert broad_canonical is not None
    reconciliation = reconcile_prototype_reer(
        "apps/reference-ui/client/JERA_BRL_USD_Scenario_Frame_Client.html",
        latest_native_value=broad_raw.value_numeric,
        latest_canonical_value=broad_canonical.value_numeric,
        latest_reference_month_end=broad_raw.reference_month_end.isoformat(),
    )

    assert reconciliation.status == "legacy_reference_only"
    assert "must not be treated as source data" in reconciliation.note
    assert reconciliation.prototype_current_value != reconciliation.source_native_latest_value
