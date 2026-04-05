"""
Time Pattern Scanner — Core Engine
====================================
Brute-force scan every possible time combination (e.g., "Friday close > Wednesday open")
across all tickers with proper statistical rigor.

Statistical pipeline:
  1. Generate hypotheses (day-of-week, day-of-month, week-of-month, month, hourly)
  2. Train/test split (70/30 chronological)
  3. T-test on train set returns
  4. Benjamini-Hochberg FDR correction at alpha=0.01
  5. Validate survivors on test set
  6. Effect size + occurrence filters
  7. Wilson confidence interval on win rate
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd
from scipy import stats

logger = logging.getLogger(__name__)

# OHLC price labels
PRICES = ["Open", "High", "Low", "Close"]

# Day-of-week names (Monday=0)
DOW_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri"]

# Indian market hourly bars: 9:15-15:30 IST = 7 bars (9, 10, 11, 12, 13, 14, 15)
INDIA_HOURS = [9, 10, 11, 12, 13, 14, 15]

# Minimum occurrences for a pattern to be valid
MIN_OCCURRENCES = 50

# Minimum effect size in basis points
MIN_EFFECT_BPS = 5

# FDR alpha
FDR_ALPHA = 0.01

# Train fraction
TRAIN_FRAC = 0.70


@dataclass
class PatternResult:
    """Result of a single pattern hypothesis test."""
    ticker: str
    pattern_type: str       # e.g., "dow_ohlc", "dom_group", "hourly"
    description: str        # human-readable, e.g., "Buy Fri Close, Sell Mon Open"
    entry_label: str        # e.g., "Fri_Close"
    exit_label: str         # e.g., "Mon_Open"

    # Train set stats
    train_n: int = 0
    train_mean_ret: float = 0.0
    train_std_ret: float = 0.0
    train_t_stat: float = 0.0
    train_p_value: float = 1.0
    train_win_rate: float = 0.0
    train_sharpe: float = 0.0

    # Test set stats (OOS)
    test_n: int = 0
    test_mean_ret: float = 0.0
    test_std_ret: float = 0.0
    test_t_stat: float = 0.0
    test_p_value: float = 1.0
    test_win_rate: float = 0.0
    test_sharpe: float = 0.0

    # Wilson CI on test win rate
    test_win_ci_lo: float = 0.0
    test_win_ci_hi: float = 0.0

    # FDR-adjusted p-value (train)
    fdr_p_value: float = 1.0

    # Conditional filter (if any)
    condition: str = ""

    # Whether pattern survived all filters
    significant: bool = False


def _wilson_ci(wins: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score confidence interval for a proportion."""
    if n == 0:
        return 0.0, 0.0
    p_hat = wins / n
    denom = 1 + z**2 / n
    centre = (p_hat + z**2 / (2 * n)) / denom
    margin = (z / denom) * np.sqrt(p_hat * (1 - p_hat) / n + z**2 / (4 * n**2))
    return max(0.0, centre - margin), min(1.0, centre + margin)


def _sharpe(returns: np.ndarray) -> float:
    """Annualized Sharpe from per-trade returns (assume ~100 trades/year for swing)."""
    if len(returns) < 2 or np.std(returns) == 0:
        return 0.0
    return float(np.mean(returns) / np.std(returns) * np.sqrt(100))


