#!/usr/bin/env python3
"""
Overnight Signal Runner
========================
Load cached daily data, run overnight multi-market model with walk-forward
validation, run gap-fade backtest, print results with rich console,
save outputs to CSV.
"""

import sys
import os
import warnings
import logging
import time
from pathlib import Path

# Ensure parent dir is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

warnings.filterwarnings("ignore")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("overnight")

import numpy as np
import pandas as pd
from rich.console import Console
from rich.table import Table

console = Console()

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)


# ── Display helpers ──────────────────────────────────────────────────

def print_model_accuracy_by_year(results: list) -> None:
    """Rich table: model accuracy broken down by year."""
    if not results:
        return

    # Collect all years
    all_years = sorted(set(
        yr for r in results for yr in r.accuracy_by_year.keys()
    ))

    table = Table(
        title="Overnight Model — Accuracy by Year",
        show_lines=True, header_style="bold cyan",
    )
    table.add_column("Model", min_width=22)
    for yr in all_years:
        table.add_column(str(yr), justify="center", width=8)
    table.add_column("Overall", justify="center", width=9, style="bold")

    for r in results:
        row = [r.name]
        for yr in all_years:
            acc = r.accuracy_by_year.get(yr)
            if acc is not None:
                style = "green" if acc > 0.55 else ("yellow" if acc > 0.50 else "red")
                row.append(f"[{style}]{acc*100:.1f}%[/{style}]")
            else:
                row.append("-")
        style = "bold green" if r.accuracy > 0.55 else ("yellow" if r.accuracy > 0.50 else "red")
        row.append(f"[{style}]{r.accuracy*100:.1f}%[/{style}]")
        table.add_row(*row)

    console.print(table)


def print_model_performance(results: list) -> None:
    """Rich table: overall model performance metrics."""
    table = Table(
        title="Overnight Model — Performance Summary",
        show_lines=True, header_style="bold cyan",
    )
    table.add_column("Model", min_width=22)
    table.add_column("Accuracy", justify="center", width=10)
    table.add_column("Sharpe", justify="center", width=10)
    table.add_column("CAGR", justify="center", width=10)
    table.add_column("Max DD", justify="center", width=10)
    table.add_column("Total Ret", justify="center", width=10)
    table.add_column("# Preds", justify="center", width=9)

    for r in results:
        acc_s = "green" if r.accuracy > 0.55 else ("yellow" if r.accuracy > 0.50 else "red")
        sh_s = "bold green" if r.sharpe > 0.5 else ("yellow" if r.sharpe > 0 else "red")
        cagr_s = "green" if r.cagr > 0 else "red"
        dd_s = "green" if r.max_drawdown > -0.15 else ("yellow" if r.max_drawdown > -0.30 else "red")

        table.add_row(
            r.name,
            f"[{acc_s}]{r.accuracy*100:.1f}%[/{acc_s}]",
            f"[{sh_s}]{r.sharpe:.2f}[/{sh_s}]",
            f"[{cagr_s}]{r.cagr*100:.1f}%[/{cagr_s}]",
            f"[{dd_s}]{r.max_drawdown*100:.1f}%[/{dd_s}]",
            f"{r.total_return*100:.1f}%",
            str(r.n_predictions),
        )

    console.print(table)


def print_gap_fade_results(gap_results: list) -> None:
    """Rich table: gap-fade strategy results by bucket."""
    table = Table(
        title="Gap-Fade Strategy — Results by Gap Size",
        show_lines=True, header_style="bold magenta",
    )
    table.add_column("Bucket", min_width=16)
    table.add_column("Action", justify="center", width=8)
    table.add_column("# Trades", justify="center", width=9)
    table.add_column("Fill Rate", justify="center", width=10)
    table.add_column("Win Rate", justify="center", width=10)
    table.add_column("Avg Return", justify="center", width=11)
    table.add_column("Total Ret", justify="center", width=10)
    table.add_column("Sharpe", justify="center", width=10)

    from quant.overnight_signal import GAP_BUCKETS
    bucket_actions = {b[0]: b[3] for b in GAP_BUCKETS}

    for r in gap_results:
        action = bucket_actions.get(r.bucket, "?")
        wr_s = "green" if r.win_rate > 0.55 else ("yellow" if r.win_rate > 0.50 else "red")
        sh_s = "bold green" if r.sharpe > 0.5 else ("yellow" if r.sharpe > 0 else "red")
        fr_s = "green" if r.fill_rate > 0.60 else "yellow"

        table.add_row(
            r.bucket,
            action.upper(),
            str(r.n_trades),
            f"[{fr_s}]{r.fill_rate*100:.0f}%[/{fr_s}]",
            f"[{wr_s}]{r.win_rate*100:.1f}%[/{wr_s}]",
            f"{r.avg_return*100:.3f}%",
            f"{r.total_return*100:.1f}%",
            f"[{sh_s}]{r.sharpe:.2f}[/{sh_s}]",
        )

    console.print(table)


