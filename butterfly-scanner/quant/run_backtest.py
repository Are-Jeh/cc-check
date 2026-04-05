#!/usr/bin/env python3
"""
Backtest Runner
================
Load cached daily data, run all strategies, combine via fund manager,
print results, save outputs.
"""

import sys
import os
import logging
import warnings

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

warnings.filterwarnings("ignore")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("backtest")

import numpy as np
import pandas as pd
from pathlib import Path
from rich.console import Console
from rich.table import Table

console = Console()

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)


def main():
    from quant.ohlc_data import load_cached_daily
    from quant.strategies import (
        run_rsi2_mean_reversion,
        run_pairs_trading,
        run_dual_momentum,
        StrategyResult,
    )
    from quant.fund_manager import run_fund_manager

    # ── Load data ────────────────────────────────────────────────────
    console.rule("[bold blue]Loading Cached Daily Data")
    data = load_cached_daily()

    available = list(data.keys())
    console.print(f"  Available tickers: {available}")
    for k, v in data.items():
        console.print(f"    {k}: {len(v)} bars, {v.index.min().date()} to {v.index.max().date()}")

    required = {"nifty50", "banknifty", "gold"}
    missing = required - set(available)
    if missing:
        console.print(f"[red]Missing required data: {missing}. Run ohlc_data.py first.[/red]")
        sys.exit(1)

    # ── Strategy 1: RSI(2) Mean Reversion on Nifty 50 ───────────────
    console.rule("[bold blue]Strategy 1: RSI(2) Cumulative Mean Reversion")
    rsi_result = run_rsi2_mean_reversion(data["nifty50"], capital=50_000.0)
    _print_strategy_summary(rsi_result)

    # Also run on BankNifty for diversity
    console.rule("[bold blue]Strategy 1b: RSI(2) on BankNifty")
    rsi_bank = run_rsi2_mean_reversion(data["banknifty"], capital=50_000.0, name="RSI2_BankNifty")
    _print_strategy_summary(rsi_bank)

    # ── Strategy 2: Pairs Trading ────────────────────────────────────
    console.rule("[bold blue]Strategy 2: Pairs Trading (Nifty50 vs BankNifty)")
    pairs_result = run_pairs_trading(
        data["nifty50"], data["banknifty"],
        capital=50_000.0,
        name_a="nifty50", name_b="banknifty",
    )
    _print_strategy_summary(pairs_result)

    # ── Strategy 3: Dual Momentum ────────────────────────────────────
    console.rule("[bold blue]Strategy 3: Dual Momentum (Nifty50 vs Gold)")
    dual_mom = run_dual_momentum(
        data["nifty50"], data["gold"],
        capital=50_000.0,
        name_equity="nifty50", name_gold="gold",
    )
    _print_strategy_summary(dual_mom)

    # ── Fund Manager ─────────────────────────────────────────────────
    console.rule("[bold blue]Fund Manager: Combined Portfolio")
    all_strategies = [rsi_result, pairs_result, dual_mom]
    fund, benchmark = run_fund_manager(
        all_strategies,
        benchmark_close=data["nifty50"]["Close"],
        initial_capital=50_000.0,
    )

    # ── Results Table ────────────────────────────────────────────────
    console.rule("[bold green]BACKTEST RESULTS")

    table = Table(
        title="Strategy Performance Summary",
        show_lines=True,
        header_style="bold cyan",
    )
    table.add_column("Strategy", min_width=28)
    table.add_column("CAGR", justify="center", width=10)
    table.add_column("Sharpe", justify="center", width=10)
    table.add_column("Max DD", justify="center", width=10)
    table.add_column("Win Rate", justify="center", width=10)
    table.add_column("# Trades", justify="center", width=9)
    table.add_column("Avg Hold", justify="center", width=10)
    table.add_column("Total Ret", justify="center", width=10)

    for sr in [rsi_result, rsi_bank, pairs_result, dual_mom]:
        _add_strategy_row(table, sr)

    # Fund manager row
    table.add_row(
        f"[bold yellow]{fund.name}[/bold yellow]",
        _fmt_pct(fund.cagr),
        _fmt_sharpe(fund.sharpe),
        _fmt_dd(fund.max_drawdown),
        "-",
        "-",
        "-",
        _fmt_pct(fund.total_return),
    )

    # Benchmark row
    table.add_row(
        f"[bold white]{benchmark.name}[/bold white]",
        _fmt_pct(benchmark.cagr),
        _fmt_sharpe(benchmark.sharpe),
        _fmt_dd(benchmark.max_drawdown),
        "-",
        "-",
        "-",
        _fmt_pct(benchmark.total_return),
    )

    console.print(table)

    # ── Save outputs ─────────────────────────────────────────────────
    console.rule("[bold blue]Saving Outputs")

    # Equity curves
    eq_df = pd.DataFrame({
        rsi_result.name: rsi_result.equity_curve,
        rsi_bank.name: rsi_bank.equity_curve,
        pairs_result.name: pairs_result.equity_curve,
        dual_mom.name: dual_mom.equity_curve,
        fund.name: fund.equity_curve,
        benchmark.name: benchmark.equity_curve,
    })
    eq_path = OUTPUT_DIR / "equity_curves.csv"
    eq_df.to_csv(eq_path)
    console.print(f"  Equity curves -> {eq_path}")

    # Trade log
    all_trades = []
    for sr in [rsi_result, rsi_bank, pairs_result, dual_mom]:
        for t in sr.trades:
            all_trades.append({
                "strategy": t.strategy,
                "entry_date": t.entry_date,
                "exit_date": t.exit_date,
                "entry_price": round(t.entry_price, 2),
                "exit_price": round(t.exit_price, 2),
                "pct_return": round(t.pct_return * 100, 2),
                "holding_days": t.holding_days,
                "side": t.side,
            })
    trade_df = pd.DataFrame(all_trades)
    trade_path = OUTPUT_DIR / "trade_log.csv"
    trade_df.to_csv(trade_path, index=False)
    console.print(f"  Trade log -> {trade_path} ({len(trade_df)} trades)")

    # Allocations
    if not fund.allocations.empty:
        alloc_path = OUTPUT_DIR / "fund_allocations.csv"
        fund.allocations.to_csv(alloc_path)
        console.print(f"  Fund allocations -> {alloc_path}")

    console.rule("[bold green]DONE")


