"""Agricultural data collector — mandi prices, reservoir levels."""

import logging

import numpy as np
import pandas as pd
import requests

from config import START_DATE, END_DATE
from db import is_cache_valid, load_series, store_series

logger = logging.getLogger(__name__)

SOURCE = "agricultural"

# Realistic parameters for synthetic data
# TODO: Replace each with real data from the indicated source
MANDI_COMMODITIES = {
    "wheat_mandi": {
        "mean": 2200,     # Rs/quintal
        "std": 200,
        "seasonal_peak_month": 4,  # April (post-harvest dip)
        "seasonal_amplitude": 0.08,
        # TODO: Replace with real data from agmarknet
        # https://agmarknet.gov.in/ or https://enam.gov.in/web/dashboard/trade-data
    },
    "rice_mandi": {
        "mean": 2800,     # Rs/quintal
        "std": 250,
        "seasonal_peak_month": 11,  # November (kharif harvest)
        "seasonal_amplitude": 0.06,
        # TODO: Replace with real data from agmarknet
        # https://agmarknet.gov.in/
    },
    "onion_mandi": {
        "mean": 2500,     # Rs/quintal — highly volatile
        "std": 800,
        "seasonal_peak_month": 9,   # Sep-Oct (pre-kharif arrival, prices spike)
        "seasonal_amplitude": 0.25,
        # TODO: Replace with real data from agmarknet or NHRDF
        # https://nhrdf.org/en-us/DailyWiseMarketAnalysis
    },
}

RESERVOIR_CONFIG = {
    "reservoir_level": {
        "mean": 65,       # % of full reservoir level
        "std": 10,
        "seasonal_peak_month": 9,  # September (end of monsoon)
        "seasonal_amplitude": 0.30,
        # TODO: Replace with real data from WRIS (Water Resources Information System)
        # https://indiawris.gov.in/wris/ or CWC bulletin
        # http://cwc.gov.in/reservoir-storage
    },
}


def _try_fetch_agmarknet(commodity: str) -> pd.Series:
    """
    Attempt to fetch commodity prices from agmarknet/eNAM.

    The agmarknet website does not have a clean REST API; this tries
    known endpoints. Returns empty Series if it fails.

    TODO: Implement proper scraping or use eNAM data download if available.
    """
    # eNAM API attempt (often rate-limited or requires auth)
    try:
        url = "https://enam.gov.in/web/Ajax/trade_data_powerful_powerful"
        # This endpoint is not guaranteed to work without proper session/auth
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            # Parse if we get valid data
            if isinstance(data, list) and len(data) > 0:
                logger.info("Got agmarknet data for %s", commodity)
                # Would need commodity-specific parsing here
                pass
    except Exception:
        pass

    return pd.Series(dtype=float)


def _try_fetch_reservoir_data() -> pd.Series:
    """
    Attempt to fetch reservoir storage data from WRIS/CWC.

    TODO: The CWC bulletin is published weekly as PDF. Would need
    PDF parsing or find a structured data source.
    """
    try:
        # CWC provides weekly bulletins, no clean API
        url = "http://cwc.gov.in/sites/default/files/reservoir-bulletin.json"
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if data:
                logger.info("Got WRIS reservoir data")
                # Would need specific parsing
                pass
    except Exception:
        pass

    return pd.Series(dtype=float)


