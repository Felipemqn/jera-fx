# Monthly Index Policy

## Canonical monthly key

All monthly data in the platform must use `reference_month_end`.

## Why month-end

- PTAX monthly aggregation naturally resolves to the last available observation in the month.
- REER workbook rows can be mapped deterministically from source month labels to month-end.
- A single month-end key prevents silent joins between month-start and month-end series.

## Implementation rules

- Raw monthly observations store both `observation_date` and `reference_month_end`, with both set to month-end when the source is already monthly.
- Daily series retain their true `observation_date`, but any monthly aggregation must write the month-end key to `reference_month_end`.
- Tests must fail if monthly joins are attempted without normalizing to month-end first.