def _compute_pattern_stats(
    returns: np.ndarray,
    ticker: str,
    pattern_type: str,
    description: str,
    entry_label: str,
    exit_label: str,
    condition: str = "",
    baseline_mean: float = 0.0,
) -> Optional[PatternResult]:
    """
    Split returns into train/test, run t-test vs baseline (drift-adjusted).
    Returns None if insufficient data.

    baseline_mean: average return for the same holding period (e.g., weekly drift).
                   Testing against this instead of 0 removes market drift bias.
    """
    n = len(returns)
    if n < MIN_OCCURRENCES:
        return None

    split = int(n * TRAIN_FRAC)
    train = returns[:split]
    test = returns[split:]

    if len(train) < 20 or len(test) < 10:
        return None

    # Test against baseline (drift-adjusted) rather than zero
    train_t, train_p = stats.ttest_1samp(train, baseline_mean)
    train_wins = int(np.sum(train > baseline_mean))

    test_t, test_p = stats.ttest_1samp(test, baseline_mean)
    test_wins = int(np.sum(test > baseline_mean))
    test_ci_lo, test_ci_hi = _wilson_ci(test_wins, len(test))

    return PatternResult(
        ticker=ticker,
        pattern_type=pattern_type,
        description=description,
        entry_label=entry_label,
        exit_label=exit_label,
        condition=condition,
        train_n=len(train),
        train_mean_ret=float(np.mean(train)),
        train_std_ret=float(np.std(train)),
        train_t_stat=float(train_t),
        train_p_value=float(train_p),
        train_win_rate=train_wins / len(train),
        train_sharpe=_sharpe(train),
        test_n=len(test),
        test_mean_ret=float(np.mean(test)),
        test_std_ret=float(np.std(test)),
        test_t_stat=float(test_t),
        test_p_value=float(test_p),
        test_win_rate=test_wins / len(test),
        test_sharpe=_sharpe(test),
        test_win_ci_lo=test_ci_lo,
        test_win_ci_hi=test_ci_hi,
    )


# ═══════════════════════════════════════════════════════════════════════
# LAYER 1: Daily scans
# ═══════════════════════════════════════════════════════════════════════

def scan_dow_ohlc(
    df: pd.DataFrame,
    ticker: str,
) -> list[PatternResult]:
    """
    Day-of-week OHLC scan (vectorized).
    For every (dayA, priceA) vs (dayB, priceB) where dayB >= dayA in the same week,
    compute return = (priceB - priceA) / priceA.
    """
    results = []
    df = df.copy()
    df["dow"] = df.index.dayofweek
    df["week_id"] = df.index.year * 100 + df.index.isocalendar().week.values.astype(int)

    # Pivot: for each week, get first occurrence of each (dow, price)
    # Build a wide table: rows=week_id, cols=(dow, price)
    pivoted = {}
    for day in range(5):
        day_df = df[df["dow"] == day]
        if day_df.empty:
            continue
        # Take first row per week for this day
        first_per_week = day_df.groupby("week_id").first()
        for price in PRICES:
            if price in first_per_week.columns:
                pivoted[(day, price)] = first_per_week[price]

    if not pivoted:
        return results

    wide = pd.DataFrame(pivoted)
    # wide.columns = MultiIndex of (day, price), index = week_id

    # Generate entry/exit combos using only tradeable prices (Open and Close).
    # Low/High are not executable prices — including them produces artifacts
    # (e.g., Low→High is always positive by construction).
    EXEC_PRICES = ["Open", "Close"]
    combos = []
    for day_a in range(5):
        for price_a in EXEC_PRICES:
            for day_b in range(5):
                for price_b in EXEC_PRICES:
                    if day_b > day_a or (day_b == day_a and price_a == "Open" and price_b == "Close"):
                        combos.append((day_a, price_a, day_b, price_b))

    # Compute baseline: average weekly Mon Open → Fri Close return (market drift)
    baseline_mean = 0.0
    key_mon_open = (0, "Open")
    key_fri_close = (4, "Close")
    if key_mon_open in wide.columns and key_fri_close in wide.columns:
        e = wide[key_mon_open]
        x = wide[key_fri_close]
        m = e.notna() & x.notna() & (e > 0)
        if m.sum() > 20:
            weekly_rets = ((x[m] - e[m]) / e[m]).values
            baseline_mean = float(np.mean(weekly_rets))

    for day_a, price_a, day_b, price_b in combos:
        key_a = (day_a, price_a)
        key_b = (day_b, price_b)
        if key_a not in wide.columns or key_b not in wide.columns:
            continue

        entry = wide[key_a]
        exit_ = wide[key_b]
        mask = entry.notna() & exit_.notna() & (entry > 0)
        trade_returns = ((exit_[mask] - entry[mask]) / entry[mask]).values

        if len(trade_returns) < MIN_OCCURRENCES:
            continue

        # Scale baseline by approximate holding period fraction of a week
        hold_days = max(day_b - day_a, 1)
        scaled_baseline = baseline_mean * hold_days / 5.0

        entry_lbl = f"{DOW_NAMES[day_a]}_{price_a}"
        exit_lbl = f"{DOW_NAMES[day_b]}_{price_b}"
        desc = f"Buy {entry_lbl} → Sell {exit_lbl}"

        result = _compute_pattern_stats(
            trade_returns,
            ticker, "dow_ohlc", desc, entry_lbl, exit_lbl,
            baseline_mean=scaled_baseline,
        )
        if result:
            results.append(result)

    logger.info("  %s DOW OHLC: %d combos tested", ticker, len(results))
    return results


