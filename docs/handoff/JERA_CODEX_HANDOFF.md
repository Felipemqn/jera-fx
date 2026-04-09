# JERA Codex Handoff

## Recommended next step

Move the project into Codex for the implementation phase.

Use ChatGPT here for:
- research
- methodology reviews
- QA of model outputs
- wording for client-facing content

Use Codex for:
- repo-wide refactors
- building the production app
- wiring live data sources
- database migrations
- tests
- CI/CD and deployment setup

## Target repository layout

```text
jera-fx-platform/
  apps/
    client-web/
    investment-web/
  packages/
    data-pipeline/
    model-core/
    ui-components/
    shared-types/
  data/
    raw/
    curated/
    vintages/
  infra/
    db/
    jobs/
    docker/
    deployment/
  notebooks/
  docs/
  tests/
```

## Non-negotiables

- No hardcoded market values in the UI.
- All displayed numbers must come from database tables or computed model outputs.
- Every chart must be reproducible from persisted data.
- Store raw data, curated features, model outputs, and scenario runs separately.
- Keep a data dictionary and source map.
- Keep vintage timestamps for revised series where possible.
- Split client mode and investment mode at the presentation layer, not at the data layer.

## Data sources to wire first

- BCB SGS
- BCB OData / Olinda for PTAX and Focus
- BIS/Bruegel REER database
- IBGE/SIDRA
- approved market-data vendor for DXY, CDS, rates, and commodities

## Core product requirements

### Client mode
- Institutional interface.
- REER bands.
- Tactical integrated signal.
- Scenario charts 1y / 3y / 5y / 10y.
- Clean methodology notes.
- No internal jargon about legacy models.

### Investment mode
- Last 1 year price variation dashboard for all variables.
- Rolling multiple regression for 3Y / 2Y / 1Y / quarter windows.
- Feature importance and contribution waterfall.
- Sensitivity lab with scenario save/load.
- Regime map (e.g. DXY x CDS).
- Rolling betas and explanatory power tracking.
- Portfolio risk sleeves tied to factor exposures.

## Model stack

### Structural layer
- REER broad bands as the main anchor.
- REER narrow as regime filter.
- REER vs NEER decomposition.
- Optional annual productivity / terms-of-trade overlay.

### Tactical layer
- Regularized linear model (ridge / elastic net).
- Tree boosting model for nonlinearity.
- Quantile forecasts for scenario bands.
- Regime classifier for DXY / fiscal / commodity states.

### Explanatory layer
- Rolling OLS / rolling ridge.
- Windowed decomposition for 3Y / 2Y / 1Y / quarter.
- Contribution chart explaining the recent move in BRL/USD.

## Database design

Required tables:
- raw_market_data
- curated_features
- model_runs
- model_predictions
- factor_contributions
- saved_scenarios
- source_registry
- data_dictionary

Each record should include:
- source
- series code
- timestamp collected
- effective date
- value
- frequency
- vintage timestamp when relevant

## Acceptance criteria

- App builds from a clean clone.
- Scheduled refresh jobs update the database without manual edits.
- UI contains zero hardcoded market values.
- All charts load from database-backed APIs.
- Tests cover data transforms and model scoring.
- There is a reproducible backtest report.
- There is a seed script for local development.
- There is a deployment guide.

## Prompt to paste into Codex

```text
You are working inside the JERA FX platform repository.

Goal:
Build a production-grade BRL/USD platform with two presentation modes on top of the same backend:
1) Client Mode: institutional, clean, publishable directly to clients.
2) Investment Mode: deep analytical mode for the internal investment team.

Critical constraints:
- No hardcoded market values anywhere in the UI.
- Every displayed metric must come from the database or model outputs.
- Organize the database cleanly and make every transformation traceable.
- Use real data connectors and build refresh jobs.
- Keep methodology explicit and auditable.
- Separate raw data, curated features, model outputs, and saved scenarios.
- Preserve historical vintages where possible.

Data sources to implement first:
- BCB SGS
- BCB OData / Olinda for PTAX and Focus
- BIS/Bruegel REER database
- IBGE/SIDRA
- approved market-data vendor hooks for DXY, CDS, rates, commodities
- do not use FRED as the core training source

Build these layers:

A. Data layer
- Create ingest jobs
- Create normalized tables
- Create feature store
- Add scheduler entrypoints
- Add source registry and data dictionary

B. Model layer
- Structural layer: REER broad bands, REER narrow filter, REER vs NEER decomposition
- Tactical layer: ridge or elastic net, boosting model, quantile bands
- Explanatory layer: rolling multiple regression for 3Y / 2Y / 1Y / quarter windows
- Factor attribution for recent BRL/USD move
- Regime map and scenario engine

C. App layer
- Client Mode with institutional layout, clean charts, methodology section
- Investment Mode with last-year variable dashboard, rolling betas, contribution waterfall, feature importance, scenario lab, scenario persistence

D. Engineering
- Tests for transforms and model scoring
- Local seed script
- Environment variables documented
- Docker/dev setup
- API routes documented
- No dead code

Deliver in phases:
1. Propose repo structure and migration plan.
2. Implement data schemas and ingestion connectors.
3. Implement feature engineering.
4. Implement models and backtests.
5. Implement APIs.
6. Implement Client Mode.
7. Implement Investment Mode.
8. Add tests, docs, and run instructions.

At each phase:
- explain what changed
- list files created/edited
- run tests
- identify any missing credentials or vendor dependencies
```

## What to bring into the repo

Bring these assets first:
- the current app sources
- the REER database file
- the converted XLSX version
- the Python pipeline module
- the methodology notes
- any deck or scenario assumptions you still want as reference only

## Recommended operating rhythm

1. Create a clean git repo.
2. Add the assets above.
3. Open the repo in Codex.
4. Paste the master prompt.
5. Ask Codex to execute Phase 1 only.
6. Review the structure.
7. Continue phase by phase.
8. Bring the diffs back here for research review and model QA.
