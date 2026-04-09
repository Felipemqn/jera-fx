# Data Dictionary

## Schemas

### `meta.sources`

- Purpose: upstream source registry
- Key fields:
  - `source_key`
  - `provider`
  - `base_url`
  - `official`
  - `release_metadata_behavior`

### `meta.series_definitions`

- Purpose: canonical series registry loaded from `config/series_catalog.yml`
- Key fields:
  - `series_key`
  - `source_key`
  - `source_code`
  - `frequency`
  - `units`
  - `transformation_rules`
  - `display_metadata`
  - `canonical_scale_policy`

### `meta.ingestion_runs`

- Purpose: idempotent ingestion execution tracking
- Key fields:
  - `ingestion_run_key`
  - `source_key`
  - `job_name`
  - `idempotency_key`
  - `status`
  - `row_count`

### `raw.source_files`

- Purpose: manifest for file-backed sources
- Used in this slice by:
  - REER workbook seed
  - manual CDS file-drop ingestion
- Key fields:
  - `checksum_sha256`
  - `update_header`
  - `released_at`
  - `metadata_json`

### `raw.observations`

- Purpose: source-native observations
- Key fields:
  - `series_key`
  - `observation_date`
  - `reference_month_end`
  - `released_at`
  - `vintage_timestamp`
  - `ingested_at`
  - `value_numeric`
  - `units`
  - `scale_policy`

## Curated feature sets

### `reer_canonical_2020avg100_v1`

- Purpose: canonical REER normalization
- Scale policy: `canonical-2020avg100`
- Feature name: `canonical_value`

### `ptax_monthly_close_v1`

- Purpose: monthly PTAX close from daily PTAX
- Scale policy: `source-native`
- Feature name: `monthly_close`

## Curated snapshots

### `client_overview`

- Endpoint: `GET /v1/client/overview`
- Purpose: first database-backed client overview
- Includes:
  - latest PTAX spot
  - latest broad/narrow REER native values
  - latest broad/narrow REER canonical values
  - normalization metadata
  - last updated metadata

### `reer_bands`

- Endpoint: `GET /v1/client/reer-bands`
- Purpose: client-facing structural REER bands
- Includes:
  - broad/narrow native values
  - broad/narrow canonical values
  - percentile rank
  - p10 / p25 / p50 / p75 / p90 bands

### `ptax_monthly_history`

- Endpoint: `GET /v1/client/ptax-history`
- Purpose: curated PTAX monthly close history
- Includes:
  - monthly close points for buy and sell PTAX series
  - latest monthly close per PTAX series
  - latest raw observation freshness per PTAX series

### `source_freshness`

- Endpoint: `GET /v1/client/source-freshness`
- Purpose: source freshness and spot freshness status
- Includes:
  - latest observation state by source
  - latest PTAX spot freshness
  - latest PTAX monthly close freshness

### `spot_freshness`

- Purpose: internal snapshot for latest PTAX spot and monthly-close freshness
- Used by: `source_freshness`

### `domestic_macro_driver_snapshot`

- Purpose: latest domestic macro and Focus expectation inputs needed by the tactical-signal foundation
- Includes:
  - latest `sgs_selic_target_rate`
  - latest Focus BRL/USD median for `2026` to `2029`
  - latest Focus IPCA median for `2026` to `2029`

### `tactical_signal_inputs`

- Endpoint: `GET /v1/client/tactical-inputs`
- Purpose: signal-ready structural, domestic, and approved market-driver inputs without emitting a tactical score
- Includes:
  - latest PTAX sell spot
  - latest PTAX sell monthly close
  - latest broad and narrow REER in native and canonical scales
  - domestic macro snapshot inputs
  - approved market drivers currently wired from official/public sources or approved internal manual-batch sources
  - explicit missing driver keys
  - `signal_computable = false` until required missing drivers are available

### `tactical_driver_history`

- Endpoint: `GET /v1/client/tactical-drivers`
- Purpose: month-end aligned history for every required tactical driver
- Includes:
  - monthly history points by driver
  - native audit scale for PTAX and market drivers
  - canonical `2020=100` history for REER drivers
  - explicit missing-driver rows when a required source is still unavailable

### `tactical_driver_latest`

- Endpoint: `GET /v1/client/tactical-drivers`
- Purpose: latest values for every required tactical driver
- Includes:
  - latest raw observation or latest monthly-close payload where relevant
  - native and canonical REER values plus normalization factor
  - missing-driver reasons for unavailable required inputs

### `tactical_driver_freshness`

- Endpoint: `GET /v1/client/tactical-driver-freshness`
- Purpose: freshness metadata for every required tactical driver
- Includes:
  - latest observation date
  - latest `reference_month_end`
  - latest release and ingestion timestamps where available
  - explicit missing-driver reason metadata
  - source-status metadata:
    - `provider`
    - `source_type`
    - `source_mode`
    - `automation_mode`
    - `production_ingestion_approved`
    - `configured_for_runtime`
    - `required_configuration`

### `tactical_signal_components`

- Purpose: internal curated components snapshot used to assemble database-backed tactical inputs without computing a score
- Includes:
  - spot
  - PTAX monthly close
  - REER broad and narrow
  - domestic macro inputs
  - approved market drivers
  - methodology metadata

### `tactical_signal_readiness`

- Endpoint: `GET /v1/client/tactical-signal-readiness`
- Purpose: explicit driver availability and missing-driver state for tactical-signal readiness
- Includes:
  - available driver keys
  - missing driver keys
  - available driver freshness metadata
  - missing-driver reasons and notes
  - policy statement explaining why no tactical score is emitted yet

### `tactical_signal`

- Endpoint: `GET /v1/client/tactical-signal`
- Purpose: read-only tactical-signal status snapshot built entirely from curated database-backed inputs
- Includes:
  - status metadata
  - source coverage metadata
  - per-driver freshness metadata
  - per-driver automation-mode metadata
  - methodology/version metadata
  - no published score in this slice

## Tactical signal endpoint status

- `GET /v1/client/tactical-signal` is available only after:
  - the approved internal CDS file is ingested
  - tactical readiness becomes complete
  - the curated tactical signal snapshot is built
- The endpoint remains read-only and metadata-driven in this slice:
  - it does not fabricate fallback drivers
  - it does not fabricate proxy scores
  - it does not publish a tactical score yet
