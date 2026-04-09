# Local Setup Runbook

## Prerequisites

- Python 3.12+
- PostgreSQL 16+ with a database available for `DATABASE_URL`
- Optional: Docker if you prefer to run PostgreSQL in a local container

## Setup

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

Update `.env` so `DATABASE_URL` points to your local PostgreSQL instance.

If you do not already have PostgreSQL running locally, one option is:

```powershell
docker run --name jera-fx-postgres -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=jera_fx -p 5432:5432 -d postgres:16
```

## Migrate

```powershell
alembic upgrade head
```

## Seed REER and catalog

```powershell
jera-fx seed
```

## Backfill PTAX

```powershell
jera-fx backfill --source ptax --start 2026-01-01 --end 2026-02-28
```

## Backfill SGS

```powershell
jera-fx backfill --source sgs --start 2026-02-25 --end 2026-02-27 --series-key sgs_selic_target_rate
jera-fx backfill --source sgs --start 2025-12-01 --end 2026-02-01 --series-key sgs_ipca_12m
jera-fx backfill --source sgs --start 2026-02-01 --end 2026-02-01 --series-key commodity_terms_of_trade
```

## Backfill Focus / Expectativas

```powershell
jera-fx backfill --source focus --start 2026-04-01 --end 2026-04-02 --series-key focus_exchange_rate_median_2026 --series-key focus_exchange_rate_median_2027 --series-key focus_exchange_rate_median_2028 --series-key focus_exchange_rate_median_2029 --series-key focus_ipca_median_2026 --series-key focus_ipca_median_2027 --series-key focus_ipca_median_2028 --series-key focus_ipca_median_2029
```

## Backfill Federal Reserve H.10

```powershell
jera-fx backfill --source h10 --start 2026-03-30 --end 2026-04-02 --series-key broad_usd_index
```

Notes:

- SGS series use the source date as the observation date and derive `reference_month_end` for joins.
- Focus uses `Data` as the survey vintage date and stores `DataReferencia` in observation attributes for downstream modeling.
- Focus annual series are filtered with `baseCalculo = 0` in this slice to avoid duplicate same-day rows.
- The H.10 connector uses the Federal Reserve Board Data Download Program package, not FRED or ALFRED.
- The H.10 package request uses a bounded `lastobs` size because oversized requests can return an empty response.

## Ingest the approved internal CDS file drop

Place the CSV file at `data/raw/cds/BRGV5YUSAC=R_2026-04-07.csv`, or pass an explicit repo-relative path with `--path`.

```powershell
jera-fx ingest-cds-file
```

Or:

```powershell
jera-fx ingest-cds-file --path data/raw/cds/BRGV5YUSAC=R_2026-04-07.csv
```

Notes:

- This source is a manual internal file drop.
- It is not a live feed.
- `released_at` remains null because the file does not carry a release timestamp.

## Build client snapshot

```powershell
jera-fx build-reer-bands
jera-fx build-source-freshness
jera-fx build-ptax-history
jera-fx build-domestic-macro
jera-fx build-tactical-driver-history
jera-fx build-tactical-driver-latest
jera-fx build-tactical-driver-freshness
jera-fx build-tactical-signal-readiness
jera-fx build-tactical-signal-components
jera-fx build-tactical-inputs
jera-fx build-tactical-signal
jera-fx build-client-overview
```

## Run the API

```powershell
uvicorn jera_fx_api.main:app --reload --host 127.0.0.1 --port 8000
```

Available client endpoints after this slice:

- `GET /v1/meta/last-updated`
- `GET /v1/client/overview`
- `GET /v1/client/reer-bands`
- `GET /v1/client/source-freshness`
- `GET /v1/client/ptax-history`
- `GET /v1/client/tactical-inputs`
- `GET /v1/client/tactical-signal-readiness`
- `GET /v1/client/tactical-drivers`
- `GET /v1/client/tactical-driver-freshness`
- `GET /v1/client/tactical-signal`

`GET /v1/client/tactical-signal` is available only after the approved internal CDS file is ingested and `jera-fx build-tactical-signal` succeeds.
It remains a read-only metadata/status endpoint in this slice and does not publish a numeric tactical score.

## Run tests

```powershell
python -m pytest -q
```

## Run PostgreSQL integration validation

Set `JERA_PG_TEST_DATABASE_URL` to a real local PostgreSQL database that can be reset during the test.

```powershell
$env:JERA_PG_TEST_DATABASE_URL="postgresql+psycopg://postgres:postgres@localhost:5432/jera_fx"
python -m pytest -q -m postgres_integration tests/test_postgres_integration.py
```