def print_comparison_table(
    model_results: list,
    gap_results: list,
    bh_perf: dict,
) -> None:
    """Rich table: all strategies vs buy-and-hold."""
    table = Table(
        title="Strategy Comparison — All vs Buy & Hold",
        show_lines=True, header_style="bold green",
    )
    table.add_column("Strategy", min_width=24)
    table.add_column("Sharpe", justify="center", width=10)
    table.add_column("CAGR", justify="center", width=10)
    table.add_column("Max DD", justify="center", width=10)
    table.add_column("Total Ret", justify="center", width=11)

    # Buy and hold row
    table.add_row(
        "[dim]Buy & Hold Nifty[/dim]",
        f"{bh_perf['sharpe']:.2f}",
        f"{bh_perf['cagr']*100:.1f}%",
        f"{bh_perf['max_drawdown']*100:.1f}%",
        f"{bh_perf['total_return']*100:.1f}%",
    )

    # Model rows
    for r in model_results:
        sh_s = "bold green" if r.sharpe > bh_perf["sharpe"] else "yellow"
        table.add_row(
            f"Signal: {r.name}",
            f"[{sh_s}]{r.sharpe:.2f}[/{sh_s}]",
            f"{r.cagr*100:.1f}%",
            f"{r.max_drawdown*100:.1f}%",
            f"{r.total_return*100:.1f}%",
        )

    # Gap-fade rows (only ones with trades)
    for r in gap_results:
        if r.n_trades == 0:
            continue
        sh_s = "bold green" if r.sharpe > bh_perf["sharpe"] else "yellow"
        table.add_row(
            f"Gap: {r.bucket}",
            f"[{sh_s}]{r.sharpe:.2f}[/{sh_s}]",
            "-",
            "-",
            f"{r.total_return*100:.1f}%",
        )

    console.print(table)


# ── Main ─────────────────────────────────────────────────────────────

def main() -> None:
    t0 = time.time()

    # ── Load cached data ─────────────────────────────────────────
    console.rule("[bold blue]PHASE 1: Load Cached Daily Data")

    from quant.ohlc_data import load_cached_daily
    daily_data = load_cached_daily()

    if not daily_data:
        console.print("[red]No cached daily data found. Run ohlc_data.py first.[/red]")
        sys.exit(1)

    for name, df in daily_data.items():
        console.print(f"  {name}: {len(df)} bars, {df.index[0].date()} to {df.index[-1].date()}")

    # ── Multi-market model ───────────────────────────────────────
    console.rule("[bold blue]PHASE 2: Overnight Multi-Market Model")

    from quant.overnight_signal import run_overnight_models, build_overnight_features
    from quant.overnight_signal import compute_performance, backtest_signal

    model_results = run_overnight_models(daily_data)

    if model_results:
        print_model_accuracy_by_year(model_results)
        console.print()
        print_model_performance(model_results)

        # Save predictions from best model
        best = model_results[0]
        if best.predictions is not None:
            pred_path = OUTPUT_DIR / "overnight_predictions.csv"
            best.predictions.to_csv(pred_path, index=False)
            console.print(f"\n  Predictions saved to [cyan]{pred_path}[/cyan]")
    else:
        console.print("[yellow]No model results produced.[/yellow]")

    # Compute buy-and-hold performance for comparison
    bh_perf = {"sharpe": 0.0, "cagr": 0.0, "max_drawdown": 0.0, "total_return": 0.0}
    if model_results and model_results[0].predictions is not None:
        bt = backtest_signal(model_results[0].predictions, daily_data["nifty50"])
        bh_perf = compute_performance(bt["bh_returns"], bt["dates"])

    # ── Gap-fade backtest ────────────────────────────────────────
    console.rule("[bold blue]PHASE 3: Gap-Fade Strategy Backtest")

    from quant.overnight_signal import run_gap_fade_backtest
    gap_results, gap_df = run_gap_fade_backtest(daily_data)

    print_gap_fade_results(gap_results)

    # Save gap analysis
    gap_path = OUTPUT_DIR / "gap_analysis.csv"
    gap_df.to_csv(gap_path)
    console.print(f"\n  Gap analysis saved to [cyan]{gap_path}[/cyan]")

    # ── Comparison ───────────────────────────────────────────────
    console.rule("[bold blue]PHASE 4: Strategy Comparison")

    print_comparison_table(model_results, gap_results, bh_perf)

    # ── Summary ──────────────────────────────────────────────────
    elapsed = time.time() - t0
    console.rule("[bold green]COMPLETE")
    console.print(f"\n  Time: {elapsed:.0f}s")
    console.print(f"  Output: {OUTPUT_DIR}/overnight_predictions.csv")
    console.print(f"  Output: {OUTPUT_DIR}/gap_analysis.csv")

    # Verdict
    console.print("\n[bold cyan]VERDICT[/bold cyan]")
    if model_results:
        best = model_results[0]
        console.print(f"  Best model: {best.name}")
        console.print(f"  Accuracy: {best.accuracy*100:.1f}% | Sharpe: {best.sharpe:.2f} | CAGR: {best.cagr*100:.1f}%")
        if best.accuracy > 0.55:
            console.print("  [bold green]Signal has edge (>55% accuracy)[/bold green]")
        elif best.accuracy > 0.52:
            console.print("  [yellow]Marginal edge (52-55%). Needs more confirmation.[/yellow]")
        else:
            console.print("  [red]Weak signal (<52%). Overnight cues alone insufficient.[/red]")

    # Gap-fade verdict
    optimal = next((r for r in gap_results if r.bucket == "optimal_fade"), None)
    if optimal and optimal.n_trades > 0:
        console.print(f"\n  Optimal gap-fade (0.3-0.8%): {optimal.win_rate*100:.0f}% win, "
                       f"{optimal.fill_rate*100:.0f}% fill rate")
        if optimal.win_rate > 0.55 and optimal.fill_rate > 0.60:
            console.print("  [bold green]Gap-fade zone confirmed.[/bold green]")
        else:
            console.print("  [yellow]Gap-fade zone marginal in this data.[/yellow]")

    console.print("\n  [dim]Walk-forward validation. No lookahead. Past ≠ future.[/dim]")


if __name__ == "__main__":
    main()
