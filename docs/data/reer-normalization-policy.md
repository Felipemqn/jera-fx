# REER Normalization Policy

## Purpose

The local REER workbook is the authoritative Phase 2 seed source, but its native scale does not match the prototype display scale. To avoid mixing display logic with source data, the platform stores both raw source-native and canonical REER values.

## Canonical rules

- Raw REER values are stored exactly as published in `raw.observations`.
- Canonical client-facing REER values are stored in `curated.feature_values`.
- Canonical scale policy is `canonical-2020avg100`.
- Conversion rule is:

```text
canonical_value = native_value * 100 / mean(native_value over calendar year 2020)
```

- The anchor year is part of feature provenance and is currently fixed at `2020`.
- APIs default to canonical REER for client presentation, but native values remain exposed for auditability.

## Reconciliation rule

Prototype REER values are legacy reference visuals only. They are explicitly not treated as source data, training data, or seed data.
