"""Market data collector — Indian & US indices, FII/DII flows."""

import logging
import numpy as np
import pandas as pd
import yfinance as yf

from config import INDIA_TICKERS, US_TICKERS, START_DATE, END_DATE
from db import is_cache_valid, load_series, store_series

logger = logging.getLogger(__name__)


def _fetch_ticker(name: str, symbol: str) -> pd.Series:
    """Download daily close for a single ticker, return as Series with DatetimeIndex."""
    try:
        df = yf.download(
            symbol,
            start=str(START_DATE),
            end=str(END_DATE),
            progress=False,
            auto_adjust=True,
        )
        if df.empty:
            logger.warning("No data returned for %s (%s)", name, symbol)
            return pd.Series(dtype=float)
        # Handle MultiIndex columns (newer yfinance versions)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        close = df["Close"]
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:, 0]
        close = close.squeeze()
        close.index = pd.to_datetime(close.index)
        close.name = name
        return close
    except Exception as e:
        logger.error("Failed to fetch %s (%s): %s", name, symbol, e)
        return pd.Series(dtype=float)


def _collect_tickers(tickers: dict[str, str], source: str) -> dict[str, pd.Series]:
    """Fetch a group of tickers, compute returns, cache results."""
    results: dict[str, pd.Series] = {}

    # Check if all tickers in this group are cached
    all_cached = all(
        is_cache_valid(f"{source}:{name}") for name in tickers
    )

    if all_cached:
        logger.info("Loading %s tickers from cache", source)
        for name in tickers:
            series = load_series(source, name)
            if not series.empty:
                results[name] = series
        return results

    # Fetch fresh data
    for name, symbol in tickers.items():
        logger.info("Fetching %s (%s)", name, symbol)
        price_series = _fetch_ticker(name, symbol)
        if price_series.empty:
            continue

        # VIX stays as levels; everything else becomes daily returns
        if "VIX" in name.upper():
            processed = price_series
        else:
            processed = price_series.pct_change().dropna()

        store_series(source, name, processed)
        results[name] = processed

    return results


def _collect_fii_dii() -> dict[str, pd.Series]:
    """
    Collect FII/DII daily net flows.

    TODO: Replace with real scraping from moneycontrol or NSDL.
    Current implementation generates synthetic placeholder data to unblock
    downstream analysis. Real FII/DII flow data is published daily by NSDL
    (https://www.fpi.nsdl.co.in/web/Reports/Latest.aspx).
    """
    source = "flows"

    # Check cache
    fii_cached = is_cache_valid(f"{source}:FII_net")
    dii_cached = is_cache_valid(f"{source}:DII_net")

    if fii_cached and dii_cached:
        logger.info("Loading FII/DII flows from cache")
        results = {}
        fii = load_series(source, "FII_net")
        dii = load_series(source, "DII_net")
        if not fii.empty:
            results["FII_net"] = fii
        if not dii.empty:
            results["DII_net"] = dii
        return results

    # Generate synthetic placeholder data
    logger.warning(
        "Generating synthetic FII/DII flow data — replace with real scraping"
    )
    dates = pd.bdate_range(start=str(START_DATE), end=str(END_DATE))
    rng = np.random.default_rng(42)

    # FII flows: mean ~-200 Cr, std ~2000 Cr (realistic range)
    fii_vals = rng.normal(loc=-200, scale=2000, size=len(dates))
    fii_series = pd.Series(fii_vals, index=dates, name="FII_net")

    # DII flows: mean ~+500 Cr, std ~1500 Cr (offsetting FII)
    dii_vals = rng.normal(loc=500, scale=1500, size=len(dates))
    dii_series = pd.Series(dii_vals, index=dates, name="DII_net")

    store_series(source, "FII_net", fii_series)
    store_series(source, "DII_net", dii_series)

    return {"FII_net": fii_series, "DII_net": dii_series}


def collect_market_data() -> dict[str, pd.Series]:
    """
    Collect all market data: Indian indices, US indices, FII/DII flows.

    Returns dict of indicator_name -> daily pd.Series with DatetimeIndex.
    Keys prefixed with "ret_" are market return targets (to be predicted).
    All other keys are market indicators (predictors).
    """
    results: dict[str, pd.Series] = {}

    # Indian indices — these are our prediction TARGETS, prefix with "ret_"
    try:
        india = _collect_tickers(INDIA_TICKERS, "india_market")
        for k, v in india.items():
            if "VIX" in k.upper():
                # VIX is an indicator, not a target
                results[k] = v
            else:
                results[f"ret_{k}"] = v
    except Exception as e:
        logger.error("Failed collecting Indian market data: %s", e)

    # US indices — these are indicators (predictors)
    try:
        us = _collect_tickers(US_TICKERS, "us_market")
        results.update(us)
    except Exception as e:
        logger.error("Failed collecting US market data: %s", e)

    # FII/DII flows — indicators
    try:
        flows = _collect_fii_dii()
        results.update(flows)
    except Exception as e:
        logger.error("Failed collecting FII/DII flow data: %s", e)

    logger.info("Market collector: %d indicators loaded", len(results))
    return results
