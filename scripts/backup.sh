#!/bin/sh
# ─────────────────────────────────────────────────────────
# JERA FX Postgres backup — daily pg_dump with rotation
#
# Runs pg_dump once a day, writes to /backups/jera_fx_<date>.sql.gz,
# and deletes backups older than BACKUP_RETENTION_DAYS.
#
# Expects: PGHOST, PGDATABASE, PGUSER, PGPASSWORD (from env).
# ─────────────────────────────────────────────────────────
set -u

BACKUP_DIR=/backups
RETENTION="${BACKUP_RETENTION_DAYS:-14}"
INTERVAL="${BACKUP_INTERVAL_SECONDS:-86400}"

mkdir -p "${BACKUP_DIR}"

echo "[backup] starting; retention=${RETENTION}d interval=${INTERVAL}s" >&2

while true; do
  STAMP=$(date +%Y%m%d_%H%M%S)
  OUT="${BACKUP_DIR}/jera_fx_${STAMP}.sql.gz"
  echo "[backup] $(date -Iseconds) dumping to ${OUT}" >&2
  if pg_dump --no-owner --no-privileges "${PGDATABASE}" | gzip > "${OUT}"; then
    SIZE=$(du -h "${OUT}" | cut -f1)
    echo "[backup] $(date -Iseconds) dump OK (${SIZE})" >&2
  else
    echo "[backup] $(date -Iseconds) dump FAILED" >&2
    rm -f "${OUT}"
  fi

  # Rotate: delete backups older than RETENTION days
  find "${BACKUP_DIR}" -name 'jera_fx_*.sql.gz' -mtime "+${RETENTION}" -delete 2>/dev/null || true

  sleep "${INTERVAL}"
done
