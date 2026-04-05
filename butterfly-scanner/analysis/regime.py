"""Market regime detection and regime-conditional correlation testing."""

from __future__ import annotations

import pandas as pd
from scipy.stats import pearsonr

from config import BULL_THRESHOLD, BEAR_THRESHOLD, REGIME_WINDOW

MIN_OBSERVATIONS = 20


def detect_regimes(
    market_series: pd.Series,
    window: int | None = None,
) -> pd.Series:
    """Classify each trading day into bull, bear, or sideways.

    The classification is based on the rolling cumulative return over
    *window* days (default taken from ``config.REGIME_WINDOW``).

    Returns a ``pd.Series`` of regime labels indexed by date.
    """
    if window is None:
        window = REGIME_WINDOW

    market_series = market_series.copy()
    market_series.index = pd.to_datetime(market_series.index)
    market_series = market_series.sort_index()

    # Compute rolling cumulative return:  (P_t / P_{t-window}) - 1
    rolling_return = market_series / market_series.shift(window) - 1

    def _classify(ret: float) -> str:
        if pd.isna(ret):
            return "sideways"
        if ret > BULL_THRESHOLD:
            return "bull"
        if ret < BEAR_THRESHOLD:
            return "bear"
        return "sideways"

    regimes = rolling_return.map(_classify)
    regimes.name = "regime"
    return regimes


def test_regime_stability(
    indicator: pd.Series,
    market: pd.Series,
    regimes: pd.Series,
    best_lag: int,
) -> dict:
    """Test whether a correlation holds across different market regimes.

    For each regime (bull, bear, sideways) the function filters both series
    to dates belonging to that regime, applies the given *best_lag*, and
    computes the Pearson correlation.

    Returns ``{regime: {"r": float, "p": float, "n": int}}``.
    """
    indicator = indicator.copy()
    market = market.copy()
    indicator.index = pd.to_datetime(indicator.index)
    market.index = pd.to_datetime(market.index)
    regimes = regimes.copy()
    regimes.index = pd.to_datetime(regimes.index)

    results: dict[str, dict] = {}

    for regime_label in ("bull", "bear", "sideways"):
        regime_dates = regimes[regimes == regime_label].index

        # Filter market to regime dates
        mkt_regime = market[market.index.isin(regime_dates)]

        # Shift indicator
        shifted = (
            indicator.shift(-best_lag, freq="D") if best_lag > 0 else indicator
        )

        combined = pd.concat(
            {"indicator": shifted, "market": mkt_regime}, axis=1, join="inner"
        ).dropna()

        n = len(combined)

        if n < MIN_OBSERVATIONS:
            results[regime_label] = {"r": None, "p": None, "n": n}
            continue

        r, p = pearsonr(combined["indicator"].values, combined["market"].values)
        results[regime_label] = {"r": float(r), "p": float(p), "n": n}

    return results
