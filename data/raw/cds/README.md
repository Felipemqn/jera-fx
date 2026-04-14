# Manual CDS file drop

Approved internal manual batch source for Brazil 5Y CDS (`BRGV5YUSAC=R`).

This source is **not** a live API. Each file is a point-in-time export
from the approved upstream vendor terminal.

## Operational process

The full operational process (validation, ingestion, rotation, failure
modes, governance) is documented in:

- [`docs/runbooks/manual-cds-ingestion.md`](../../../docs/runbooks/manual-cds-ingestion.md)

Do not edit files in this folder or ingest a new file without reading
that runbook first.

## Filename convention

```
BRGV5YUSAC=R_YYYY-MM-DD.csv
```

Where `YYYY-MM-DD` is the export date of the file.

## Expected columns

`Date`, `Price`, `Open`, `High`, `Low`, `Change %`

## Quick reference

```bash
# Dry-run validation (no DB writes)
python -m jera_fx_api.cli validate-cds-file \
  --path data/raw/cds/<FILE>.csv --check-db

# Ingestion with operator audit trail
python -m jera_fx_api.cli ingest-cds-file \
  --path data/raw/cds/<FILE>.csv \
  --operator <operator-id> \
  --source-note "<description of export>"
```

## Archive

Historical CDS files should be moved to `archive/` (gitignored) when
superseded. Long-term retention lives in the approved internal storage,
not in the repository.
