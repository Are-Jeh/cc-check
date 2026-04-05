#!/usr/bin/env python3
"""
Time Pattern Scanner — Orchestrator
=====================================
Brute-force scan every possible time combination across all tickers.

Usage:
    python quant/run_patterns.py
    python quant/run_patterns.py --force   # re-download all OHLC data
"""

import sys
import os
import warnings
import logging
import time
import argparse

# Ensure parent dir is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

warnings.filterwarnings("ignore")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("patterns")

from rich.console import Console
console = Console()


def main():
    parser = argparse.ArgumentParser(description="Time Pattern Scanner")
    parser.add_argument("--force", action="store_true", help="Force re-download OHLC data")
    parser.add_argument("--no-hourly", action="store_true", help="Skip hourly scan (faster)")
    parser.add_argument("--no-celestial", action="store_true", help="Skip conditional celestial scans")
    args = parser.parse_args()

    t0 = time.time()

    # ── Phase 1: Fetch OHLC Data ──────────────────────────────────
    console.rule("[bold blue]PHASE 1: Fetch OHLC Data")

    from quant.ohlc_data import fetch_daily_ohlc, fetch_hourly_ohlc

    console.print("  Fetching daily OHLC (10 years)...")
    daily_data = fetch_daily_ohlc(force=args.force)
    console.print(f"    {len(daily_data)} tickers loaded")
    for name, df in daily_data.items():
        console.print(f"      {name}: {len(df)} bars ({df.index.min().date()} → {df.index.max().date()})")

    hourly_data = {}
    if not args.no_hourly:
        console.print("  Fetching hourly OHLC (~2 years)...")
        hourly_data = fetch_hourly_ohlc(force=args.force)
        console.print(f"    {len(hourly_data)} tickers loaded")
        for name, df in hourly_data.items():
            console.print(f"      {name}: {len(df)} bars")
    else:
        console.print("  [yellow]Skipping hourly data (--no-hourly)[/yellow]")

    # ── Phase 2: Load Celestial Data (for conditional scans) ──────
    celestial_df = None
    nature_df = None

    if not args.no_celestial:
        console.rule("[bold blue]PHASE 2: Load Celestial + Nature Data")
        try:
            from quant.celestial_engine import compute_all_celestial, compute_hybrid_indicators
            console.print("  Computing celestial mechanics...")
            celestial_raw = compute_all_celestial(start_date="2015-01-01", end_date="2025-12-31")
            celestial_df = compute_hybrid_indicators(celestial_raw)
            console.print(f"    Celestial: {celestial_df.shape[1]} features, {len(celestial_df)} days")
        except Exception as e:
            console.print(f"  [red]Celestial failed: {e}[/red]")

        try:
            from quant.nature_metrics import collect_all_nature_metrics
            console.print("  Collecting nature metrics...")
            nature_df = collect_all_nature_metrics(start_date="2015-01-01", end_date="2025-12-31")
            console.print(f"    Nature: {nature_df.shape[1]} features, {len(nature_df)} days")
        except Exception as e:
            console.print(f"  [red]Nature metrics failed: {e}[/red]")
    else:
        console.print("[yellow]Skipping celestial data (--no-celestial)[/yellow]")

    # ── Phase 3: Run All Scans ────────────────────────────────────
    console.rule("[bold blue]PHASE 3: Pattern Scanning")

    from quant.pattern_scanner import run_all_scans

    console.print("  Running all scans...")
    all_results, significant = run_all_scans(
        daily_data=daily_data,
        hourly_data=hourly_data,
        celestial_df=celestial_df,
        nature_df=nature_df,
    )

    console.print(f"  [bold]{len(all_results)} hypotheses tested[/bold]")
    console.print(f"  [bold green]{len(significant)} patterns survived FDR + OOS validation[/bold green]")

    # ── Phase 4: Report ───────────────────────────────────────────
    console.rule("[bold blue]PHASE 4: Report Generation")

    from quant.pattern_report import generate_full_report

    tickers = list(daily_data.keys())
    generate_full_report(all_results, significant, tickers)

    # ── Summary ───────────────────────────────────────────────────
    elapsed = time.time() - t0
    console.rule("[bold green]COMPLETE")
    console.print(f"\n  Time: {elapsed:.0f}s")
    console.print(f"  Hypotheses tested: {len(all_results)}")
    console.print(f"  Significant patterns: {len(significant)}")
    console.print(f"  Charts: charts/patterns/")
    console.print(f"  CSV: output/pattern_scan_results.csv")

    if significant:
        console.print("\n[bold cyan]TOP 3 PATTERNS:[/bold cyan]")
        ranked = sorted(significant, key=lambda r: r.test_sharpe, reverse=True)[:3]
        for i, r in enumerate(ranked):
            console.print(
                f"  {i+1}. {r.ticker} | {r.description} | "
                f"OOS Sharpe={r.test_sharpe:.2f} | WR={r.test_win_rate:.1%} | "
                f"μ={r.test_mean_ret*10000:+.1f}bps"
            )
    else:
        console.print("\n[yellow]No patterns survived statistical testing.[/yellow]")
        console.print("[dim]This is informative — it means time-of-week/month patterns")
        console.print("are not reliably exploitable in these tickers.[/dim]")


if __name__ == "__main__":
    main()
