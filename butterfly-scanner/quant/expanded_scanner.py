"""
Expanded Pattern Scanner — Multi-day holds + Regime splits
============================================================
Extends the core pattern scanner with:
  1. Multi-day holding periods (N = 2, 3, 5, 10, 20 days per entry DOW)
  2. VIX regime split (above/below median India VIX)
  3. Trend regime split (price above/below 50-day SMA at entry)

All patterns use the same statistical pipeline as the core scanner:
  70/30 chronological split, drift-adjusted t-test, Wilson CI,
  min 50 occurrences, min 5 bps effect, BH-FDR at alpha=0.01,
  OOS validation at p<0.05.
"""

import logging
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from quant.pattern_scanner import (
    PatternResult,
    _compute_pattern_stats,
    apply_fdr_and_filter,
    DOW_NAMES,
    MIN_OCCURRENCES,
)

logger = logging.getLogger(__name__)

# Holding periods in trading days
HOLD_DAYS = [2, 3, 5, 10, 20]

# 50-day SMA lookback for trend regime
SMA_WINDOW = 50

# Path to India VIX parquet (relative to project root)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
VIX_PARQUET = _PROJECT_ROOT / "data" / "daily" / "indiavix.parquet"


# ═══════════════════════════════════════════════════════════════════════
# DATA HELPERS
# ═══════════════════════════════════════════════════════════════════════

def _load_vix_series() -> Optional[pd.Series]:
    """Load India VIX close prices from cached parquet."""
    if not VIX_PARQUET.exists():
        logger.warning("India VIX parquet not found at %s", VIX_PARQUET)
        return None
    vix_df = pd.read_parquet(VIX_PARQUET)
    if "Close" not in vix_df.columns:
        logger.warning("India VIX parquet has no Close column")
        return None
    vix = vix_df["Close"].dropna()
    vix.index = pd.to_datetime(vix.index)
    logger.info("Loaded India VIX: %d bars", len(vix))
    return vix


def _compute_n_day_returns(
    df: pd.DataFrame,
    n: int,
) -> pd.Series:
    """
    Compute forward N-day returns from Close.
    return_t = (Close_{t+n} - Close_t) / Close_t
    """
    close = df["Close"]
    future_close = close.shift(-n)
    mask = close > 0
    returns = (future_close - close) / close
    returns = returns[mask]
    return returns.dropna()


def _compute_baseline_n_day(df: pd.DataFrame, n: int) -> float:
    """Average N-day forward return (drift baseline)."""
    rets = _compute_n_day_returns(df, n)
    if len(rets) < 20:
        return 0.0
    return float(rets.mean())


# ═══════════════════════════════════════════════════════════════════════
# SCAN 1: Multi-day holding periods
# ═══════════════════════════════════════════════════════════════════════

def scan_multiday_hold(
    df: pd.DataFrame,
    ticker: str,
) -> list[PatternResult]:
    """
    For each entry day-of-week (Mon-Fri) and holding period N in {2,3,5,10,20},
    compute buy-at-Close on entry day, sell at Close N trading days later.
    5 entry days x 5 holding periods = 25 patterns per ticker.
    """
    results: list[PatternResult] = []
    df = df.copy()
    df["dow"] = df.index.dayofweek

    for hold_n in HOLD_DAYS:
        # Precompute forward N-day returns for the whole series
        close = df["Close"].values
        n = len(close)
        if n <= hold_n:
            continue

        # Vectorized: future close is close shifted by hold_n positions
        future_close = np.empty(n, dtype=float)
        future_close[:] = np.nan
        future_close[:n - hold_n] = close[hold_n:]

        fwd_returns = (future_close - close) / close
        df[f"fwd_{hold_n}d"] = fwd_returns

        # Baseline drift for this holding period
        valid_rets = fwd_returns[~np.isnan(fwd_returns) & (close > 0)]
        baseline = float(np.mean(valid_rets)) if len(valid_rets) > 20 else 0.0

        for entry_dow in range(5):
            mask = (df["dow"] == entry_dow) & df[f"fwd_{hold_n}d"].notna()
            trade_returns = df.loc[mask, f"fwd_{hold_n}d"].values

            if len(trade_returns) < MIN_OCCURRENCES:
                continue

            entry_lbl = f"{DOW_NAMES[entry_dow]}_Close"
            exit_lbl = f"Close+{hold_n}d"
            desc = f"Buy {entry_lbl} -> Sell {exit_lbl}"

            result = _compute_pattern_stats(
                trade_returns,
                ticker, "multiday_hold", desc, entry_lbl, exit_lbl,
                baseline_mean=baseline,
            )
            if result:
                results.append(result)

        # Clean up temp column
        df.drop(columns=[f"fwd_{hold_n}d"], inplace=True)

    logger.info("  %s Multi-day hold: %d combos tested", ticker, len(results))
    return results


