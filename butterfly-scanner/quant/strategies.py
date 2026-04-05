"""
Backtested Trading Strategies
==============================
Three independent strategies with full trade-level tracking.
All use vectorized pandas operations. No lookahead bias.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ── Data structures ──────────────────────────────────────────────────

@dataclass
class Trade:
    strategy: str
    entry_date: pd.Timestamp
    exit_date: pd.Timestamp
    entry_price: float
    exit_price: float
    pct_return: float
    holding_days: int
    side: str = "long"  # "long" or "short"


@dataclass
class StrategyResult:
    name: str
    trades: list[Trade]
    equity_curve: pd.Series  # daily portfolio value (indexed by date)
    cagr: float
    sharpe: float
    max_drawdown: float
    win_rate: float
    avg_holding_days: float
    total_return: float

    @property
    def n_trades(self) -> int:
        return len(self.trades)


# ── Helpers ──────────────────────────────────────────────────────────

def compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's smoothed RSI."""
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)

    # First average uses simple mean, then Wilder's EMA
    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi


def compute_sma(close: pd.Series, period: int) -> pd.Series:
    return close.rolling(window=period, min_periods=period).mean()


def compute_metrics(equity: pd.Series, trades: list[Trade]) -> dict:
    """Compute CAGR, Sharpe, MaxDD, win rate, avg holding from an equity curve."""
    if len(equity) < 2:
        return dict(cagr=0, sharpe=0, max_drawdown=0, win_rate=0, avg_holding_days=0, total_return=0)

    # Daily returns
    daily_ret = equity.pct_change().dropna()

    # Total return
    total_return = (equity.iloc[-1] / equity.iloc[0]) - 1.0

    # CAGR
    n_years = (equity.index[-1] - equity.index[0]).days / 365.25
    if n_years > 0 and equity.iloc[-1] > 0:
        cagr = (equity.iloc[-1] / equity.iloc[0]) ** (1.0 / n_years) - 1.0
    else:
        cagr = 0.0

    # Sharpe (annualized, risk-free = 0 for simplicity)
    if daily_ret.std() > 0:
        sharpe = (daily_ret.mean() / daily_ret.std()) * np.sqrt(252)
    else:
        sharpe = 0.0

    # Max drawdown
    cummax = equity.cummax()
    drawdown = (equity - cummax) / cummax
    max_drawdown = drawdown.min()

    # Win rate
    if trades:
        wins = sum(1 for t in trades if t.pct_return > 0)
        win_rate = wins / len(trades)
        avg_holding = np.mean([t.holding_days for t in trades])
    else:
        win_rate = 0.0
        avg_holding = 0.0

    return dict(
        cagr=cagr,
        sharpe=sharpe,
        max_drawdown=max_drawdown,
        win_rate=win_rate,
        avg_holding_days=avg_holding,
        total_return=total_return,
    )


# ── Strategy 1: RSI(2) Cumulative Mean Reversion ────────────────────

def run_rsi2_mean_reversion(
    df: pd.DataFrame,
    capital: float = 50_000.0,
    name: str = "RSI2_MeanRev",
) -> StrategyResult:
    """
    Larry Connors RSI(2) cumulative mean-reversion on a single instrument.

    Buy:  cumulative RSI(2) < 25 AND close > SMA(200)
    Sell: cumulative RSI(2) > 70 OR close < SMA(200)

    Thresholds loosened from original 10/90 to 25/70 for more trades on indices.
    """
    close = df["Close"].copy()
    close = close.dropna()

    rsi2 = compute_rsi(close, period=2)
    cum_rsi2 = rsi2 + rsi2.shift(1)  # today + yesterday
    sma200 = compute_sma(close, 200)

    # Generate signals (vectorized prep, then iterate for state tracking)
    buy_cond = (cum_rsi2 < 25) & (close > sma200)
    sell_cond = (cum_rsi2 > 70) | (close < sma200)

    # Walk forward tracking positions
    trades: list[Trade] = []
    equity_values: list[float] = []
    equity_dates: list[pd.Timestamp] = []

    in_position = False
    entry_price = 0.0
    entry_date = pd.Timestamp("2000-01-01")
    current_capital = capital

    for i in range(len(close)):
        dt = close.index[i]
        px = close.iloc[i]

        if not in_position:
            equity_values.append(current_capital)
            equity_dates.append(dt)
            # Check buy — use signal from previous bar to avoid lookahead
            if i >= 1 and buy_cond.iloc[i - 1]:
                in_position = True
                entry_price = px  # enter at today's open ~ close proxy
                entry_date = dt
        else:
            # Mark to market
            unrealized = (px / entry_price - 1.0)
            equity_values.append(current_capital * (1.0 + unrealized))
            equity_dates.append(dt)
            # Check sell — use signal from previous bar
            if i >= 1 and sell_cond.iloc[i - 1]:
                pct_ret = px / entry_price - 1.0
                holding = (dt - entry_date).days
                trades.append(Trade(
                    strategy=name,
                    entry_date=entry_date,
                    exit_date=dt,
                    entry_price=entry_price,
                    exit_price=px,
                    pct_return=pct_ret,
                    holding_days=holding,
                ))
                current_capital *= (1.0 + pct_ret)
                in_position = False

    equity = pd.Series(equity_values, index=equity_dates, name=name)
    metrics = compute_metrics(equity, trades)
    logger.info("%s: %d trades, CAGR=%.2f%%, Sharpe=%.2f", name, len(trades),
                metrics["cagr"] * 100, metrics["sharpe"])

    return StrategyResult(
        name=name,
        trades=trades,
        equity_curve=equity,
        **metrics,
    )


