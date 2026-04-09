"""
JERA Investment Data Pipeline and Modeling Framework
===================================================

This module implements a reproducible framework for assembling a clean
dataset of exchange‑rate drivers, constructing engineered features and
training simple predictive and explanatory models of the BRL/USD.

The goal of this module is two‑fold:
  1. Provide an example of how to organise data ingestion in a way that
     can be scheduled and updated in an automated fashion.
  2. Deliver reference implementations of rolling regressions and
     regularised machine learning models that the investment team can
     experiment with, extend and ultimately deploy in the internal
     analytics platform.  Nothing is hard‑coded – all inputs come
     either from the local REER database or from external APIs.

Key design principles
---------------------

* **Transparency** – All data ingestion is explicit.  Functions are
  provided for each external source rather than hidden behind a single
  monolithic download routine.  The references for each API are
  documented for compliance.
* **No surprise caching** – Raw API responses are not silently cached.
  Users should build their own caching layer if required.
* **Pure functions** – Where possible, functions return pandas DataFrames
  without side‑effects to aid reproducibility and unit testing.
* **Extensibility** – The pipeline is written in plain Python with
  minimal dependencies so that analysts can easily add new data
  sources or models.

Limitations
-----------

This framework illustrates the structure and logic of the data pipeline
but does not attempt to fetch real market data from external endpoints
during execution in this environment.  Network connectivity is not
guaranteed in the hosted environment used to run this code.  The
functions that call web services (e.g. BCB, BIS or FRED APIs) are
therefore written as stubs: they contain the request logic and
documentation, but they return empty DataFrames when executed here.
To use this framework in production, remove the stub guards (the
`if not allow_network:` blocks) and supply appropriate API keys where
necessary.

References
----------

* Banco Central do Brasil (BCB) Open Data APIs – e.g. the SGS service
  for macroeconomic time series and the OData endpoint for PTAX and
  Focus survey results: https://dadosabertos.bcb.gov.br
* Bank for International Settlements (BIS) Effective Exchange Rate
  indices – the REER and NEER series used in the REER database: see
  https://www.bis.org/statistics/eer.htm
* Federal Reserve Board – G.5 and H.10 releases for broad dollar index
  and major currency indices: https://www.federalreserve.gov/releases

Example usage
-------------

```python
from jera_investment_pipeline import (
    fetch_reer_database, fetch_bcb_sgs, assemble_dataset,
    run_rolling_ols, run_ridge_model
)

# Load REER/NEER from local xlsx (provided with this repository)
reer_df = fetch_reer_database('REER_database_ver11Mar2026.xlsx')

# Optionally download BCB series (this returns empty DataFrames here
# because network calls are disabled by default).  In production you
# would set allow_network=True and supply start/end dates.
ptax = fetch_bcb_sgs(series_id=20741, start='2000-01-01', end='2026-12-31')
cds  = fetch_bcb_sgs(series_id=13621, start='2000-01-01', end='2026-12-31')

# Combine features into a single DataFrame.  In this example we only
# use REER/NEER because the API calls return empty DataFrames.
features = assemble_dataset(reer_df, ptax=ptax, cds=cds)

# Train a rolling OLS on the last five years of data
ols_result = run_rolling_ols(features, target='pct_chg_brusd')

# Train a ridge regression on the full sample up to 2023 and
# evaluate on 2024 onwards (if data exist)
ridge_result = run_ridge_model(features)
```
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from typing import Dict, Iterable, Tuple, Optional

import numpy as _np
import pandas as _pd
from sklearn.linear_model import RidgeCV
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import mean_squared_error
import statsmodels.api as _sma


def fetch_reer_database(xlsx_path: str, series: str = "REER_120_BR") -> _pd.DataFrame:
    """Load the REER/NEER database for Brazil from a local XLSX file.

    Parameters
    ----------
    xlsx_path : str
        Absolute or relative path to the REER database (converted to XLSX format).
    series : str, default 'REER_120_BR'
        The name of the column within the REER workbook to return.  By
        default this returns the broad REER index for Brazil.  Other
        valid options include 'NEER_120_BR' for the nominal effective
        exchange rate, as well as 'REER_MONTHLY_51' or
        'NEER_MONTHLY_51' for partner‑specific baskets.

    Returns
    -------
    DataFrame
        A two‑column DataFrame with a DateIndex (year‑month) and
        the selected series as float.  The index is monthly and is
        named 'date'.  Missing values are forward‑filled.
    """
    xls = _pd.ExcelFile(xlsx_path)
    sheet_name = None
    col_name = series

    # Determine which sheet contains the desired series.
    if series.startswith("REER_120"):
        sheet_name = "REER_MONTHLY_120"
    elif series.startswith("NEER_120"):
        sheet_name = "NEER_MONTHLY_120"
    elif series.startswith("REER_51"):
        sheet_name = "REER_MONTHLY_51"
    elif series.startswith("NEER_51"):
        sheet_name = "NEER_MONTHLY_51"
    else:
        raise ValueError(f"Unrecognised series name: {series}")

    df = _pd.read_excel(xlsx_path, sheet_name=sheet_name)
    if col_name not in df.columns:
        raise KeyError(f"Column {col_name} not found in {sheet_name}")

    # Build a DateIndex from the first column which is in 'YYYYMM'
    # format.  Strip any non‑numeric characters and parse to year and
    # month.  Some entries might be missing – we coerce to NaN.
    date_strs = df.iloc[:, 0].astype(str).str.extract(r'(\d{4})M(\d{2})')
    dates = _pd.to_datetime({
        'year': date_strs[0].astype(int),
        'month': date_strs[1].astype(int),
        'day': 1
    })
    series_data = df[col_name].astype(float)
    reer_df = _pd.DataFrame({series: series_data.values}, index=dates)
    reer_df.index.name = 'date'
    # Sort index and forward fill missing values
    reer_df = reer_df.sort_index().asfreq('MS')
    reer_df[series] = reer_df[series].fillna(method='ffill')
    return reer_df


def fetch_bcb_sgs(
    series_id: int,
    start: Optional[str] = None,
    end: Optional[str] = None,
    allow_network: bool = False,
) -> _pd.DataFrame:
    """Fetch a time series from the Banco Central do Brasil (SGS) API.

    This function retrieves a series given its numeric ID from the SGS
    API.  It returns a DataFrame with a DateIndex and a single
    column named after the ID.  For safety, network requests are
    disabled by default – set `allow_network=True` to enable.

    Notes
    -----
    The SGS API exposes macroeconomic series including interest rates,
    credit aggregates and price indices.  Documentation and series
    catalogue are available at https://dadosabertos.bcb.gov.br.  The
    `start` and `end` parameters should be ISO dates (YYYY‑MM‑DD) and
    correspond to the period to download.  If omitted the API returns
    all available history.

    Returns
    -------
    DataFrame
        A DataFrame indexed by date with a column named
        f'sgs_{series_id}'.  If network is disabled it returns an
        empty DataFrame.
    """
    if not allow_network:
        # Return an empty DataFrame as a stub when network calls are
        # disabled.  Analysts should set allow_network=True when
        # running in an environment with internet access.
        return _pd.DataFrame()

    import requests

    # Build URL according to BCB Open Data API spec
    url = (
        f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{series_id}/dados"
        f"?formato=json"
    )
    if start:
        url += f"&dataInicial={start}"
    if end:
        url += f"&dataFinal={end}"

    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    records = resp.json()
    # Convert to DataFrame
    df = _pd.DataFrame(records)
    if df.empty:
        return df
    df['data'] = _pd.to_datetime(df['data'], dayfirst=True)
    df['valor'] = _pd.to_numeric(df['valor'], errors='coerce')
    df = df.rename(columns={'data': 'date', 'valor': f'sgs_{series_id}'})
    df = df.set_index('date').sort_index()
    return df


def assemble_dataset(
    reer_df: _pd.DataFrame,
    ptax: Optional[_pd.DataFrame] = None,
    cds: Optional[_pd.DataFrame] = None,
    **extra: Dict[str, _pd.DataFrame],
) -> _pd.DataFrame:
    """Combine REER, nominal exchange rates and other variables into a single panel.

    Parameters
    ----------
    reer_df : DataFrame
        DataFrame returned by :func:`fetch_reer_database` containing the
        selected REER or NEER series for Brazil.  It must be indexed
        by month.
    ptax : DataFrame, optional
        Daily PTAX series from BCB.  Should have a 'date' index and a
        column containing the BRL/USD rate.  If provided, it will be
        resampled to month‑end and log returns will be computed.
    cds : DataFrame, optional
        Credit Default Swap spread for Brazil (e.g. 5yr).  Should
        have a 'date' index.  It will be resampled to monthly and
        mean aggregated.  Additional variables can be passed via
        `extra` where the key is the column name and the value is a
        DataFrame.

    Returns
    -------
    DataFrame
        A panel DataFrame indexed by month with columns: the REER
        values, the percentage change in PTAX (pct_chg_brusd), the
        monthly average CDS and any extra variables.  Missing values
        are forward‑filled.
    """
    panel = reer_df.copy()

    # Resample PTAX to month end and compute percentage change
    if ptax is not None and not ptax.empty:
        ptax_monthly = ptax.resample('M').last()
        # Convert to end-of-month date index (month start) to align with REER
        ptax_monthly.index = ptax_monthly.index.to_period('M').to_timestamp('M')
        br = ptax_monthly.iloc[:, 0]
        pct_chg = br.pct_change()
        pct_chg.name = 'pct_chg_brusd'
        panel = panel.join(pct_chg, how='left')

    # Resample CDS (monthly mean)
    if cds is not None and not cds.empty:
        cds_monthly = cds.resample('M').mean()
        cds_monthly.index = cds_monthly.index.to_period('M').to_timestamp('M')
        cds_col = cds_monthly.iloc[:, 0]
        cds_col.name = 'cds'
        panel = panel.join(cds_col, how='left')

    # Join any extra variables provided
    for key, df in extra.items():
        if df is not None and not df.empty:
            monthly = df.resample('M').mean()
            monthly.index = monthly.index.to_period('M').to_timestamp('M')
            series = monthly.iloc[:, 0]
            series.name = key
            panel = panel.join(series, how='left')

    # Forward fill any missing values
    panel = panel.sort_index().fillna(method='ffill')
    return panel


def run_rolling_ols(
    panel: _pd.DataFrame,
    target: str,
    window: int = 60,
    min_periods: int = 24,
    drop_na: bool = True,
) -> Dict[str, _pd.Series]:
    """Run a rolling OLS of the target on all other columns in the panel.

    Parameters
    ----------
    panel : DataFrame
        Panel DataFrame containing the target column and feature columns.
    target : str
        Name of the column to use as the dependent variable.
    window : int, default 60
        Number of observations in each rolling window (e.g. 60 months ≈ 5
        years).
    min_periods : int, default 24
        Minimum number of non‑NA observations required to estimate a
        regression.  If fewer observations are present, the result
        for that window is NaN.
    drop_na : bool, default True
        Whether to drop rows with any missing values before running
        regressions.  If False, missing values are automatically
        handled by statsmodels.

    Returns
    -------
    dict
        A mapping containing:
        - ``'betas'``: DataFrame of regression coefficients for each
          feature (columns) indexed by the end of each rolling window.
        - ``'r2'``: Series of coefficient of determination (R²) for
          each window.
        - ``'resid_std'``: Series of standard deviation of residuals
          (RMSE) for each window.
    """
    if target not in panel.columns:
        raise KeyError(f"Target column {target} not found in panel")

    # Optionally drop rows with any NA values
    if drop_na:
        data = panel.dropna().copy()
    else:
        data = panel.copy()

    y_full = data[target]
    X_full = data.drop(columns=[target])
    endog_names = X_full.columns

    # Prepare containers for results
    betas = []
    r2_scores = []
    resid_stds = []
    index_dates = []

    for i in range(window, len(data) + 1):
        sub_y = y_full.iloc[i - window:i]
        sub_X = X_full.iloc[i - window:i]
        if sub_y.count() < min_periods:
            betas.append(_np.full(len(endog_names), _np.nan))
            r2_scores.append(_np.nan)
            resid_stds.append(_np.nan)
            index_dates.append(y_full.index[i - 1])
            continue
        # Add constant
        sub_X_const = _sma.add_constant(sub_X)
        model = _sma.OLS(sub_y, sub_X_const, missing='drop')
        result = model.fit()
        beta_values = result.params[endog_names]
        betas.append(beta_values.values)
        r2_scores.append(result.rsquared)
        resid_stds.append(_np.sqrt(result.mse_resid))
        index_dates.append(y_full.index[i - 1])

    betas_df = _pd.DataFrame(
        betas,
        index=_pd.Index(index_dates, name='date'),
        columns=endog_names,
    )
    r2_series = _pd.Series(r2_scores, index=betas_df.index, name='r2')
    resid_std = _pd.Series(resid_stds, index=betas_df.index, name='rmse')
    return {'betas': betas_df, 'r2': r2_series, 'resid_std': resid_std}


def run_ridge_model(
    panel: _pd.DataFrame,
    target: str = 'pct_chg_brusd',
    test_start: Optional[str] = None,
    alphas: Iterable[float] = (0.1, 1.0, 10.0, 100.0),
    cv_splits: int = 5,
) -> Dict[str, any]:
    """Train a ridge regression on the panel and evaluate out‑of‑sample.

    Parameters
    ----------
    panel : DataFrame
        Panel DataFrame indexed by date containing the target and
        features.  Must not contain missing values.  It is the
        caller's responsibility to drop or fill NAs appropriately.
    target : str, default 'pct_chg_brusd'
        Name of the column to use as dependent variable.
    test_start : str, optional
        ISO date indicating the first month of the holdout period.
        All observations strictly before this date are used for
        training, and the rest for testing.  If None, the entire
        sample is used with cross‑validation only.
    alphas : iterable of float, default (0.1, 1.0, 10.0, 100.0)
        Candidate regularisation strengths for RidgeCV.
    cv_splits : int, default 5
        Number of splits for TimeSeriesSplit cross‑validation.

    Returns
    -------
    dict
        Contains the following keys:
        - ``'model'``: the fitted RidgeCV instance.
        - ``'train_score'``: RMSE on the training period.
        - ``'test_score'``: RMSE on the test period (if test_start
          provided) or None.
        - ``'coefficients'``: Series of fitted coefficients indexed by
          feature names.
    """
    if target not in panel.columns:
        raise KeyError(f"Target column {target} not found in panel")
    df = panel.dropna().copy()
    y = df[target]
    X = df.drop(columns=[target])

    if test_start:
        test_start_dt = _pd.to_datetime(test_start)
        train_mask = df.index < test_start_dt
        test_mask = df.index >= test_start_dt
        X_train, y_train = X.loc[train_mask], y.loc[train_mask]
        X_test, y_test = X.loc[test_mask], y.loc[test_mask]
    else:
        X_train, y_train = X, y
        X_test, y_test = _pd.DataFrame(), _pd.Series(dtype=float)

    # Use time series split for cross‑validation inside the training set
    tscv = TimeSeriesSplit(n_splits=cv_splits)
    model = RidgeCV(alphas=_np.array(list(alphas)), cv=tscv, scoring='neg_root_mean_squared_error')
    model.fit(X_train, y_train)

    coeffs = _pd.Series(model.coef_, index=X.columns, name='coef')
    train_pred = model.predict(X_train)
    train_rmse = mean_squared_error(y_train, train_pred, squared=False)
    if not X_test.empty:
        test_pred = model.predict(X_test)
        test_rmse = mean_squared_error(y_test, test_pred, squared=False)
    else:
        test_rmse = None

    return {
        'model': model,
        'train_score': train_rmse,
        'test_score': test_rmse,
        'coefficients': coeffs,
    }


if __name__ == '__main__':
    # Example demonstration when executed as a script.
    # This is provided for developers to quickly test the pipeline
    # within an environment that has network access.  In this hosted
    # environment network is disabled by default, so API calls will
    # return empty DataFrames.
    import argparse
    parser = argparse.ArgumentParser(description='Run Jera investment pipeline demo')
    parser.add_argument('--reer', type=str, default='REER_120_BR',
                        help='REER series code to load from the local database')
    parser.add_argument('--reer-file', type=str, default='REER_database_ver11Mar2026.xlsx',
                        help='Path to the REER database file (xlsx)')
    parser.add_argument('--allow-network', action='store_true',
                        help='Enable network calls to fetch BCB series')
    args = parser.parse_args()

    reer_path = args.reer_file
    reer_df = fetch_reer_database(reer_path, series=args.reer)
    # Attempt to fetch PTAX (BCB series 20745 is PTAX ask).  If
    # network is disabled, an empty DataFrame will be returned.
    ptax = fetch_bcb_sgs(series_id=20745, start='2000-01-01', allow_network=args.allow_network)
    cds = fetch_bcb_sgs(series_id=13621, start='2000-01-01', allow_network=args.allow_network)
    panel = assemble_dataset(reer_df, ptax=ptax, cds=cds)
    if 'pct_chg_brusd' in panel.columns and not panel['pct_chg_brusd'].isna().all():
        # Run rolling OLS for demonstration
        ols_res = run_rolling_ols(panel, target='pct_chg_brusd', window=60)
        print('Rolling OLS coefficients (tail):')
        print(ols_res['betas'].tail())
        # Run ridge regression splitting at 2024-01-01 if data are present
        ridge_res = run_ridge_model(panel, target='pct_chg_brusd', test_start='2024-01-01')
        print('Ridge model coefficients:')
        print(ridge_res['coefficients'].sort_values())
        print('Train RMSE:', ridge_res['train_score'])
        print('Test RMSE:', ridge_res['test_score'])
    else:
        print('Panel lacks pct_chg_brusd; PTAX data not available in this environment')