def scan_dom_groups(
    df: pd.DataFrame,
    ticker: str,
) -> list[PatternResult]:
    """
    Day-of-month group scan.
    Groups: [1-5], [6-10], [11-15], [16-20], [21-25], [26-31]
    For each pair of groups, compute return from group_A close to group_B close.
    6 groups → 6*5 = 30 ordered pairs (entry != exit).
    """
    results = []
    df = df.copy()

    bins = [0, 5, 10, 15, 20, 25, 32]
    labels = ["D01-05", "D06-10", "D11-15", "D16-20", "D21-25", "D26-31"]
    df["dom_group"] = pd.cut(df.index.day, bins=bins, labels=labels, right=True)
    df["month_key"] = df.index.to_period("M")

    for grp_a in labels:
        for grp_b in labels:
            if grp_a == grp_b:
                continue

            trade_returns = []
            for mk, mdf in df.groupby("month_key"):
                a_rows = mdf[mdf["dom_group"] == grp_a]
                b_rows = mdf[mdf["dom_group"] == grp_b]
                if a_rows.empty or b_rows.empty:
                    continue

                # Use last close in each group
                entry_price = a_rows["Close"].iloc[-1]
                exit_price = b_rows["Close"].iloc[-1]

                if pd.notna(entry_price) and pd.notna(exit_price) and entry_price > 0:
                    trade_returns.append((exit_price - entry_price) / entry_price)

            if len(trade_returns) < MIN_OCCURRENCES:
                continue

            desc = f"Buy {grp_a} Close → Sell {grp_b} Close"
            result = _compute_pattern_stats(
                np.array(trade_returns),
                ticker, "dom_group", desc, grp_a, grp_b,
            )
            if result:
                results.append(result)

    logger.info("  %s DOM Groups: %d combos tested", ticker, len(results))
    return results


