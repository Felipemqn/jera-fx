#!/bin/sh
# ─────────────────────────────────────────────────────────
# JERA FX scheduler — simple daily loop
#
# Runs python -m jera_fx_api.scheduler every
# SCHEDULER_INTERVAL_SECONDS (default 86400 = 24h).
#
# Much simpler than installing cron inside the container.
# On failure, logs to stderr and retries on the next cycle.
# ─────────────────────────────────────────────────────────
set -u

INTERVAL="${SCHEDULER_INTERVAL_SECONDS:-86400}"

echo "[scheduler-loop] starting; interval=${INTERVAL}s" >&2

while true; do
  echo "[scheduler-loop] $(date -Iseconds) running refresh..." >&2
  if python -m jera_fx_api.scheduler; then
    echo "[scheduler-loop] $(date -Iseconds) refresh OK" >&2
  else
    EXIT=$?
    echo "[scheduler-loop] $(date -Iseconds) refresh FAILED (exit=${EXIT})" >&2
  fi
  echo "[scheduler-loop] sleeping ${INTERVAL}s until next cycle" >&2
  sleep "${INTERVAL}"
done
