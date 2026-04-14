# Tactical Signal v1 — Methodology

**Version:** `tactical-signal-score-v1`
**Status:** Production v1
**Module:** `src/jera_fx_features/tactical_score.py`
**Last updated:** 2026-04-13

---

## 1. Purpose

The tactical signal provides a single composite score summarizing whether
the BRL/USD rate appears cheap, neutral, or expensive relative to its
structural and market drivers. It is designed for:

- **Client Mode:** headline signal with regime label and methodology transparency.
- **Investment Mode:** driver attribution, z-score decomposition, and input to
  the scenario lab.

## 2. Design principles

1. **Transparent** — every weight, threshold, and z-score window is a named
   constant. No hidden parameters.
2. **Deterministic** — identical curated data produces identical scores.
3. **Governed** — the API response always includes `methodology_version`,
   weights, and driver contributions.
4. **Fail-safe** — if any required driver has insufficient history, the
   score is `null` and status is `degraded`. No invented numbers.

## 3. Score definition

- **Range:** -100 to +100.
- **Negative** = BRL looks cheap / favorable for long BRL.
- **Positive** = BRL looks expensive or under stress / adverse for BRL.
- **Zero** = neutral.

## 4. Factors and weights

| Factor | Driver key | Weight | Sign convention |
|---|---|---|---|
| REER broad | `reer_120_br` | 20% | High REER = BRL expensive = positive |
| REER narrow | `reer_51_br` | 10% | High REER = BRL expensive = positive |
| Broad USD (DXY) | `broad_usd_index` | 20% | Strong USD = positive |
| Brazil 5Y CDS | `cds_brazil_5y` | 15% | High CDS = risk = positive |
| Commodity ToT | `commodity_terms_of_trade` | 15% | High commodity = BRL supportive = **inverted** |
| Selic target | `sgs_selic_target_rate` | 10% | High Selic = flow support = **inverted** |
| Focus FX median | `focus_exchange_rate` | 10% | High median = expected depreciation = positive |

**Total: 100%**

Inverted drivers: a high reading is BRL-supportive, so the z-score sign
is flipped before weighting.

## 5. Z-score computation

For each driver:

1. Take the full monthly history from the curated driver history snapshot.
2. Compute `mean` and `std` over the entire available history.
3. Compute z-score: `z = (latest - mean) / std`, capped at +/-4.
4. If the driver is inverted, flip the sign: `z = -z`.
5. Weighted contribution: `z * weight * 25.0`
   (scaling factor: z=4 at weight=1.0 maps to score=100).

## 6. Focus FX aggregation

The Focus Exchange Rate series exists per horizon year (2026, 2027, 2028,
2029). For the tactical signal, these are aggregated into a single factor
by averaging across horizons at each time step.

## 7. Minimum history requirement

Each driver must have at least **12 monthly observations** to produce a
valid z-score. If any required driver has fewer points, the entire score
degrades. This prevents unstable readings from short histories.

## 8. Regime classification

| Score range | Regime label |
|---|---|
| score <= -30 | `brl-favorable` |
| -30 < score <= -10 | `mildly-brl-favorable` |
| -10 < score <= 10 | `neutral` |
| 10 < score <= 30 | `mildly-brl-adverse` |
| score > 30 | `brl-adverse` |

## 9. Missing data policy

- If any `required_for_signal=true` driver is missing from the database,
  the signal reports `status: missing-drivers` and `score: null`.
- If all drivers are present but any has fewer than 12 monthly points,
  the signal reports `status: degraded` and `score: null`.
- The API never returns an invented score. Degraded state is explicit.

## 10. API response contract

`GET /v1/client/tactical-signal` returns:

- `status`: `"scored"` | `"degraded"` | `"missing-drivers"`
- `score`: float | null
- `regime`: string | null
- `methodology.version`: `"tactical-signal-score-v1"`
- `methodology.definition.weights`: the full weight map
- `driver_contributions[]`: per-driver z-score, weight, contribution
- `coverage`: which drivers were available, insufficient, or missing
- `degraded_reasons[]`: human-readable reasons when score is null

## 11. Upgrade path

- v1 is a **deterministic factor z-score model** — no ML, no estimation.
- Future ML models (Phase 6: `feat/ml-research-v1`) will be benchmarked
  against v1 as the baseline.
- Promotion of any ML model to client-facing score requires explicit
  approval and a new methodology version.

## 12. Reproducibility

The score is fully reproducible from:

1. The curated driver history snapshot (`tactical_driver_history`).
2. The methodology version and constants in `tactical_score.py`.
3. The `methodology.definition` block in the API response.

No external state, random seeds, or training artifacts are involved.
