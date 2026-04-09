# Source Map

## Phase 2 sources

### Local REER seed

- Source key: `bis_reer_local_seed`
- Provider: BIS/Bruegel local workbook seed
- Runtime role: seed only
- Connector: `src/jera_fx_connectors/reer_workbook.py`
- Raw storage:
  - `raw.source_files`
  - `raw.observations`
- Supported series:
  - `reer_120_br`
  - `reer_51_br`

### BCB PTAX OData

- Source key: `bcb_ptax_odata`
- Provider: Banco Central do Brasil
- Connector: `src/jera_fx_connectors/bcb_ptax.py`
- Raw storage: `raw.observations`
- Curated storage:
  - `curated.feature_values` via `ptax_monthly_close_v1`
  - `curated.client_snapshots` via `ptax_monthly_history` and `source_freshness`
- Supported series:
  - `ptax_usd_brl_buy`
  - `ptax_usd_brl_sell`

### BCB SGS

- Source key: `bcb_sgs_api`
- Provider: Banco Central do Brasil
- Connector: `src/jera_fx_connectors/bcb_sgs.py`
- Raw storage: `raw.observations`
- Supported series in this slice:
  - `sgs_selic_target_rate` (`432`)
  - `sgs_ipca_12m` (`13522`)
  - `commodity_terms_of_trade` (`29042`, IC-Br in US dollars)

### BCB Focus / Expectativas

- Source key: `bcb_expectativas_odata`
- Provider: Banco Central do Brasil
- Connector: `src/jera_fx_connectors/bcb_focus.py`
- Raw storage: `raw.observations`
- Supported series in this slice:
  - `focus_exchange_rate_median_2026`
  - `focus_exchange_rate_median_2027`
  - `focus_exchange_rate_median_2028`
  - `focus_exchange_rate_median_2029`
  - `focus_ipca_median_2026`
  - `focus_ipca_median_2027`
  - `focus_ipca_median_2028`
  - `focus_ipca_median_2029`

### Federal Reserve H.10

- Source key: `fed_h10_datadownload`
- Provider: Board of Governors of the Federal Reserve System
- Connector: `src/jera_fx_connectors/fed_h10.py`
- Raw storage: `raw.observations`
- Supported series in this slice:
  - `broad_usd_index` (`JRXWTFB_N.B`)

### Approved internal CDS file drop

- Source key: `approved_internal_cds_file_drop`
- Provider: `internal_manual_upload`
- Source mode: `approved_internal_file_drop`
- Automation mode: `manual_batch`
- Connector: `src/jera_fx_connectors/manual_cds_file.py`
- Raw storage:
  - `raw.source_files`
  - `raw.observations`
- Supported series in this slice:
  - `cds_brazil_5y` (`BRGV5YUSAC=R`)
- File handling:
  - expected production drop path: `data/raw/cds/BRGV5YUSAC=R_2026-04-07.csv`
  - expected columns: `Date`, `Price`, `Open`, `High`, `Low`, `Change %`
  - canonical value field: `Price`
  - this source is file-based, not API-based, and not live

## Tactical signal foundation coverage

- Included now:
  - `reer_120_br`
  - `reer_51_br`
  - `ptax_usd_brl_sell`
  - `sgs_selic_target_rate`
  - Focus exchange-rate medians for `2026` to `2029`
  - Focus IPCA medians for `2026` to `2029`
  - `broad_usd_index`
  - `commodity_terms_of_trade`
  - `cds_brazil_5y`
- Tactical score status in this slice:
  - no score is emitted
  - readiness remains false until every required driver has an approved source or approved internal manual-batch source with ingested observations
  - the CDS path is now governed as an approved internal manual file drop rather than a live vendor/API integration
  - `GET /v1/client/tactical-signal` is only materialized after the CDS file is ingested and the curated tactical signal snapshot is built

## Vintage handling assumptions

### SGS

- SGS payloads expose observation dates and values, but not an explicit release timestamp.
- Phase 2 stores the original date as `observation_date`.
- `reference_month_end` is derived from `observation_date`.
- `released_at` is populated only for daily SGS series when the observation date is used as the best available release-date proxy.

### Focus / Expectativas

- The OData payload exposes `Data` as the survey snapshot date and `DataReferencia` as the target forecast year.
- Phase 2 uses `Data` as the raw observation date and as the vintage date proxy.
- `reference_month_end` is derived from `Data`, not from `DataReferencia`.
- `DataReferencia` is preserved in `attributes_json` for downstream modeling.
- Focus annual series are filtered with `baseCalculo = 0` in this slice to avoid duplicate same-day rows from alternative calculation bases.

### Federal Reserve H.10

- The H.10 package is fetched from the Federal Reserve Board Data Download Program, not from FRED or ALFRED.
- This slice stores the published daily observation date as both `observation_date` and the best available `released_at` proxy.
- `reference_month_end` is derived from the daily observation date for month-end joins.
- The connector skips non-numeric package rows such as `ND`.
- The H.10 package request uses a bounded `lastobs` size to avoid the empty-response behavior seen with oversized requests.

### Manual CDS file drop

- The CSV file carries observation dates but no explicit release timestamp.
- Phase 2 stores `released_at = null` and always records `ingested_at`.
- `reference_month_end` is derived from each daily `Date` value.
- The original CSV row is preserved in `raw.observations.attributes_json.raw_row`.