# ═══════════════════════════════════════════════════════════════════════
# SCAN 2: VIX regime split
# ═══════════════════════════════════════════════════════════════════════

def scan_vix_regime(
    df: pd.DataFrame,
    ticker: str,
    vix: pd.Series,
) -> list[PatternResult]:
    """
    Split multi-day hold patterns by India VIX regime (above/below median).
    For each entry DOW x hold period, test separately in high-VIX and low-VIX.
    """
    results: list[PatternResult] = []
    if vix is None or vix.empty:
        return results

    df = df.copy()
    df["dow"] = df.index.dayofweek

    # Align VIX to trading dates (forward-fill to handle missing days)
    vix_aligned = vix.reindex(df.index, method="ffill")
    vix_median = vix_aligned.median()
    if pd.isna(vix_median):
        return results

    high_vix_mask = vix_aligned > vix_median
    low_vix_mask = vix_aligned <= vix_median

    regimes = [
        ("vix_high", high_vix_mask),
        ("vix_low", low_vix_mask),
    ]

    for hold_n in HOLD_DAYS:
        close = df["Close"].values
        n = len(close)
        if n <= hold_n:
            continue

        future_close = np.empty(n, dtype=float)
        future_close[:] = np.nan
        future_close[:n - hold_n] = close[hold_n:]
        fwd_returns = (future_close - close) / close
        df[f"fwd_{hold_n}d"] = fwd_returns

        # Baseline per regime
        valid_mask = ~np.isnan(fwd_returns) & (close > 0)

        for regime_name, regime_mask in regimes:
            regime_vals = regime_mask.values if hasattr(regime_mask, 'values') else regime_mask
            combined_valid = valid_mask & regime_vals
            regime_rets = fwd_returns[combined_valid]
            baseline = float(np.mean(regime_rets)) if len(regime_rets) > 20 else 0.0

            for entry_dow in range(5):
                dow_mask = (df["dow"] == entry_dow).values
                mask = dow_mask & combined_valid & df[f"fwd_{hold_n}d"].notna().values
                trade_returns = fwd_returns[mask]

                if len(trade_returns) < MIN_OCCURRENCES:
                    continue

                entry_lbl = f"{DOW_NAMES[entry_dow]}_Close"
                exit_lbl = f"Close+{hold_n}d"
                desc = f"[{regime_name}] Buy {entry_lbl} -> Sell {exit_lbl}"

                result = _compute_pattern_stats(
                    trade_returns,
                    ticker, "vix_regime", desc, entry_lbl, exit_lbl,
                    condition=regime_name,
                    baseline_mean=baseline,
                )
                if result:
                    results.append(result)

        df.drop(columns=[f"fwd_{hold_n}d"], inplace=True)

    logger.info("  %s VIX regime: %d combos tested", ticker, len(results))
    return results


# ═══════════════════════════════════════════════════════════════════════
# SCAN 3: Trend regime split (price vs 50-day SMA)
# ═══════════════════════════════════════════════════════════════════════

