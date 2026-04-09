# Tactical-Signal Foundation

## Included in this slice

- Structural inputs:
  - `reer_120_br`
  - `reer_51_br`
- Spot inputs:
  - `ptax_usd_brl_sell`
  - PTAX monthly close history derived from daily PTAX
- Domestic macro inputs:
  - `sgs_selic_target_rate`
  - Focus BRL/USD median expectations for `2026`, `2027`, `2028`, and `2029`
  - Focus IPCA median expectations for `2026`, `2027`, `2028`, and `2029`
- Approved market inputs now wired from live sources:
  - `broad_usd_index` from Federal Reserve H.10 (`JRXWTFB_N.B`)
  - `commodity_terms_of_trade` from BCB SGS `29042` (`IC-Br` in US dollars)
- Approved market input wired from an internal manual batch source:
  - `cds_brazil_5y` from the approved internal CSV file drop `BRGV5YUSAC=R`

## Not yet included

- A published tactical score
  - current status: the backend now supports full source coverage and a read-only tactical signal status snapshot, but it still does not publish a numeric tactical score

## Readiness policy

- This slice does not compute or publish a tactical signal score.
- `GET /v1/client/tactical-inputs` exposes only database-backed signal-ready components.
- `GET /v1/client/tactical-signal-readiness` reports which required drivers are present vs missing.
- `GET /v1/client/tactical-drivers` exposes the latest values and month-end history for all required drivers.
- `GET /v1/client/tactical-driver-freshness` exposes per-driver freshness and missing-driver reasons.
- `GET /v1/client/tactical-signal` becomes available only after every required driver has:
  - a registered source in the catalog
  - an approved connector
  - ingested observations in the database
- The CDS source is explicitly manual:
  - source mode: `approved_internal_file_drop`
  - automation mode: `manual_batch`
  - provenance is file-based, not API-based, and not live

## Why this is intentional

- The backend now has full required driver coverage from approved public sources plus an approved internal manual batch source for CDS.
- The new tactical signal endpoint is still metadata-driven in this slice and does not fabricate a numeric score.
- The readiness, tactical-driver, and tactical-signal APIs surface source type, source mode, automation mode, approval state, and freshness metadata explicitly.
- This foundation keeps the backend truthful while making a future scored methodology slice explicit.
