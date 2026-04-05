#!/usr/bin/env python3
"""
Expanded Pattern Scanner — Runner
===================================
Multi-day holds + VIX/trend regime splits across all cached tickers.

Usage:
    python quant/run_expanded.py
"""

import sys
import os
import warnings
import logging
import time
from dataclasses import fields
from pathlib import Path

# Ensure parent dir is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

warnings.filterwarnings("ignore")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("expanded")

import pandas as pd
from rich.console import Console
from rich.table import Table

console = Console()

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _results_to_dataframe(results: list) -> pd.DataFrame:
    """Convert list of PatternResult dataclasses to DataFrame."""
    if not results:
        return pd.DataFrame()
    from quant.pattern_scanner import PatternResult
    field_names = [f.name for f in fields(PatternResult)]
    rows = [{f: getattr(r, f) for f in field_names} for r in results]
    return pd.DataFrame(rows)


def main():
    t0 = time.time()

    # ── Phase 1: Load cached data ──────────────────────────────────
    console.rule("[bold blue]PHASE 1: Load Cached Daily Data")

    from quant.ohlc_data import load_cached_daily

    daily_data = load_cached_daily()
    if not daily_data:
        console.print("[red]No cached daily data found. Run quant/ohlc_data.py first.[/red]")
        sys.exit(1)

    console.print(f"  {len(daily_data)} tickers loaded:")
    for name, df in daily_data.items():
        console.print(
            f"    {name}: {len(df)} bars "
            f"({df.index.min().date()} -> {df.index.max().date()})"
        )

    # ── Phase 2: Run expanded scans ────────────────────────────────
    console.rule("[bold blue]PHASE 2: Expanded Pattern Scanning")

    from quant.expanded_scanner import run_expanded_scans

    console.print("  Running multi-day hold + regime scans...")
    all_results, significant = run_expanded_scans(daily_data)

    console.print(f"  [bold]{len(all_results)} hypotheses tested[/bold]")
    console.print(
        f"  [bold green]{len(significant)} patterns survived "
        f"FDR + OOS validation[/bold green]"
    )

    # ── Phase 3: Save results ──────────────────────────────────────
    console.rule("[bold blue]PHASE 3: Save Results")

    all_df = _results_to_dataframe(all_results)
    sig_df = _results_to_dataframe(significant)

    all_path = OUTPUT_DIR / "expanded_scan_results.csv"
    sig_path = OUTPUT_DIR / "expanded_scan_significant.csv"

    if not all_df.empty:
        all_df.to_csv(all_path, index=False)
        console.print(f"  All results: {all_path} ({len(all_df)} rows)")
    else:
        console.print("  [yellow]No results to save.[/yellow]")

    if not sig_df.empty:
        sig_df.to_csv(sig_path, index=False)
        console.print(f"  Significant: {sig_path} ({len(sig_df)} rows)")
    else:
        console.print(f"  [yellow]No significant patterns found.[/yellow]")

    # ── Phase 4: Summary ───────────────────────────────────────────
    console.rule("[bold blue]PHASE 4: Summary")

    elapsed = time.time() - t0

    # Breakdown by scan type
    if not all_df.empty:
        type_counts = all_df["pattern_type"].value_counts()
        type_table = Table(title="Hypotheses by Scan Type")
        type_table.add_column("Scan Type", style="cyan")
        type_table.add_column("Count", justify="right")
        for ptype, count in type_counts.items():
            type_table.add_row(ptype, str(count))
        type_table.add_row("[bold]TOTAL[/bold]", f"[bold]{len(all_df)}[/bold]")
        console.print(type_table)

    if not sig_df.empty:
        # Breakdown of significant by type and ticker
        sig_table = Table(title="Significant Patterns")
        sig_table.add_column("Ticker", style="cyan")
        sig_table.add_column("Type", style="green")
        sig_table.add_column("Description")
        sig_table.add_column("Condition", style="yellow")
        sig_table.add_column("Train mu (bps)", justify="right")
        sig_table.add_column("OOS mu (bps)", justify="right")
        sig_table.add_column("OOS Sharpe", justify="right")
        sig_table.add_column("OOS WR", justify="right")
        sig_table.add_column("FDR p", justify="right")

        ranked = sig_df.sort_values("test_sharpe", ascending=False)
        for _, row in ranked.iterrows():
            sig_table.add_row(
                row["ticker"],
                row["pattern_type"],
                row["description"],
                row.get("condition", ""),
                f"{row['train_mean_ret'] * 10000:+.1f}",
                f"{row['test_mean_ret'] * 10000:+.1f}",
                f"{row['test_sharpe']:.2f}",
                f"{row['test_win_rate']:.1%}",
                f"{row['fdr_p_value']:.4f}",
            )
        console.print(sig_table)

        # Top 5 by OOS Sharpe
        console.print("\n[bold cyan]TOP 5 BY OOS SHARPE:[/bold cyan]")
        top5 = ranked.head(5)
        for i, (_, row) in enumerate(top5.iterrows()):
            console.print(
                f"  {i+1}. {row['ticker']} | {row['description']} | "
                f"Sharpe={row['test_sharpe']:.2f} | "
                f"WR={row['test_win_rate']:.1%} | "
                f"mu={row['test_mean_ret'] * 10000:+.1f}bps"
            )
    else:
        console.print(
            "\n[yellow]No patterns survived statistical testing.[/yellow]"
        )
        console.print(
            "[dim]This is expected under strict FDR correction -- "
            "it means these patterns are not reliably exploitable.[/dim]"
        )

    console.rule("[bold green]COMPLETE")
    console.print(f"  Time: {elapsed:.1f}s")
    console.print(f"  Hypotheses: {len(all_results)}")
    console.print(f"  Survivors: {len(significant)}")


if __name__ == "__main__":
    main()