# ── Strategy 2: Pairs Trading (Z-Score Mean Reversion) ──────────────

def run_pairs_trading(
    df_a: pd.DataFrame,
    df_b: pd.DataFrame,
    capital: float = 50_000.0,
    z_entry: float = 2.0,
    z_exit: float = -0.5,
    z_stop: float = 3.5,
    lookback: int = 60,
    name_a: str = "nifty50",
    name_b: str = "banknifty",
) -> StrategyResult:
    """
    Pairs trading: go long the underperformer when spread z-score < -z_entry.
    Exit when z reverts to z_exit or blows past z_stop.
    """
    name = f"Pairs_{name_a}_vs_{name_b}"

    close_a = df_a["Close"].dropna()
    close_b = df_b["Close"].dropna()

    # Align on common dates
    common = close_a.index.intersection(close_b.index)
    close_a = close_a.loc[common]
    close_b = close_b.loc[common]

    # Log price ratio spread
    spread = np.log(close_a / close_b)
    spread_mean = spread.rolling(lookback, min_periods=lookback).mean()
    spread_std = spread.rolling(lookback, min_periods=lookback).std()
    z_score = (spread - spread_mean) / spread_std.replace(0, np.nan)

    trades: list[Trade] = []
    equity_values: list[float] = []
    equity_dates: list[pd.Timestamp] = []

    in_position = False
    long_asset = ""  # which asset we're long
    entry_price = 0.0
    entry_date = pd.Timestamp("2000-01-01")
    current_capital = capital

    for i in range(len(z_score)):
        dt = z_score.index[i]
        z = z_score.iloc[i]

        if np.isnan(z):
            equity_values.append(current_capital)
            equity_dates.append(dt)
            continue

        if not in_position:
            equity_values.append(current_capital)
            equity_dates.append(dt)
            # Use previous bar's z to avoid lookahead
            if i >= 1:
                z_prev = z_score.iloc[i - 1]
                if not np.isnan(z_prev) and z_prev < -z_entry:
                    # A is cheap relative to B -> go long A
                    in_position = True
                    long_asset = name_a
                    entry_price = close_a.iloc[i]
                    entry_date = dt
                elif not np.isnan(z_prev) and z_prev > z_entry:
                    # B is cheap relative to A -> go long B
                    in_position = True
                    long_asset = name_b
                    entry_price = close_b.iloc[i]
                    entry_date = dt
        else:
            # Mark to market
            if long_asset == name_a:
                current_px = close_a.iloc[i]
            else:
                current_px = close_b.iloc[i]
            unrealized = current_px / entry_price - 1.0
            equity_values.append(current_capital * (1.0 + unrealized))
            equity_dates.append(dt)

            # Exit conditions (use previous bar's z)
            if i >= 1:
                z_prev = z_score.iloc[i - 1]
                if np.isnan(z_prev):
                    continue
                should_exit = False
                if long_asset == name_a and (z_prev > z_exit or z_prev < -z_stop):
                    should_exit = True
                elif long_asset == name_b and (z_prev < -z_exit or z_prev > z_stop):
                    should_exit = True

                if should_exit:
                    pct_ret = current_px / entry_price - 1.0
                    holding = (dt - entry_date).days
                    trades.append(Trade(
                        strategy=name,
                        entry_date=entry_date,
                        exit_date=dt,
                        entry_price=entry_price,
                        exit_price=current_px,
                        pct_return=pct_ret,
                        holding_days=holding,
                    ))
                    current_capital *= (1.0 + pct_ret)
                    in_position = False

    equity = pd.Series(equity_values, index=equity_dates, name=name)
    metrics = compute_metrics(equity, trades)
    logger.info("%s: %d trades, CAGR=%.2f%%, Sharpe=%.2f", name, len(trades),
                metrics["cagr"] * 100, metrics["sharpe"])

    return StrategyResult(
        name=name,
        trades=trades,
        equity_curve=equity,
        **metrics,
    )


