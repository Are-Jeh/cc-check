"""Lagged correlation analysis — Pearson, Spearman, Kendall."""

import warnings
import numpy as np
import pandas as pd
from scipy.stats import pearsonr, spearmanr, kendalltau

MIN_OBSERVATIONS = 30


def compute_lagged_correlations(
    indicator: pd.Series,
    market: pd.Series,
    max_lag: int = 30,
) -> list[dict]:
    """Compute Pearson, Spearman, and Kendall correlations at each lag.

    For each lag from 0 to *max_lag*, the *indicator* series is shifted forward
    by *lag* days relative to the *market* series (i.e. indicator leads market).
    The two series are inner-joined on their date index and rows with NaN are
    dropped.  A minimum of 30 overlapping observations is required to produce
    a result for a given lag.

    Returns a list of dicts, one per valid lag, with keys:
        lag, pearson_r, pearson_p, spearman_r, spearman_p, kendall_r, kendall_p
    """
    results: list[dict] = []

    # Normalise indexes to DatetimeIndex for reliable alignment
    indicator = indicator.copy()
    market = market.copy()
    indicator.index = pd.to_datetime(indicator.index)
    market.index = pd.to_datetime(market.index)

    for lag in range(0, max_lag + 1):
        # Shift indicator forward: today's indicator value paired with
        # market value *lag* days later.
        shifted = indicator.shift(-lag, freq="D") if lag > 0 else indicator

        # Inner join on dates
        combined = pd.concat(
            {"indicator": shifted, "market": market}, axis=1, join="inner"
        ).dropna()

        if len(combined) < MIN_OBSERVATIONS:
            continue

        x = combined["indicator"].values
        y = combined["market"].values

        # Skip if either series is constant (correlation undefined)
        if np.std(x) == 0 or np.std(y) == 0:
            continue

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            pr, pp = pearsonr(x, y)
            sr, sp = spearmanr(x, y)
            kr, kp = kendalltau(x, y)

        results.append(
            {
                "lag": lag,
                "pearson_r": float(pr),
                "pearson_p": float(pp),
                "spearman_r": float(sr),
                "spearman_p": float(sp),
                "kendall_r": float(kr),
                "kendall_p": float(kp),
            }
        )

    return results
