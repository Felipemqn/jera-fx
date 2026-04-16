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

## 2. Production Deploy — On-Prem Docker

### 2.1 Pre-deploy checklist

- [ ] Servidor Linux com Docker 24+ e Docker Compose v2
- [ ] Firewall permitindo 8000 (API), 3000/3001 (UIs) **apenas** da rede interna / VPN
- [ ] Reverse proxy (nginx/Traefik) terminando TLS na frente — o compose nao expoe HTTPS
- [ ] `.env` copiado de `.env.example` com valores reais:
  - `POSTGRES_PASSWORD` gerado via `openssl rand -base64 32`
  - `DATABASE_URL` coerente com o password acima
  - `CORS_ALLOWED_ORIGINS` apontando para os hostnames reais (https://...)
- [ ] Volume persistente `pgdata` em storage backed-up
- [ ] DNS interno resolvendo os hostnames para o servidor

### 2.2 First-time deploy

```bash
# 1. Clone
git clone https://github.com/Felipemqn/jera-fx.git
cd jera-fx
git checkout v1.0.1-prod-ready   # ou a tag mais recente

# 2. Configure environment
cp .env.example .env
nano .env   # preencha POSTGRES_PASSWORD, DATABASE_URL, CORS_ALLOWED_ORIGINS

# 3. Build + start
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

# 4. Verify health (wait ~20s)
curl http://localhost:8000/v1/meta/health
# Expected: {"status":"ok","version":"1.0.1","db":"ok",...}

# 5. Seed initial data
docker compose exec api python -m jera_fx_api.cli seed

# 6. First data backfill + snapshot build
docker compose exec api python -m jera_fx_api.scheduler
```

After this, the `scheduler` service will automatically re-run the
pipeline every 24h (controlled by `SCHEDULER_INTERVAL_SECONDS`).
The `backup` service will dump Postgres every 24h into the `pgbackups`
volume and rotate anything older than `BACKUP_RETENTION_DAYS` (default 14).

### 2.3 Local dev (no prod override)

```bash
# Uses dev defaults (weak password, Postgres port exposed)
docker compose up -d
docker compose exec api python -m jera_fx_api.cli seed
docker compose run --rm scheduler   # one-shot refresh
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
# {"status":"ok","version":"1.0.1","db":"ok","timestamp":"..."}
```

Use this endpoint for:
- Load balancer health probes (returns 200 when OK)
- External monitoring (Datadog, UptimeRobot, internal Nagios)
- `status` field: `"ok"` when DB ping succeeds, `"degraded"` when DB unreachable

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

## 9. Backup & Restore

### Automatic backups (production)
The `backup` service in `docker-compose.prod.yml` runs `pg_dump`
every `BACKUP_INTERVAL_SECONDS` (default 24h) and stores gzipped
dumps in the `pgbackups` volume. Older backups are auto-deleted
after `BACKUP_RETENTION_DAYS` (default 14).

```bash
# List current backups
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  exec backup ls -lh /backups

# Copy a backup off the container
docker cp <container_id>:/backups/jera_fx_YYYYMMDD_HHMMSS.sql.gz ./
```

### Manual backup
```bash
docker compose exec db pg_dump -U ${POSTGRES_USER} ${POSTGRES_DB} \
  | gzip > manual_backup_$(date +%Y%m%d).sql.gz
```

### Restore
```bash
gunzip -c jera_fx_YYYYMMDD.sql.gz | \
  docker compose exec -T db psql -U ${POSTGRES_USER} ${POSTGRES_DB}
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
