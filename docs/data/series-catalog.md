# Series Catalog Note

The series catalog is seeded from `config/series_catalog.yml` and is the only allowed source of truth for source metadata and series identifiers in Phase 2.

Each series entry must define:

- provider
- source code
- frequency
- units
- source mode when applicable
- automation mode when applicable
- release metadata behavior
- transformation rules
- display metadata
- canonical scale policy

Phase 2 catalog entries include:

- `reer_120_br`
- `reer_51_br`
- `ptax_usd_brl_buy`
- `ptax_usd_brl_sell`
- `cds_brazil_5y` via approved internal manual CSV file drop

No connector should embed provider-specific series IDs outside this catalog.
