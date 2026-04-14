# Runbook: Manual CDS File Ingestion

**Source key:** `approved_internal_cds_file_drop`
**Series key:** `cds_brazil_5y`
**Source symbol:** `BRGV5YUSAC=R`
**Automation mode:** `manual_batch`
**Production approved:** yes, manual-batch only

This runbook defines the operational process for ingesting the approved
internal Brazil 5Y CDS CSV file drop. It is the single source of truth for
how new CDS files enter the system.

---

## 1. Source definition

The CDS file drop is an **approved internal manual batch**. It is not an API
feed. Each file represents a point-in-time export from the approved upstream
vendor terminal. A new file must be supplied whenever the CDS series is
refreshed.

Expected columns (order does not matter, presence does):

- `Date`
- `Price` (canonical value)
- `Open`
- `High`
- `Low`
- `Change %`

## 2. Filename convention

Files must follow:

```
<SOURCE_SYMBOL>_YYYY-MM-DD.csv
```

Example:

```
BRGV5YUSAC=R_2026-04-07.csv
```

Where `YYYY-MM-DD` is the **export date** (the snapshot date of the file,
not necessarily the most recent observation date inside the file).

The ingestor does not hard-reject non-conforming filenames, but emits a
warning and records `filename_convention_ok=false` in the source file
metadata. Files that do not match should be renamed before ingestion.

## 3. Storage layout

```
data/raw/cds/
  README.md                     # short pointer to this runbook
  BRGV5YUSAC=R_YYYY-MM-DD.csv   # current active file (tracked in Git only for regression fixture)
  archive/                      # historical files, not tracked in Git
    BRGV5YUSAC=R_YYYY-MM-DD.csv
```

Rules:

- Only one active file should live directly under `data/raw/cds/` at a time.
- When a new file arrives, move the previous file to `data/raw/cds/archive/`.
- The `archive/` folder is **not tracked in Git** (see `.gitignore`). Use
  your approved internal storage (SharePoint / OneDrive operational folder)
  for long-term retention.
- The fixture file currently committed in `data/raw/cds/` exists as a
  regression test artifact. Do not delete it until superseded by a newer
  committed file, and do not update it in place without updating regression
  test expectations.

## 4. Pre-ingestion validation (dry-run)

Before every ingestion, run the validator. It reads the file but does not
write anything to the database.

```bash
python -m jera_fx_api.cli validate-cds-file \
  --path data/raw/cds/BRGV5YUSAC=R_2026-04-07.csv \
  --check-db
```

The validator returns a JSON report with:

- `file_exists`
- `columns_ok` and `missing_columns`
- `naming_convention_ok` and `naming_convention_warnings`
- `row_count`
- `checksum_sha256`
- `observation_date_range`
- `already_ingested` (only when `--check-db` is passed)
- `errors` (list of blocking problems)

Exit status:

- `0` — file is safe to ingest
- `1` — file has blocking errors (missing columns, parse failures, etc.)

If `already_ingested=true`, the ingest step is still safe to re-run (it is
idempotent by checksum), but this usually indicates the same file is being
processed twice. Investigate before proceeding.

## 5. Ingestion

Ingestion requires an explicit operator identifier. A human-readable note
describing the export is recommended but optional.

```bash
python -m jera_fx_api.cli ingest-cds-file \
  --path data/raw/cds/BRGV5YUSAC=R_2026-04-07.csv \
  --operator fnobre@jera.capital \
  --source-note "Reuters Eikon manual export 2026-04-07 by fnobre"
```

The operator string is persisted in:

- `ingestion_runs.parameters_json.operator`
- `source_files.metadata_json.operator`

This creates the audit trail for who ingested which file.

Idempotency is enforced by SHA-256 of the file contents: re-running the
same command for the same file is a no-op at the row level (no duplicate
observations will be created).

## 6. Post-ingestion rebuild

After every successful CDS ingestion, rebuild the curated snapshots that
depend on CDS:

```bash
python -m jera_fx_api.cli build-source-freshness
python -m jera_fx_api.cli build-tactical-driver-history
python -m jera_fx_api.cli build-tactical-driver-latest
python -m jera_fx_api.cli build-tactical-driver-freshness
python -m jera_fx_api.cli build-tactical-signal-readiness
python -m jera_fx_api.cli build-tactical-signal-components
python -m jera_fx_api.cli build-tactical-inputs
python -m jera_fx_api.cli build-tactical-signal
```

## 7. Failure modes

| Symptom | Action |
|---|---|
| `validate-cds-file` reports `missing_columns` | Ask data provider for corrected export. Do not rename columns by hand. |
| `validate-cds-file` reports `naming_convention_warnings` | Rename file to the canonical pattern before ingesting. |
| `validate-cds-file` reports `already_ingested=true` | Verify with operator whether an older file was re-dropped. If so, skip ingestion. |
| `ingest-cds-file` fails mid-run | The `ingestion_runs` entry stays in `status=running` with the idempotency key. Investigate, fix the input, and re-run. |
| Post-rebuild `build-tactical-signal` reports `status != ready` | Check `build-tactical-signal-readiness` output for which driver is missing. |

## 8. Governance

- The file-drop source is `production_ingestion_approved: true` only in
  `manual_batch` mode. Do not build live-polling jobs against it.
- Every committed update to the reference fixture in `data/raw/cds/` must
  be accompanied by an updated regression test expectation.
- The operator argument is **required** — do not ingest anonymously.
- Vintage / revision timestamps are not tracked for this source because
  the upstream vendor export does not carry a release header. This is
  explicit in the catalog (`release_metadata_behavior: file drop has no
  release timestamp`).