def _generate_synthetic_daily(
    name: str,
    mean: float,
    std: float,
    seasonal_peak_month: int,
    seasonal_amplitude: float,
    seed: int,
) -> pd.Series:
    """
    Generate realistic synthetic daily data with seasonality, trend, and noise.

    Seasonality follows a sinusoidal pattern peaking at the specified month.
    """
    dates = pd.date_range(start=str(START_DATE), end=str(END_DATE), freq="D")
    n = len(dates)
    rng = np.random.default_rng(seed)

    # Day of year for seasonality
    day_of_year = np.array([d.timetuple().tm_yday for d in dates])

    # Peak day (approximate)
    peak_day = (seasonal_peak_month - 1) * 30 + 15

    # Seasonal component
    seasonal = 1.0 + seasonal_amplitude * np.cos(
        2 * np.pi * (day_of_year - peak_day) / 365.25
    )

    # Slight upward trend (1% per year)
    days_from_start = np.arange(n, dtype=float)
    trend = 1.0 + 0.01 * days_from_start / 365.25

    # Random walk component for realistic day-to-day correlation
    daily_shocks = rng.normal(0, std * 0.1, size=n)
    random_walk = np.cumsum(daily_shocks)
    # Mean-revert the random walk
    random_walk = random_walk - np.linspace(
        random_walk[0], random_walk[-1], n
    ) * 0.5

    values = mean * seasonal * trend + random_walk
    values = np.maximum(values, mean * 0.2)  # floor

    return pd.Series(values, index=dates, name=name)


def collect_agricultural_data() -> dict[str, pd.Series]:
    """
    Collect agricultural indicators: mandi commodity prices, reservoir levels.

    Tries real data sources first (agmarknet, WRIS). Falls back to
    synthetic placeholders with TODO comments if APIs are unavailable.

    Returns dict of indicator_name -> daily pd.Series with DatetimeIndex.
    """
    results: dict[str, pd.Series] = {}

    # --- Mandi commodity prices ---
    for idx, (name, params) in enumerate(MANDI_COMMODITIES.items()):
        cache_key = f"{SOURCE}:{name}"

        if is_cache_valid(cache_key):
            series = load_series(SOURCE, name)
            if not series.empty:
                results[name] = series
                logger.info("Loaded %s from cache (%d values)", name, len(series))
                continue

        # Try fetching real data
        try:
            real_data = _try_fetch_agmarknet(name)
            if not real_data.empty:
                store_series(SOURCE, name, real_data)
                results[name] = real_data
                logger.info("Fetched real %s data: %d values", name, len(real_data))
                continue
        except Exception as e:
            logger.warning("Real data fetch failed for %s: %s", name, e)

        # Fall back to synthetic data
        # TODO: Replace with real mandi price data from agmarknet/eNAM
        logger.warning(
            "Generating synthetic data for %s — replace with real agmarknet data",
            name,
        )
        series = _generate_synthetic_daily(
            name=name,
            mean=params["mean"],
            std=params["std"],
            seasonal_peak_month=params["seasonal_peak_month"],
            seasonal_amplitude=params["seasonal_amplitude"],
            seed=100 + idx,
        )
        store_series(SOURCE, name, series)
        results[name] = series
        logger.info("Generated synthetic %s: %d daily values", name, len(series))

    # --- Reservoir levels ---
    for idx, (name, params) in enumerate(RESERVOIR_CONFIG.items()):
        cache_key = f"{SOURCE}:{name}"

        if is_cache_valid(cache_key):
            series = load_series(SOURCE, name)
            if not series.empty:
                results[name] = series
                logger.info("Loaded %s from cache (%d values)", name, len(series))
                continue

        # Try fetching real data
        try:
            real_data = _try_fetch_reservoir_data()
            if not real_data.empty:
                store_series(SOURCE, name, real_data)
                results[name] = real_data
                logger.info("Fetched real %s data: %d values", name, len(real_data))
                continue
        except Exception as e:
            logger.warning("Real data fetch failed for %s: %s", name, e)

        # Fall back to synthetic data
        # TODO: Replace with real reservoir data from WRIS/CWC
        logger.warning(
            "Generating synthetic data for %s — replace with real WRIS data",
            name,
        )
        series = _generate_synthetic_daily(
            name=name,
            mean=params["mean"],
            std=params["std"],
            seasonal_peak_month=params["seasonal_peak_month"],
            seasonal_amplitude=params["seasonal_amplitude"],
            seed=200 + idx,
        )
        store_series(SOURCE, name, series)
        results[name] = series
        logger.info("Generated synthetic %s: %d daily values", name, len(series))

    logger.info("Agricultural collector: %d indicators loaded", len(results))
    return results
