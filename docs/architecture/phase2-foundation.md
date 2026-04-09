# Phase 2 Foundation Architecture

This slice establishes the backend-only foundation for the JERA BRL/USD platform.

## Boundaries

- `meta` schema stores source registry, canonical series definitions, and ingestion run metadata.
- `raw` schema stores file manifests and source-native observations exactly as published by each provider.
- `curated` schema stores derived feature sets, feature values, and database-backed client snapshots.
- Prototype HTML files remain reference-only artifacts and are not used as application data sources.

## Phase 2 flow

1. Seed the series catalog from `config/series_catalog.yml`.
2. Ingest the local REER workbook into `raw.source_files` and `raw.observations`.
3. Backfill PTAX from Banco Central do Brasil into `raw.observations`.
4. Build canonical REER feature values using the `2020=100` normalization policy.
5. Build the first client snapshot from database-backed raw and curated layers.
6. Serve typed `GET /v1/meta/last-updated` and `GET /v1/client/overview` responses from curated snapshots only.

## Alignment rule

All monthly joins use `reference_month_end`. REER rows, curated PTAX monthly values, and all future monthly features must align to month-end before joins or regressions are built.
