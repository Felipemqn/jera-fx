# JERA FX Platform

## Project goal
Build a production-grade BRL/USD platform for JERA with two modes:
- Client Mode
- Investment Mode

The platform must use real market data, a structured database, reproducible models, and zero hardcoded market values in UI, scenarios, or model logic.

## Product modes
### Client Mode
Institutional presentation of:
- BRL/USD spot
- REER bands
- tactical integrated signal
- scenario fan chart for 1Y / 3Y / 5Y / 10Y
- neutral language suitable for direct client sharing

### Investment Mode
Analyst workspace with:
- last 1Y changes for all variables
- rolling explanatory regressions for 3Y / 2Y / 1Y / quarter
- factor attribution
- scenario lab with sensitivity controls
- saved scenarios
- model diagnostics
- feature importance
- backtests

## Data rules
- Use official or primary sources whenever possible.
- Prefer Banco Central do Brasil open data for PTAX, SGS and Focus / Expectations.
- Use the local REER database as the seed source and create a provider abstraction for future updates.
- Separate raw data, curated features, model artifacts and scenario runs.
- Store source metadata, release timestamps and ingestion timestamps.
- Do not hardcode spot, rates, scenario paths, bands, chart arrays or model coefficients.

## Engineering rules
- Strong typing.
- Clear package boundaries.
- Tests for every data transform.
- Every screen must show `last updated`.
- Every model run must be reproducible from stored metadata.
- Every API response contract must be typed.

## Definition of done
A task is done only if:
1. code builds,
2. tests pass,
3. no hardcoded market values remain,
4. docs are updated,
5. output is reviewable by PM, analyst and engineering.
