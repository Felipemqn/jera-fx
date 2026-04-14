# Scenario Engine v1 — Methodology

**Version:** `scenario-engine-v1`
**Module:** `src/jera_fx_features/scenario_engine.py`
**Last updated:** 2026-04-13

---

## 1. Purpose

The scenario engine produces reproducible BRL/USD paths across standard
horizons (1Y, 3Y, 5Y, 10Y) for a set of named scenarios. Each scenario
is defined by explicit driver assumptions. No paths are hardcoded.

## 2. Design

- **Assumptions are data** — every scenario stores its DXY, CDS, carry,
  commodity, and productivity assumptions alongside the computed paths.
- **Horizon-dependent betas** — short-term paths are dominated by DXY/CDS;
  long-term paths give more weight to productivity and structural factors.
- **Probability-weighted expected path** — the center line of the fan
  chart is the weighted average across all scenarios.

## 3. Scenario definitions (v1)

| Key | Label | Probability | Terminal direction |
|---|---|---|---|
| `benign` | Reforma + dolar mais fraco | 25% | BRL strong |
| `base` | Base / premio sticky | 50% | BRL moderate weakness |
| `fiscal_stress` | Premio fiscal | 15% | BRL weak |
| `superdollar` | Super-dolar / EUA excepcional | 10% | BRL very weak |

## 4. Fair value formula

For each scenario at each horizon:

```
fair = anchor
     x (DXY / 100) ^ beta_dxy
     x exp(beta_cds x cds_shock_bps)
     x exp(beta_carry x carry_pct)
     x exp(beta_comm x commodity_shock_pct)
     x exp(beta_prod x productivity_gap_pct)
```

## 5. Horizon betas

| Horizon | beta_dxy | beta_cds | beta_carry | beta_comm | beta_prod |
|---|---|---|---|---|---|
| 1Y | 0.55 | 0.0012 | -0.04 | -0.003 | 0.00 |
| 3Y | 0.45 | 0.0010 | -0.03 | -0.004 | 0.02 |
| 5Y | 0.35 | 0.0008 | -0.02 | -0.005 | 0.04 |
| 10Y | 0.20 | 0.0005 | -0.01 | -0.006 | 0.08 |

Negative betas mean the driver is BRL-supportive (higher carry or
commodity terms-of-trade strengthens BRL, lowering the fair value).

## 6. Anchor

For v1, the anchor is the latest PTAX spot. In future versions, a
REER-implied structural fair value may replace it.

## 7. Fan chart

At each horizon, the fan chart provides:
- **min/max** across all scenarios
- **expected** = probability-weighted average
- **per-scenario values**

## 8. API endpoint

`GET /v1/client/scenarios` returns the full scenario set including
assumptions, paths, expected path, and fan chart.

## 9. Reproducibility

The result is fully reproducible from:
1. The anchor value (from curated snapshot).
2. The scenario definitions (deterministic, versioned).
3. The horizon betas (constants in `scenario_engine.py`).

No random state or training artifacts are involved.
