# Runbook: Production Operations

## 1. Architecture

```
┌─────────────────┐   ┌───────────────┐   ┌──────────────────┐
│  Client Web     │   │  Investment   │   │  Scheduler       │
│  :3000          │──▶│  Web :3001    │   │  (cron/manual)   │
└────────┬────────┘   └───────┬───────┘   └────────┬─────────┘
         │                    │                     │
         ▼                    ▼                     ▼
     ┌──────────────────────────────────────────────────┐
     │              FastAPI :8000                        │
     │  /v1/client/*   /v1/investment/*   /v1/meta/*    │
     └──────────────────────┬───────────────────────────┘
                            │
                            ▼
     ┌──────────────────────────────────────────────────┐
     │              PostgreSQL :5432                     │
     │  meta / raw / curated / snapshots                │
     └──────────────────────────────────────────────────┘
```

## 2. Quick Start

```bash
# Docker (recommended for production)
docker compose up -d

# Then seed + build initial snapshots:
docker compose run --rm api python -m jera_fx_api.cli seed
docker compose run --rm --profile refresh scheduler

# Or locally:
pip install -e .
python -m jera_fx_api.cli seed
python -m jera_fx_api.scheduler
uvicorn jera_fx_api.main:app --host 0.0.0.0 --port 8000
```

## 3. Daily Refresh

The scheduler runs the full pipeline in dependency order:

1. Seed catalog (idempotent)
2. Backfill PTAX, SGS, H10 (last 7 days)
3. Build curated features (REER canonical → client overview → bands → ...)
4. Build tactical signal (readiness → components → inputs → score)
5. Build scenario set
6. Build investment snapshots (regression, variations)

### Run manually:
```bash
python -m jera_fx_api.scheduler
```

### Schedule via cron (Linux):
```cron
0 7 * * 1-5 cd /path/to/jera-fx && python -m jera_fx_api.scheduler >> /var/log/jera-fx-scheduler.log 2>&1
```

### Schedule via Task Scheduler (Windows):
- Program: `python`
- Arguments: `-m jera_fx_api.scheduler`
- Working directory: project root
- Trigger: daily at 07:00, weekdays only

## 4. CDS Manual Ingestion

CDS is the only manual data source. See:
- [`docs/runbooks/manual-cds-ingestion.md`](manual-cds-ingestion.md)

After ingesting a new CDS file, re-run the scheduler to rebuild all dependent snapshots.

## 5. Environment Variables

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://postgres:postgres@localhost:5432/jera_fx` | PostgreSQL connection |
| `APP_ENV` | `development` | `development` or `production` |
| `SERIES_CATALOG_PATH` | `config/series_catalog.yml` | Path to series catalog |
| `REER_WORKBOOK_PATH` | `data/raw/reer/REER_database_ver11Mar2026.xlsx` | REER seed workbook |
| `CDS_BRAZIL_5Y_FILE_PATH` | `data/raw/cds/BRGV5YUSAC=R_2026-04-07.csv` | Default CDS file |
| `API_HOST` | `127.0.0.1` | API bind host |
| `API_PORT` | `8000` | API bind port |

## 6. Database Migrations

```bash
# Apply all pending migrations
alembic upgrade head

# Check current revision
alembic current
```

## 7. Monitoring

### Health check
```bash
curl http://localhost:8000/v1/meta/health
```

### Source freshness
```bash
curl http://localhost:8000/v1/client/source-freshness | python -m json.tool
```

Check that `latest_ingested_at` for each source is within the expected window.

### Tactical signal status
```bash
curl http://localhost:8000/v1/client/tactical-signal | python -m json.tool
```

If `status` is `degraded` or `missing-drivers`, investigate `degraded_reasons`.

## 8. Troubleshooting

| Symptom | Action |
|---|---|
| API returns 404 on all endpoints | Run `python -m jera_fx_api.scheduler` to build snapshots |
| Tactical signal status = `degraded` | Check if all drivers have ≥12 monthly observations |
| Tactical signal status = `missing-drivers` | Check which driver is missing in readiness endpoint |
| Scheduler fails on backfill | Check network access to BCB/Fed APIs |
| CDS data is stale | Run manual CDS ingestion (see runbook) |

## 9. Backup

```bash
pg_dump -U postgres jera_fx > backup_$(date +%Y%m%d).sql
```

## 10. Test Suite

```bash
python -m pytest -q
```

Expected: all tests pass, 1 skipped (Postgres integration requires `JERA_PG_TEST_DATABASE_URL`).

## 11. Ports

| Service | Port | Purpose |
|---|---|---|
| API | 8000 | FastAPI backend |
| Client Web | 3000 | Institutional client mode |
| Investment Web | 3001 | Internal investment workspace |
| PostgreSQL | 5432 | Database |