# ── Strategy 3: Dual Momentum ───────────────────────────────────────

def run_dual_momentum(
    df_equity: pd.DataFrame,
    df_gold: pd.DataFrame,
    capital: float = 50_000.0,
    lookback_months: int = 12,
    name_equity: str = "nifty50",
    name_gold: str = "gold",
) -> StrategyResult:
    """
    Dual momentum: compare 12-month returns of equity vs gold.
    Hold the better performer if its return > 0, else cash.
    Rebalance on last trading day of each month.
    """
    name = f"DualMom_{name_equity}_vs_{name_gold}"

    close_eq = df_equity["Close"].dropna()
    close_gd = df_gold["Close"].dropna()

    # Align
    common = close_eq.index.intersection(close_gd.index)
    close_eq = close_eq.loc[common]
    close_gd = close_gd.loc[common]

    # 12-month (~252 trading day) returns
    lb = lookback_months * 21  # approximate trading days
    ret_eq_12m = close_eq.pct_change(lb)
    ret_gd_12m = close_gd.pct_change(lb)

    # Identify last trading day of each month
    month_groups = close_eq.groupby(close_eq.index.to_period("M"))
    rebalance_set = set(group.index[-1] for _, group in month_groups)

    trades: list[Trade] = []
    equity_values: list[float] = []
    equity_dates: list[pd.Timestamp] = []

    current_capital = capital
    holding = "cash"  # "equity", "gold", "cash"
    entry_price = 0.0
    entry_date = pd.Timestamp("2000-01-01")

    for i in range(len(close_eq)):
        dt = close_eq.index[i]
        px_eq = close_eq.iloc[i]
        px_gd = close_gd.iloc[i]

        # Mark to market
        if holding == "equity":
            unrealized = px_eq / entry_price - 1.0
            equity_values.append(current_capital * (1.0 + unrealized))
        elif holding == "gold":
            unrealized = px_gd / entry_price - 1.0
            equity_values.append(current_capital * (1.0 + unrealized))
        else:
            equity_values.append(current_capital)
        equity_dates.append(dt)

        # Rebalance on month-end
        if dt not in rebalance_set:
            continue
        if pd.isna(ret_eq_12m.iloc[i]) or pd.isna(ret_gd_12m.iloc[i]):
            continue

        r_eq = ret_eq_12m.iloc[i]
        r_gd = ret_gd_12m.iloc[i]

        # Determine target
        if r_eq > r_gd and r_eq > 0:
            target = "equity"
        elif r_gd > r_eq and r_gd > 0:
            target = "gold"
        else:
            target = "cash"

        # Close existing position if switching
        if holding != target and holding != "cash":
            if holding == "equity":
                exit_px = px_eq
            else:
                exit_px = px_gd
            pct_ret = exit_px / entry_price - 1.0
            h_days = (dt - entry_date).days
            trades.append(Trade(
                strategy=name,
                entry_date=entry_date,
                exit_date=dt,
                entry_price=entry_price,
                exit_price=exit_px,
                pct_return=pct_ret,
                holding_days=h_days,
            ))
            current_capital *= (1.0 + pct_ret)
            holding = "cash"

        # Open new position
        if target != "cash" and holding == "cash":
            holding = target
            if target == "equity":
                entry_price = px_eq
            else:
                entry_price = px_gd
            entry_date = dt

    equity = pd.Series(equity_values, index=equity_dates, name=name)
    metrics = compute_metrics(equity, trades)
    logger.info("%s: %d trades, CAGR=%.2f%%, Sharpe=%.2f", name, len(trades),
                metrics["cagr"] * 100, metrics["sharpe"])

    return StrategyResult(
        name=name,
        trades=trades,
        equity_curve=equity,
        **metrics,
    )
