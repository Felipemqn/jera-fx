# Methodology for the JERA Investment Data Pipeline

## Overview

This note describes the conceptual and technical underpinnings of the
`jera_investment_pipeline.py` module.  It was designed as a starting
point for the JERA investment team to build a repeatable workflow to
collect, clean, transform and model the BRL/USD exchange rate using
official data sources and transparent analytical techniques.  The
module itself is written in pure Python and avoids any hard‑coded
constants; all numerical inputs must be provided by the user via
external data sources.  Nothing in the pipeline requires that a
specific estimate of “fair value” be fixed in code – instead it
constructs features from raw data and hands them to standard
regressions or machine‑learning estimators.

## Data sources

### Banco Central do Brasil (BCB) open data

Many Brazilian macroeconomic time series are published by the Banco
Central do Brasil via its **SGS** (Sistema Gerenciador de Séries
Temporais) and **OData** services.  These endpoints support
machine‑readable formats such as JSON and CSV.  For example, the
``bcdata.sgs.{id}`` endpoint returns a given series identified by its
numeric code.  BCB also provides access to PTAX (the BRL/USD fixing)
and Focus survey expectations through its OData service.  A listing
of API endpoints and documentation is available on the BCB’s open
data portal【313381720220770†L23-L41】.  When using these services,
pay attention to parameter names: dates must be specified in ISO
format (`dataInicial=YYYY-MM-DD` and `dataFinal=YYYY-MM-DD`) and the
`formato` parameter controls the returned data structure.  The
pipeline’s `fetch_bcb_sgs` function is a thin wrapper around this
endpoint and will return an empty DataFrame unless the `allow_network`
flag is set to `True`.

### Bank for International Settlements (BIS) REER database

The Real Effective Exchange Rate (REER) and Nominal Effective
Exchange Rate (NEER) indices compiled by the BIS measure a
country’s currency relative to a trade‑weighted basket of partners.
These data are published with monthly frequency and are available
for a broad basket of 120 partners (our default) as well as a
narrow basket of 51 partners.  The REER dataset used here comes
from the Bruegel/BIS “REER Database” and spans 1993–Feb 2026.
Columns are labelled `REER_120_BR` for Brazil’s broad real index,
`NEER_120_BR` for the nominal index, and analogous codes for other
countries.  The module provides a convenience function
`fetch_reer_database` that loads one of these columns into a tidy
DataFrame with a monthly DateIndex and forward‑fills missing values.

### External constraints

This development environment does not provide unrestricted internet
access.  As a result, the API functions in the pipeline are
implemented as *stubs* that return empty data frames by default.
They can still be used in production by setting the `allow_network`
flag to `True` and supplying a valid internet connection.  Analysts
should install the module in their own environment with network
access to make full use of the data ingestion functions.

### Legal considerations for FRED

The Federal Reserve Bank of St. Louis operates the FRED and ALFRED
databases which are popular sources for macroeconomic data.  The
FRED terms of use explicitly prohibit data mining and scraping of
their content for commercial or derivative purposes【741188237723883†L105-L111】.
In particular, the FAQ states that users may not “take all the data
on FRED and claim it’s a unique product or service” and that data
mining or extraction of FRED data is not allowed【741188237723883†L105-L111】.
Because machine‑learning model training necessarily involves
extracting large amounts of data, we recommend **not** using FRED
as the primary data source for the pipeline.  Instead, use data from
the original publishers (e.g. BCB, IBGE, BIS) or licensed vendors.

## Feature construction

The core function of the pipeline is `assemble_dataset`, which
creates a monthly panel of the BRL/USD drivers.  At a minimum this
panel includes:

* A real exchange rate series (by default, `REER_120_BR`),
  representing the structural valuation anchor.
* If PTAX data are supplied, the month‑end BRL/USD level and its
  percentage change (`pct_chg_brusd`).  This is the typical target
  variable for short‑horizon regressions.
* If CDS data are provided, the monthly average of the 5‑year
  sovereign CDS spread for Brazil.
* Any additional variables supplied by the caller (e.g. DXY index,
  commodity prices, carry spreads).  These are automatically
  resampled to monthly frequency.

Missing values are forward‑filled.  Analysts can extend this
function to include inflation differentials, productivity measures,
or other macro variables as needed.

## Modelling approaches

The module illustrates two complementary modelling techniques:

### Rolling Ordinary Least Squares

`run_rolling_ols` slides a fixed‑width window (default 60 months) over
the panel and fits an OLS regression in each window.  The function
returns the time series of coefficients (`betas`), the R² for each
window and the RMSE of the residuals.  This is useful for
diagnosing how the sensitivity of the BRL/USD to each driver changes
through time and for constructing a *beta map* for risk management.

### Ridge regression with time‑series cross‑validation

`run_ridge_model` fits a regularised linear model to the entire
dataset and uses `TimeSeriesSplit` cross‑validation to select the
regularisation parameter (`alpha`).  An optional `test_start`
argument defines an explicit hold‑out period for evaluating
out‑of‑sample performance.  Ridge regression is less sensitive to
multicollinearity among features and can improve stability in
smaller samples compared with OLS.  The returned object includes
the estimated coefficients, training RMSE and test RMSE (if a
hold‑out is defined).

## How to use the pipeline

1. **Convert the REER database**: The Bruegel/BIS database is
   distributed as an `.xls` file.  Use LibreOffice or another
   converter to transform it into `.xlsx` format so that it can be
   read by pandas.  A command like `soffice --headless --convert-to
   xlsx REER_database_ver11Mar2026.xls` will produce
   `REER_database_ver11Mar2026.xlsx`.
2. **Load the REER series** with `fetch_reer_database`.  Provide
   the path to the `.xlsx` file and the desired series code.
3. **Fetch additional data** from BCB or other providers if you
   enable network access in your environment.  For example:
   ```python
   ptax = fetch_bcb_sgs(series_id=20745, start='2000-01-01', allow_network=True)
   cds  = fetch_bcb_sgs(series_id=13621, start='2000-01-01', allow_network=True)
   ```
4. **Assemble the panel** using `assemble_dataset(reer_df, ptax=ptax, cds=cds, ...)`.
5. **Run explanatory regressions** with `run_rolling_ols` to
   understand recent drivers of BRL/USD.
6. **Train predictive models** with `run_ridge_model` or other
   estimators from scikit‑learn.  Cross‑validation is handled using
   expanding windows suitable for time series.

## Extending the framework

This module is deliberately minimal.  The investment team is
encouraged to extend it by:

* Adding functions to fetch commodity prices, international interest
  rates or domestic macro variables from their respective APIs.
* Incorporating inflation differentials, productivity measures and
  terms of trade in the structural REER model.
* Implementing classification models to detect regime shifts in
  exchange‑rate dynamics (e.g. changes in the DXY/commodities/CDS
  landscape).
* Developing portfolio sleeves tied to the rolling betas produced by
  `run_rolling_ols` to improve risk forecasting and hedging.

## Caveats

* This module does **not** include any forecasting of fair value or
  price targets; it merely constructs a flexible dataset and
  demonstrates standard modelling tools.  Investment conclusions
  should be drawn by combining model outputs with analyst judgement.
* The preloaded REER database ends in February 2026.  Users must
  update the database as new releases become available.
* FRED data must not be used for machine‑learning training without
  explicit permission from the data owners【741188237723883†L105-L111】.