def scan_week_of_month(
    df: pd.DataFrame,
    ticker: str,
) -> list[PatternResult]:
    """
    Week-of-month scan. Weeks 1-4 (by day: 1-7=W1, 8-14=W2, 15-21=W3, 22+=W4).
    4 weeks → 4*3 = 12 ordered pairs.
    """
    results = []
    df = df.copy()

    def _wom(day):
        return min((day - 1) // 7 + 1, 4)

    df["wom"] = df.index.day.map(_wom)
    df["month_key"] = df.index.to_period("M")

    for wa in range(1, 5):
        for wb in range(1, 5):
            if wa == wb:
                continue

            trade_returns = []
            for mk, mdf in df.groupby("month_key"):
                a_rows = mdf[mdf["wom"] == wa]
                b_rows = mdf[mdf["wom"] == wb]
                if a_rows.empty or b_rows.empty:
                    continue

                entry_price = a_rows["Close"].iloc[-1]
                exit_price = b_rows["Close"].iloc[-1]

                if pd.notna(entry_price) and pd.notna(exit_price) and entry_price > 0:
                    trade_returns.append((exit_price - entry_price) / entry_price)

            if len(trade_returns) < MIN_OCCURRENCES:
                continue

            desc = f"Buy W{wa} Close → Sell W{wb} Close"
            result = _compute_pattern_stats(
                np.array(trade_returns),
                ticker, "week_of_month", desc, f"W{wa}", f"W{wb}",
            )
            if result:
                results.append(result)

    logger.info("  %s Week-of-Month: %d combos tested", ticker, len(results))
    return results


def scan_month_over_month(
    df: pd.DataFrame,
    ticker: str,
) -> list[PatternResult]:
    """
    Month-over-month scan. For each pair (monthA, monthB), compare close of monthA
    to close of monthB in the same year. 12*11 = 132 ordered pairs.
    """
    results = []
    df = df.copy()
    df["month"] = df.index.month
    df["year"] = df.index.year

    # Get monthly last close
    monthly_close = df.groupby(["year", "month"])["Close"].last().unstack(level="month")

    for ma in range(1, 13):
        for mb in range(1, 13):
            if ma == mb:
                continue
            if ma not in monthly_close.columns or mb not in monthly_close.columns:
                continue

            paired = monthly_close[[ma, mb]].dropna()
            if len(paired) < MIN_OCCURRENCES:
                continue

            returns = ((paired[mb] - paired[ma]) / paired[ma]).values
            ma_name = pd.Timestamp(2000, ma, 1).strftime("%b")
            mb_name = pd.Timestamp(2000, mb, 1).strftime("%b")

            desc = f"Buy {ma_name} Close → Sell {mb_name} Close"
            result = _compute_pattern_stats(
                returns, ticker, "month", desc, ma_name, mb_name,
            )
            if result:
                results.append(result)

    logger.info("  %s Month-over-Month: %d combos tested", ticker, len(results))
    return results


# ═══════════════════════════════════════════════════════════════════════
# LAYER 2: Hourly scan
# ═══════════════════════════════════════════════════════════════════════

def scan_hourly_dow(
    df: pd.DataFrame,
    ticker: str,
) -> list[PatternResult]:
    """
    Hourly day-of-week scan (vectorized).
    For each (dayA, hourA) vs (dayB, hourB), compute intra-week return.
    5 days x 7 hours = 35 points → ~595 ordered pairs.
    """
    results = []
    if df.empty:
        return results

    df = df.copy()
    df["dow"] = df.index.dayofweek
    df["hour"] = df.index.hour

    # Filter to Indian market hours
    df = df[df["hour"].isin(INDIA_HOURS)]
    if df.empty:
        return results

    df["week_id"] = df.index.year * 100 + df.index.isocalendar().week.values.astype(int)

    # Pivot: for each (dow, hour), get first Close per week
    pivoted = {}
    for day in range(5):
        for hour in INDIA_HOURS:
            subset = df[(df["dow"] == day) & (df["hour"] == hour)]
            if subset.empty:
                continue
            first_per_week = subset.groupby("week_id")["Close"].first()
            pivoted[(day, hour)] = first_per_week

    if not pivoted:
        return results

    wide = pd.DataFrame(pivoted)

    # Generate all combos
    combos = []
    for day_a in range(5):
        for hour_a in INDIA_HOURS:
            for day_b in range(5):
                for hour_b in INDIA_HOURS:
                    if day_b > day_a or (day_b == day_a and hour_b > hour_a):
                        combos.append((day_a, hour_a, day_b, hour_b))

    for day_a, hour_a, day_b, hour_b in combos:
        key_a = (day_a, hour_a)
        key_b = (day_b, hour_b)
        if key_a not in wide.columns or key_b not in wide.columns:
            continue

        entry = wide[key_a]
        exit_ = wide[key_b]
        mask = entry.notna() & exit_.notna() & (entry > 0)
        trade_returns = ((exit_[mask] - entry[mask]) / entry[mask]).values

        if len(trade_returns) < MIN_OCCURRENCES:
            continue

        entry_lbl = f"{DOW_NAMES[day_a]}_{hour_a:02d}"
        exit_lbl = f"{DOW_NAMES[day_b]}_{hour_b:02d}"
        desc = f"Buy {entry_lbl} → Sell {exit_lbl}"

        result = _compute_pattern_stats(
            trade_returns,
            ticker, "hourly_dow", desc, entry_lbl, exit_lbl,
        )
        if result:
            results.append(result)

    logger.info("  %s Hourly DOW: %d combos tested", ticker, len(results))
    return results


# ═══════════════════════════════════════════════════════════════════════
# CONDITIONAL: Celestial-filtered patterns
# ═══════════════════════════════════════════════════════════════════════

def scan_dow_conditional(
    df: pd.DataFrame,
    ticker: str,
    celestial_df: pd.DataFrame,
) -> list[PatternResult]:
    """
    Day-of-week patterns filtered by celestial conditions:
      - Moon waning (phase > 0.5)
      - High tidal force (above median)
      - Quiet geomagnetic (Kp < 3)

    Uses daily OHLC data cross-referenced with celestial/nature data.
    """
    results = []
    if celestial_df is None or celestial_df.empty:
        return results

    df = df.copy()
    df["dow"] = df.index.dayofweek
    df["week"] = df.index.isocalendar().week.values.astype(int)
    df["year"] = df.index.year

    # Align celestial data
    cel = celestial_df.reindex(df.index, method="nearest", tolerance="1D")

    conditions = {}

    # Moon waning: phase > 0.5
    if "moon_phase" in cel.columns:
        conditions["moon_waning"] = cel["moon_phase"] > 0.5

    # High tidal force: above median
    if "tidal_force_combined" in cel.columns:
        median_tidal = cel["tidal_force_combined"].median()
        conditions["high_tidal"] = cel["tidal_force_combined"] > median_tidal

    # Quiet geomagnetic: Kp < 3 (look for kp_mean in celestial or nature data)
    if "kp_mean" in cel.columns:
        conditions["quiet_geomag"] = cel["kp_mean"] < 3.0

    # For each condition, run a simplified DOW scan (Close-to-Close only)
    for cond_name, mask in conditions.items():
        cond_df = df[mask]
        if len(cond_df) < MIN_OCCURRENCES * 2:
            continue

        weekly_groups = cond_df.groupby(["year", "week"])

        for day_a in range(5):
            for day_b in range(day_a + 1, 5):
                trade_returns = []
                for (yr, wk), wk_df in weekly_groups:
                    a_rows = wk_df[wk_df["dow"] == day_a]
                    b_rows = wk_df[wk_df["dow"] == day_b]
                    if a_rows.empty or b_rows.empty:
                        continue
                    ep = a_rows["Close"].iloc[0]
                    xp = b_rows["Close"].iloc[0]
                    if pd.notna(ep) and pd.notna(xp) and ep > 0:
                        trade_returns.append((xp - ep) / ep)

                if len(trade_returns) < MIN_OCCURRENCES:
                    continue

                entry_lbl = f"{DOW_NAMES[day_a]}_Close"
                exit_lbl = f"{DOW_NAMES[day_b]}_Close"
                desc = f"[{cond_name}] Buy {entry_lbl} → Sell {exit_lbl}"

                result = _compute_pattern_stats(
                    np.array(trade_returns),
                    ticker, "conditional_dow", desc, entry_lbl, exit_lbl,
                    condition=cond_name,
                )
                if result:
                    results.append(result)

    logger.info("  %s Conditional DOW: %d combos tested", ticker, len(results))
    return results


# ═══════════════════════════════════════════════════════════════════════
# FDR CORRECTION + FILTERING
# ═══════════════════════════════════════════════════════════════════════

def apply_fdr_and_filter(
    all_results: list[PatternResult],
) -> list[PatternResult]:
    """
    Apply Benjamini-Hochberg FDR correction on train p-values,
    then filter by:
      1. FDR-adjusted p < FDR_ALPHA (train)
      2. Test p < 0.05 (OOS validation)
      3. Effect size > MIN_EFFECT_BPS
      4. Same direction in train and test
    """
    if not all_results:
        return []

    n = len(all_results)
    # Sort by train p-value for BH procedure
    sorted_results = sorted(all_results, key=lambda r: r.train_p_value)
    p_values = np.array([r.train_p_value for r in sorted_results])

    # Benjamini-Hochberg
    ranks = np.arange(1, n + 1)
    bh_critical = ranks / n * FDR_ALPHA
    # Find largest k where p(k) <= k/n * alpha
    rejected = p_values <= bh_critical

    # Assign FDR-adjusted p-values
    fdr_pvals = np.minimum(p_values * n / ranks, 1.0)
    # Make monotone (enforce non-decreasing from the end)
    for i in range(n - 2, -1, -1):
        fdr_pvals[i] = min(fdr_pvals[i], fdr_pvals[i + 1])

    for i, r in enumerate(sorted_results):
        r.fdr_p_value = float(fdr_pvals[i])

    # Filter
    survivors = []
    for r in sorted_results:
        # 1. FDR-significant in train
        if r.fdr_p_value >= FDR_ALPHA:
            continue
        # 2. Significant in test (relaxed)
        if r.test_p_value >= 0.05:
            continue
        # 3. Effect size
        if abs(r.train_mean_ret) < MIN_EFFECT_BPS * 1e-4:
            continue
        # 4. Same direction in train and test
        if np.sign(r.train_mean_ret) != np.sign(r.test_mean_ret):
            continue

        r.significant = True
        survivors.append(r)

    logger.info(
        "FDR filter: %d tested → %d FDR-significant → %d survived all filters",
        n,
        int(np.sum(rejected)),
        len(survivors),
    )
    return survivors


# ═══════════════════════════════════════════════════════════════════════
# MAIN SCAN ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════════════

def run_all_scans(
    daily_data: dict[str, pd.DataFrame],
    hourly_data: dict[str, pd.DataFrame],
    celestial_df: Optional[pd.DataFrame] = None,
    nature_df: Optional[pd.DataFrame] = None,
) -> tuple[list[PatternResult], list[PatternResult]]:
    """
    Run all pattern scans across all tickers.

    Returns:
        (all_results, significant_results)
    """
    all_results: list[PatternResult] = []

    # Merge celestial + nature for conditional scans
    cond_df = None
    if celestial_df is not None and not celestial_df.empty:
        cond_df = celestial_df.copy()
        if nature_df is not None and not nature_df.empty:
            # Add kp_mean from nature data if available
            if "kp_mean" in nature_df.columns and "kp_mean" not in cond_df.columns:
                cond_df = cond_df.join(nature_df[["kp_mean"]], how="left")

    for ticker, df in daily_data.items():
        logger.info("Scanning %s (daily: %d bars)...", ticker, len(df))

        # Layer 1: Daily scans
        all_results.extend(scan_dow_ohlc(df, ticker))
        all_results.extend(scan_dom_groups(df, ticker))
        all_results.extend(scan_week_of_month(df, ticker))
        all_results.extend(scan_month_over_month(df, ticker))

        # Conditional scans
        if cond_df is not None:
            all_results.extend(scan_dow_conditional(df, ticker, cond_df))

    # Layer 2: Hourly scans
    for ticker, df in hourly_data.items():
        if len(df) < 100:
            continue
        logger.info("Scanning %s (hourly: %d bars)...", ticker, len(df))
        all_results.extend(scan_hourly_dow(df, ticker))

    logger.info("Total hypotheses tested: %d", len(all_results))

    # Apply FDR correction and filtering
    significant = apply_fdr_and_filter(all_results)

    return all_results, significant
