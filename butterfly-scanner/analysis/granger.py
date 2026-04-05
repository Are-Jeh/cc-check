"""Granger causality testing."""

from __future__ import annotations

import logging

import pandas as pd
from statsmodels.tsa.stattools import grangercausalitytests

logger = logging.getLogger(__name__)


def granger_causality_test(
    indicator: pd.Series,
    market: pd.Series,
    max_lag: int = 30,
) -> dict | None:
    """Run Granger causality tests for lags 1 through *max_lag*.

    The test determines whether past values of *indicator* contain information
    that helps predict *market* beyond what past values of *market* alone
    provide.

    Returns a dict with:
        best_lag     — lag with the lowest p-value
        best_p_value — the corresponding p-value
        all_results  — dict mapping lag -> p-value (ssr_ftest)

    Returns a dict with None values for best_lag / best_p_value if the tests
    fail (e.g. non-stationary data).
    """
    # Normalise indexes
    indicator = indicator.copy()
    market = market.copy()
    indicator.index = pd.to_datetime(indicator.index)
    market.index = pd.to_datetime(market.index)

    # Align series: inner join, forward-fill gaps, drop remaining NaN
    combined = pd.concat(
        {"indicator": indicator, "market": market}, axis=1, join="inner"
    )
    combined = combined.ffill().dropna()

    if len(combined) < max_lag + 2:
        logger.warning(
            "Not enough observations (%d) for Granger test with max_lag=%d",
            len(combined),
            max_lag,
        )
        return {"best_lag": None, "best_p_value": None, "all_results": {}}

    # grangercausalitytests expects a 2-column array: [y, x]
    # where we test if x Granger-causes y.
    data = combined[["market", "indicator"]].values

    try:
        test_results = grangercausalitytests(data, maxlag=max_lag, verbose=False)
    except Exception as exc:
        logger.warning("Granger test failed: %s", exc)
        return {"best_lag": None, "best_p_value": None, "all_results": {}}

    all_results: dict[int, float] = {}
    for lag in range(1, max_lag + 1):
        try:
            # ssr_ftest returns (F-stat, p-value, df_denom, df_num)
            p_value = test_results[lag][0]["ssr_ftest"][1]
            all_results[lag] = float(p_value)
        except (KeyError, IndexError, TypeError):
            continue

    if not all_results:
        return {"best_lag": None, "best_p_value": None, "all_results": {}}

    best_lag = min(all_results, key=all_results.get)  # type: ignore[arg-type]
    return {
        "best_lag": best_lag,
        "best_p_value": all_results[best_lag],
        "all_results": all_results,
    }