def scan_trend_regime(
    df: pd.DataFrame,
    ticker: str,
) -> list[PatternResult]:
    """
    Split multi-day hold patterns by trend regime:
    above 50-day SMA (uptrend) vs below (downtrend) at entry time.
    """
    results: list[PatternResult] = []
    df = df.copy()
    df["dow"] = df.index.dayofweek

    sma = df["Close"].rolling(window=SMA_WINDOW, min_periods=SMA_WINDOW).mean()
    above_sma = df["Close"] > sma
    below_sma = df["Close"] <= sma

    # Need enough data after SMA warmup
    if above_sma.sum() < MIN_OCCURRENCES or below_sma.sum() < MIN_OCCURRENCES:
        return results

    regimes = [
        ("trend_up", above_sma),
        ("trend_down", below_sma),
    ]

    for hold_n in HOLD_DAYS:
        close = df["Close"].values
        n = len(close)
        if n <= hold_n:
            continue

        future_close = np.empty(n, dtype=float)
        future_close[:] = np.nan
        future_close[:n - hold_n] = close[hold_n:]
        fwd_returns = (future_close - close) / close
        df[f"fwd_{hold_n}d"] = fwd_returns

        valid_mask = ~np.isnan(fwd_returns) & (close > 0)

        for regime_name, regime_mask in regimes:
            regime_vals = regime_mask.values if hasattr(regime_mask, 'values') else regime_mask
            combined_valid = valid_mask & regime_vals
            regime_rets = fwd_returns[combined_valid]
            baseline = float(np.mean(regime_rets)) if len(regime_rets) > 20 else 0.0

            for entry_dow in range(5):
                dow_mask = (df["dow"] == entry_dow).values
                mask = dow_mask & combined_valid & df[f"fwd_{hold_n}d"].notna().values
                trade_returns = fwd_returns[mask]

                if len(trade_returns) < MIN_OCCURRENCES:
                    continue

                entry_lbl = f"{DOW_NAMES[entry_dow]}_Close"
                exit_lbl = f"Close+{hold_n}d"
                desc = f"[{regime_name}] Buy {entry_lbl} -> Sell {exit_lbl}"

                result = _compute_pattern_stats(
                    trade_returns,
                    ticker, "trend_regime", desc, entry_lbl, exit_lbl,
                    condition=regime_name,
                    baseline_mean=baseline,
                )
                if result:
                    results.append(result)

        df.drop(columns=[f"fwd_{hold_n}d"], inplace=True)

    logger.info("  %s Trend regime: %d combos tested", ticker, len(results))
    return results


# ═══════════════════════════════════════════════════════════════════════
# ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════════════

def run_expanded_scans(
    daily_data: dict[str, pd.DataFrame],
) -> tuple[list[PatternResult], list[PatternResult]]:
    """
    Run all expanded scans across all tickers.

    Args:
        daily_data: dict of {ticker_name: OHLCV DataFrame with DatetimeIndex}

    Returns:
        (all_results, significant_results) after FDR correction
    """
    all_results: list[PatternResult] = []

    # Load VIX once for regime splits
    vix = _load_vix_series()

    # Exclude indiavix from scanning (it's a regime indicator, not a tradeable ticker)
    scan_tickers = {k: v for k, v in daily_data.items() if k != "indiavix"}

    for ticker, df in scan_tickers.items():
        if len(df) < MIN_OCCURRENCES * 2:
            logger.warning("Skipping %s: only %d bars", ticker, len(df))
            continue

        logger.info("Expanded scan: %s (%d daily bars)...", ticker, len(df))

        # Scan 1: Multi-day holding periods
        all_results.extend(scan_multiday_hold(df, ticker))

        # Scan 2: VIX regime split
        if vix is not None:
            all_results.extend(scan_vix_regime(df, ticker, vix))

        # Scan 3: Trend regime split
        all_results.extend(scan_trend_regime(df, ticker))

    logger.info("Expanded scan: %d total hypotheses tested", len(all_results))

    # Apply FDR correction and filtering (shared with core scanner)
    significant = apply_fdr_and_filter(all_results)

    return all_results, significant