# ── Formatting helpers ───────────────────────────────────────────────

def _fmt_pct(v: float) -> str:
    s = f"{v * 100:.1f}%"
    return f"[green]{s}[/green]" if v > 0 else f"[red]{s}[/red]"


def _fmt_sharpe(v: float) -> str:
    s = f"{v:.2f}"
    if v > 1.0:
        return f"[bold green]{s}[/bold green]"
    elif v > 0.5:
        return f"[green]{s}[/green]"
    elif v > 0:
        return f"[yellow]{s}[/yellow]"
    return f"[red]{s}[/red]"


def _fmt_dd(v: float) -> str:
    s = f"{v * 100:.1f}%"
    if v > -0.10:
        return f"[green]{s}[/green]"
    elif v > -0.20:
        return f"[yellow]{s}[/yellow]"
    return f"[red]{s}[/red]"


def _print_strategy_summary(sr) -> None:
    """Quick one-liner summary after each strategy runs."""
    console.print(
        f"  {sr.name}: {sr.n_trades} trades | "
        f"CAGR={sr.cagr*100:.1f}% | Sharpe={sr.sharpe:.2f} | "
        f"MaxDD={sr.max_drawdown*100:.1f}% | WinRate={sr.win_rate*100:.0f}%"
    )


def _add_strategy_row(table: Table, sr) -> None:
    table.add_row(
        sr.name,
        _fmt_pct(sr.cagr),
        _fmt_sharpe(sr.sharpe),
        _fmt_dd(sr.max_drawdown),
        f"{sr.win_rate * 100:.0f}%" if sr.trades else "-",
        str(sr.n_trades),
        f"{sr.avg_holding_days:.0f}d" if sr.trades else "-",
        _fmt_pct(sr.total_return),
    )


if __name__ == "__main__":
    main()
