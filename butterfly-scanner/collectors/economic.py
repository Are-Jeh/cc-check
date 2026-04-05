"""Economic indicators collector — monthly macro data interpolated to daily."""

import logging

import numpy as np
import pandas as pd

from config import START_DATE, END_DATE
from db import is_cache_valid, load_series, store_series

logger = logging.getLogger(__name__)

SOURCE = "economic"

# Each indicator: (name, description, realistic_mean, realistic_std, unit, real_source)
INDICATORS = {
    "GST_collections": {
        "mean": 1_40_000,   # ~1.4 lakh crore monthly
        "std": 20_000,
        "trend": 0.02,      # 2% monthly growth trend
        "unit": "crore_INR",
        # TODO: Replace with real data from GST Council press releases
        # https://gstcouncil.gov.in/gst-revenue
    },
    "UPI_volumes": {
        "mean": 800,         # ~800 crore monthly transactions
        "std": 100,
        "trend": 0.03,       # strong growth trend
        "unit": "crore_txns",
        # TODO: Replace with real data from NPCI
        # https://www.npci.org.in/what-we-do/upi/upi-ecosystem-statistics
    },
    "auto_sales": {
        "mean": 3_00_000,    # ~3 lakh units monthly
        "std": 50_000,
        "trend": 0.005,
        "unit": "units",
        # TODO: Replace with real data from SIAM
        # https://www.siam.in/statistics.aspx
    },
    "power_consumption": {
        "mean": 120,          # ~120 billion units monthly
        "std": 15,
        "trend": 0.01,
        "unit": "billion_kWh",
        # TODO: Replace with real data from CEA
        # https://cea.nic.in/dashboard/
    },
    "cement_dispatches": {
        "mean": 30,           # ~30 million tonnes monthly
        "std": 5,
        "trend": 0.008,
        "unit": "million_tonnes",
        # TODO: Replace with real data from CMA
        # https://www.cmaindia.org/
    },
    "railway_freight": {
        "mean": 120,          # ~120 million tonnes monthly
        "std": 15,
        "trend": 0.006,
        "unit": "million_tonnes",
        # TODO: Replace with real data from Indian Railways
        # https://indianrailways.gov.in/railwayboard/view_section.jsp?lang=0&id=0,1,304,366,554
    },
}


def _generate_synthetic_monthly(
    name: str, mean: float, std: float, trend: float, seed: int
) -> pd.Series:
    """
    Generate realistic synthetic monthly data with trend, seasonality, noise.
    """
    months = pd.date_range(
        start=str(START_DATE),
        end=str(END_DATE),
        freq="MS",  # month start
    )
    n = len(months)
    rng = np.random.default_rng(seed)

    # Trend component: exponential growth
    trend_vals = mean * (1 + trend) ** np.arange(n)

    # Seasonal component: slight pattern (Q4 typically higher)
    month_of_year = np.array([d.month for d in months])
    seasonal = 1.0 + 0.05 * np.sin(2 * np.pi * (month_of_year - 3) / 12)

    # Noise
    noise = rng.normal(0, std, size=n)

    values = trend_vals * seasonal + noise
    values = np.maximum(values, mean * 0.3)  # floor at 30% of mean

    return pd.Series(values, index=months, name=name)


def _interpolate_to_daily(monthly_series: pd.Series) -> pd.Series:
    """
    Interpolate a monthly series to daily using cubic interpolation.
    """
    daily_index = pd.date_range(
        start=monthly_series.index.min(),
        end=monthly_series.index.max(),
        freq="D",
    )
    daily = monthly_series.reindex(daily_index).interpolate(method="cubic")
    return daily.dropna()


def collect_economic_data() -> dict[str, pd.Series]:
    """
    Collect economic indicators. Tries to load from SQLite cache first;
    if not found, generates realistic synthetic placeholder data with
    TODO comments indicating the real data source.

    All monthly data is interpolated to daily using cubic interpolation.

    Returns dict of indicator_name -> daily pd.Series with DatetimeIndex.
    """
    results: dict[str, pd.Series] = {}

    for idx, (name, params) in enumerate(INDICATORS.items()):
        cache_key = f"{SOURCE}:{name}"

        # Try loading from cache
        if is_cache_valid(cache_key):
            series = load_series(SOURCE, name)
            if not series.empty:
                results[name] = series
                logger.info("Loaded %s from cache (%d values)", name, len(series))
                continue

        # Generate synthetic data
        # TODO: Replace synthetic data with real data from sources listed
        # in the INDICATORS dict above
        logger.warning(
            "Generating synthetic data for %s — replace with real data from %s",
            name,
            params.get("unit", "unknown source"),
        )

        monthly = _generate_synthetic_monthly(
            name=name,
            mean=params["mean"],
            std=params["std"],
            trend=params["trend"],
            seed=42 + idx,
        )

        daily = _interpolate_to_daily(monthly)

        store_series(SOURCE, name, daily)
        results[name] = daily
        logger.info("Generated synthetic %s: %d daily values", name, len(daily))

    logger.info("Economic collector: %d indicators loaded", len(results))
    return results
