"""
OHLC Data Layer
================
Fetch daily (10 yr) and hourly (2 yr) OHLC data for all tickers via yfinance.
Cache as parquet files in data/daily/ and data/hourly/.
"""

import logging
import sys
import os
from pathlib import Path
from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

logger = logging.getLogger(__name__)

DAILY_DIR = _PROJECT_ROOT / "data" / "daily"
HOURLY_DIR = _PROJECT_ROOT / "data" / "hourly"
DAILY_DIR.mkdir(parents=True, exist_ok=True)
HOURLY_DIR.mkdir(parents=True, exist_ok=True)

# All tickers to scan
TICKERS = {
    "nifty50": "^NSEI",
    "banknifty": "^NSEBANK",
    "niftyit": "^CNXIT",
    "niftyfmcg": "^CNXFMCG",
    "indiavix": "^INDIAVIX",
    "gold": "GC=F",
    "silver": "SI=F",
    "crude": "CL=F",
    "usdinr": "INR=X",
    "sp500": "^GSPC",
    "dxy": "DX-Y.NYB",
    "us10y": "^TNX",
}


def _flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Flatten MultiIndex columns from yfinance."""
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df


def fetch_daily_ohlc(
    start: str = "2015-01-01",
    end: str = "2025-12-31",
    force: bool = False,
) -> dict[str, pd.DataFrame]:
    """
    Fetch daily OHLC for all tickers. Cache as parquet.

    Returns dict of {ticker_name: DataFrame with OHLC columns}.
    """
    results = {}
    for name, sym in TICKERS.items():
        path = DAILY_DIR / f"{name}.parquet"

        if path.exists() and not force:
            df = pd.read_parquet(path)
            if len(df) > 100:
                results[name] = df
                logger.info("Loaded daily %s from cache: %d rows", name, len(df))
                continue

        try:
            logger.info("Fetching daily OHLC for %s (%s)...", name, sym)
            df = yf.download(sym, start=start, end=end, progress=False, auto_adjust=True)
            df = _flatten_columns(df)
            df.index = pd.to_datetime(df.index)
            df.index.name = "date"

            # Keep only OHLCV
            ohlc_cols = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]
            df = df[ohlc_cols].dropna(subset=["Close"])

            if len(df) > 0:
                df.to_parquet(path)
                results[name] = df
                logger.info("  %s: %d daily bars saved", name, len(df))
            else:
                logger.warning("  %s: no data returned", name)
        except Exception as e:
            logger.error("  %s failed: %s", name, e)

    return results


def fetch_hourly_ohlc(
    force: bool = False,
) -> dict[str, pd.DataFrame]:
    """
    Fetch hourly OHLC (max ~2 years from yfinance with interval='1h').
    Cache as parquet. Supports incremental updates.

    Returns dict of {ticker_name: DataFrame with OHLC columns}.
    """
    results = {}
    # yfinance 1h data: max 730 days lookback
    end_dt = datetime.now()
    start_dt = end_dt - timedelta(days=729)

    for name, sym in TICKERS.items():
        path = HOURLY_DIR / f"{name}.parquet"
        existing = None

        if path.exists() and not force:
            existing = pd.read_parquet(path)
            existing.index = pd.to_datetime(existing.index)
            last_date = existing.index.max()
            # If data is recent enough (within 2 days), skip
            if (end_dt - last_date.to_pydatetime().replace(tzinfo=None)).days < 2:
                results[name] = existing
                logger.info("Loaded hourly %s from cache: %d rows (up to %s)",
                            name, len(existing), last_date.date())
                continue
            # Incremental: fetch from last date
            fetch_start = last_date - timedelta(days=1)
        else:
            fetch_start = start_dt

        try:
            logger.info("Fetching hourly OHLC for %s (%s) from %s...",
                        name, sym, fetch_start.strftime("%Y-%m-%d"))
            df = yf.download(
                sym,
                start=fetch_start.strftime("%Y-%m-%d"),
                end=end_dt.strftime("%Y-%m-%d"),
                interval="1h",
                progress=False,
                auto_adjust=True,
            )
            df = _flatten_columns(df)
            df.index = pd.to_datetime(df.index)
            # Remove timezone info for consistency
            if df.index.tz is not None:
                df.index = df.index.tz_localize(None)
            df.index.name = "datetime"

            ohlc_cols = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]
            df = df[ohlc_cols].dropna(subset=["Close"])

            if existing is not None and len(df) > 0:
                # Merge with existing, drop duplicates
                combined = pd.concat([existing, df])
                combined = combined[~combined.index.duplicated(keep="last")]
                combined = combined.sort_index()
                df = combined

            if len(df) > 0:
                df.to_parquet(path)
                results[name] = df
                logger.info("  %s: %d hourly bars saved", name, len(df))
            else:
                logger.warning("  %s: no hourly data returned", name)
        except Exception as e:
            logger.error("  %s hourly failed: %s", name, e)

    return results


def load_cached_daily() -> dict[str, pd.DataFrame]:
    """Load all cached daily parquets without fetching."""
    results = {}
    for name in TICKERS:
        path = DAILY_DIR / f"{name}.parquet"
        if path.exists():
            results[name] = pd.read_parquet(path)
    return results


def load_cached_hourly() -> dict[str, pd.DataFrame]:
    """Load all cached hourly parquets without fetching."""
    results = {}
    for name in TICKERS:
        path = HOURLY_DIR / f"{name}.parquet"
        if path.exists():
            results[name] = pd.read_parquet(path)
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    print("=== Fetching Daily OHLC ===")
    daily = fetch_daily_ohlc()
    for name, df in daily.items():
        print(f"  {name}: {len(df)} bars, {df.index.min().date()} to {df.index.max().date()}")

    print("\n=== Fetching Hourly OHLC ===")
    hourly = fetch_hourly_ohlc()
    for name, df in hourly.items():
        print(f"  {name}: {len(df)} bars, {df.index.min()} to {df.index.max()}")
