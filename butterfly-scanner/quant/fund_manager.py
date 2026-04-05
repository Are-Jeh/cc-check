"""
Fund Manager
=============
Allocates capital across strategies based on recent Sharpe ratio.
Rebalances monthly. Tracks portfolio-level metrics.
"""

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from quant.strategies import StrategyResult, compute_metrics, Trade

logger = logging.getLogger(__name__)


@dataclass
class FundResult:
    name: str
    equity_curve: pd.Series
    allocations: pd.DataFrame  # date x strategy allocation weights
    cagr: float
    sharpe: float
    max_drawdown: float
    total_return: float


def compute_rolling_sharpe(equity: pd.Series, window: int = 63) -> pd.Series:
    """Rolling annualized Sharpe over ~3 months."""
    daily_ret = equity.pct_change()
    rolling_mean = daily_ret.rolling(window, min_periods=window // 2).mean()
    rolling_std = daily_ret.rolling(window, min_periods=window // 2).std()
    return (rolling_mean / rolling_std.replace(0, np.nan)) * np.sqrt(252)


def run_fund_manager(
    strategy_results: list[StrategyResult],
    benchmark_close: pd.Series,
    initial_capital: float = 50_000.0,
    min_alloc: float = 0.20,
    max_alloc: float = 0.50,
    sharpe_lookback: int = 63,
) -> tuple[FundResult, StrategyResult]:
    """
    Combine strategies with dynamic Sharpe-based allocation.

    Returns (fund_result, benchmark_result).
    """
    name = "FundManager"

    # Collect all equity curves and align to common dates
    curves = {}
    for sr in strategy_results:
        curves[sr.name] = sr.equity_curve

    all_eq = pd.DataFrame(curves)
    all_eq = all_eq.dropna(how="all").ffill()

    # Daily returns per strategy
    strat_returns = all_eq.pct_change().fillna(0.0)

    # Identify rebalance dates (last trading day of each month)
    month_groups = all_eq.groupby(all_eq.index.to_period("M"))
    rebal_set = set(group.index[-1] for _, group in month_groups)

    n_strats = len(strategy_results)
    strat_names = [sr.name for sr in strategy_results]

    # Default equal allocation
    current_weights = pd.Series(1.0 / n_strats, index=strat_names)

    portfolio_values: list[float] = []
    portfolio_dates: list[pd.Timestamp] = []
    alloc_records: list[dict] = []

    portfolio_value = initial_capital

    for i, dt in enumerate(all_eq.index):
        # Rebalance at month-end
        if dt in rebal_set and i >= sharpe_lookback:
            # Compute rolling Sharpe for each strategy up to this point
            sharpes = {}
            for sn in strat_names:
                hist = all_eq[sn].iloc[:i + 1]
                rs = compute_rolling_sharpe(hist, window=sharpe_lookback)
                latest = rs.iloc[-1] if len(rs) > 0 and not pd.isna(rs.iloc[-1]) else 0.0
                sharpes[sn] = max(latest, 0.0)  # floor at 0

            total_sharpe = sum(sharpes.values())
            if total_sharpe > 0:
                raw_weights = {s: sharpes[s] / total_sharpe for s in strat_names}
            else:
                raw_weights = {s: 1.0 / n_strats for s in strat_names}

            # Apply min/max constraints
            weights = _apply_constraints(raw_weights, min_alloc, max_alloc)
            current_weights = pd.Series(weights)

            alloc_records.append({"date": dt, **weights})
            logger.debug("Rebalance %s: %s", dt.date(), {k: f"{v:.1%}" for k, v in weights.items()})

        # Daily P&L
        if i > 0:
            day_ret = 0.0
            for sn in strat_names:
                if sn in strat_returns.columns and dt in strat_returns.index:
                    w = current_weights[sn] if sn in current_weights.index else 0.0
                    day_ret += w * strat_returns.at[dt, sn]
            portfolio_value *= (1.0 + day_ret)

        portfolio_values.append(portfolio_value)
        portfolio_dates.append(dt)

    equity = pd.Series(portfolio_values, index=portfolio_dates, name=name)
    alloc_df = pd.DataFrame(alloc_records).set_index("date") if alloc_records else pd.DataFrame()

    metrics = compute_metrics(equity, [])

    fund = FundResult(
        name=name,
        equity_curve=equity,
        allocations=alloc_df,
        cagr=metrics["cagr"],
        sharpe=metrics["sharpe"],
        max_drawdown=metrics["max_drawdown"],
        total_return=metrics["total_return"],
    )

    # Benchmark: buy-and-hold Nifty 50
    bench_close = benchmark_close.loc[benchmark_close.index.isin(all_eq.index)].copy()
    if len(bench_close) > 0:
        bench_equity = (bench_close / bench_close.iloc[0]) * initial_capital
        bench_equity.name = "Nifty50_BuyHold"
        bench_metrics = compute_metrics(bench_equity, [])
        benchmark = StrategyResult(
            name="Nifty50_BuyHold",
            trades=[],
            equity_curve=bench_equity,
            **bench_metrics,
        )
    else:
        benchmark = StrategyResult(
            name="Nifty50_BuyHold", trades=[],
            equity_curve=pd.Series(dtype=float),
            cagr=0, sharpe=0, max_drawdown=0, win_rate=0,
            avg_holding_days=0, total_return=0,
        )

    logger.info("Fund: CAGR=%.2f%%, Sharpe=%.2f, MaxDD=%.1f%%",
                fund.cagr * 100, fund.sharpe, fund.max_drawdown * 100)
    logger.info("Benchmark: CAGR=%.2f%%, Sharpe=%.2f, MaxDD=%.1f%%",
                benchmark.cagr * 100, benchmark.sharpe, benchmark.max_drawdown * 100)

    return fund, benchmark


def _apply_constraints(
    raw: dict[str, float],
    min_alloc: float,
    max_alloc: float,
) -> dict[str, float]:
    """Clip weights to [min_alloc, max_alloc] and re-normalize to sum=1."""
    n = len(raw)
    if n == 0:
        return raw

    # If all zero, equal weight
    if all(v == 0 for v in raw.values()):
        return {k: 1.0 / n for k in raw}

    clipped = {k: np.clip(v, min_alloc, max_alloc) for k, v in raw.items()}
    total = sum(clipped.values())
    if total > 0:
        clipped = {k: v / total for k, v in clipped.items()}
    return clipped
