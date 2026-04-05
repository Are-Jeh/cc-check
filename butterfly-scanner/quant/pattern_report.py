"""
Pattern Report — Tables, heatmaps, equity curves, CSV export.
"""

import logging
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from rich.console import Console
from rich.table import Table

from quant.pattern_scanner import PatternResult, DOW_NAMES, PRICES, INDIA_HOURS

logger = logging.getLogger(__name__)
console = Console()

OUT = Path(__file__).parent.parent / "charts" / "patterns"
OUT.mkdir(parents=True, exist_ok=True)
CSV_DIR = Path(__file__).parent.parent / "output"
CSV_DIR.mkdir(parents=True, exist_ok=True)


# ═══════════════════════════════════════════════════════════════════════
# RICH TABLES
# ═══════════════════════════════════════════════════════════════════════

def print_significant_patterns(results: list[PatternResult], top_n: int = 30):
    """Rich table of top patterns ranked by OOS Sharpe."""
    if not results:
        console.print("[yellow]No significant patterns found after FDR correction.[/yellow]")
        console.print("[dim]This is a legitimate finding — it means no reproducible")
        console.print("time-based patterns survive proper statistical testing.[/dim]")
        return

    # Sort by test Sharpe descending
    ranked = sorted(results, key=lambda r: r.test_sharpe, reverse=True)[:top_n]

    table = Table(
        title=f"Top {min(top_n, len(ranked))} Significant Patterns (ranked by OOS Sharpe)",
        show_lines=True,
        header_style="bold cyan",
    )
    table.add_column("#", justify="right", width=3)
    table.add_column("Ticker", width=10)
    table.add_column("Pattern", min_width=30)
    table.add_column("Type", width=14)
    table.add_column("Train μ (bps)", justify="center", width=12)
    table.add_column("Test μ (bps)", justify="center", width=11)
    table.add_column("Train WR", justify="center", width=9)
    table.add_column("Test WR", justify="center", width=9)
    table.add_column("WR CI", justify="center", width=12)
    table.add_column("OOS Sharpe", justify="center", width=10)
    table.add_column("N (train/test)", justify="center", width=13)
    table.add_column("FDR p", justify="center", width=8)

    for i, r in enumerate(ranked):
        tr_bps = r.train_mean_ret * 10000
        te_bps = r.test_mean_ret * 10000
        sharpe_style = "bold green" if r.test_sharpe > 1.0 else ("green" if r.test_sharpe > 0.5 else "yellow")
        wr_style = "green" if r.test_win_rate > 0.55 else ("yellow" if r.test_win_rate > 0.50 else "red")

        table.add_row(
            str(i + 1),
            r.ticker,
            r.description,
            r.pattern_type,
            f"{tr_bps:+.1f}",
            f"{te_bps:+.1f}",
            f"{r.train_win_rate:.1%}",
            f"[{wr_style}]{r.test_win_rate:.1%}[/{wr_style}]",
            f"[{r.test_win_ci_lo:.1%},{r.test_win_ci_hi:.1%}]",
            f"[{sharpe_style}]{r.test_sharpe:.2f}[/{sharpe_style}]",
            f"{r.train_n}/{r.test_n}",
            f"{r.fdr_p_value:.4f}",
        )

    console.print(table)


def print_scan_summary(
    all_results: list[PatternResult],
    significant: list[PatternResult],
):
    """Print summary statistics of the scan."""
    table = Table(title="Scan Summary", show_lines=True, header_style="bold magenta")
    table.add_column("Metric", min_width=30)
    table.add_column("Value", justify="right", width=15)

    n_total = len(all_results)
    n_sig = len(significant)

    # Count by type
    type_counts = {}
    for r in all_results:
        type_counts[r.pattern_type] = type_counts.get(r.pattern_type, 0) + 1
    sig_type_counts = {}
    for r in significant:
        sig_type_counts[r.pattern_type] = sig_type_counts.get(r.pattern_type, 0) + 1

    # Count tickers
    tickers_tested = len(set(r.ticker for r in all_results))
    tickers_with_signal = len(set(r.ticker for r in significant))

    table.add_row("Total hypotheses tested", str(n_total))
    table.add_row("Significant after FDR + OOS", str(n_sig))
    table.add_row("Discovery rate", f"{n_sig/n_total:.2%}" if n_total > 0 else "N/A")
    table.add_row("Tickers tested", str(tickers_tested))
    table.add_row("Tickers with signal", str(tickers_with_signal))
    table.add_row("", "")

    for pt, cnt in sorted(type_counts.items()):
        sig_cnt = sig_type_counts.get(pt, 0)
        table.add_row(f"  {pt}", f"{sig_cnt}/{cnt}")

    console.print(table)


# ═══════════════════════════════════════════════════════════════════════
# HEATMAPS
# ═══════════════════════════════════════════════════════════════════════

def plot_dow_heatmap(
    all_results: list[PatternResult],
    ticker: str,
):
    """
    5x5 day-of-week heatmap for a single ticker.
    Cell = mean return of Close-to-Close pattern for that (entry_day, exit_day).
    """
    # Filter to DOW OHLC, Close-to-Close only
    grid = np.full((5, 5), np.nan)
    for r in all_results:
        if r.ticker != ticker or r.pattern_type != "dow_ohlc":
            continue
        if not r.entry_label.endswith("_Close") or not r.exit_label.endswith("_Close"):
            continue

        entry_day = DOW_NAMES.index(r.entry_label.split("_")[0])
        exit_day = DOW_NAMES.index(r.exit_label.split("_")[0])
        # Use full-sample mean (train weighted more, but use train as proxy)
        grid[entry_day, exit_day] = r.train_mean_ret * 10000  # bps

    fig, ax = plt.subplots(figsize=(8, 6))
    vmax = max(abs(np.nanmin(grid)), abs(np.nanmax(grid)), 1)
    im = ax.imshow(grid, cmap="RdYlGn", vmin=-vmax, vmax=vmax, aspect="auto")

    ax.set_xticks(range(5))
    ax.set_xticklabels(DOW_NAMES)
    ax.set_yticks(range(5))
    ax.set_yticklabels(DOW_NAMES)
    ax.set_xlabel("Exit Day (Close)")
    ax.set_ylabel("Entry Day (Close)")
    ax.set_title(f"{ticker} — DOW Close-to-Close Returns (bps)", fontweight="bold")

    # Annotate cells
    for i in range(5):
        for j in range(5):
            val = grid[i, j]
            if not np.isnan(val):
                color = "white" if abs(val) > vmax * 0.6 else "black"
                ax.text(j, i, f"{val:+.1f}", ha="center", va="center",
                        fontsize=10, fontweight="bold", color=color)

    plt.colorbar(im, ax=ax, label="Mean Return (bps)")
    plt.tight_layout()
    fig.savefig(OUT / f"heatmap_dow_{ticker}.png", dpi=150)
    plt.close()
    logger.info("Saved heatmap_dow_%s.png", ticker)


def plot_hourly_heatmap(
    all_results: list[PatternResult],
    ticker: str,
):
    """
    Hourly heatmap: (entry_day_hour) vs (exit_day_hour).
    Rows/cols are DOW_HOUR combos (35 total for India hours).
    """
    hourly = [r for r in all_results
              if r.ticker == ticker and r.pattern_type == "hourly_dow"]
    if not hourly:
        return

    # Build label list
    labels = [f"{d}_{h:02d}" for d in DOW_NAMES for h in INDIA_HOURS]
    n = len(labels)
    label_idx = {lbl: i for i, lbl in enumerate(labels)}

    grid = np.full((n, n), np.nan)
    for r in hourly:
        if r.entry_label in label_idx and r.exit_label in label_idx:
            i = label_idx[r.entry_label]
            j = label_idx[r.exit_label]
            grid[i, j] = r.train_mean_ret * 10000

    fig, ax = plt.subplots(figsize=(16, 14))
    vmax = max(abs(np.nanmin(grid)), abs(np.nanmax(grid)), 1)
    im = ax.imshow(grid, cmap="RdYlGn", vmin=-vmax, vmax=vmax, aspect="auto")

    # Show every 7th label (one per day)
    tick_positions = list(range(0, n, 7))
    tick_labels = [labels[i].split("_")[0] for i in tick_positions]
    ax.set_xticks(tick_positions)
    ax.set_xticklabels(tick_labels)
    ax.set_yticks(tick_positions)
    ax.set_yticklabels(tick_labels)
    ax.set_xlabel("Exit (Day)")
    ax.set_ylabel("Entry (Day)")
    ax.set_title(f"{ticker} — Hourly DOW Returns Heatmap (bps)", fontweight="bold")

    plt.colorbar(im, ax=ax, label="Mean Return (bps)")
    plt.tight_layout()
    fig.savefig(OUT / f"heatmap_hourly_{ticker}.png", dpi=150)
    plt.close()
    logger.info("Saved heatmap_hourly_%s.png", ticker)


def plot_equity_curve(significant: list[PatternResult], top_n: int = 5):
    """
    Plot simulated equity curve for top N patterns.
    (Illustrative only — uses train+test returns chronologically.)
    """
    if not significant:
        return

    ranked = sorted(significant, key=lambda r: r.test_sharpe, reverse=True)[:top_n]

    fig, ax = plt.subplots(figsize=(12, 6))
    colors = ["#E74C3C", "#3498DB", "#2ECC71", "#F39C12", "#9B59B6"]

    for i, r in enumerate(ranked):
        # Simulate: repeated mean return per trade, N trades
        n_total = r.train_n + r.test_n
        # Generate synthetic equity from mean + std
        np.random.seed(hash(r.description) % 2**31)
        sim_returns = np.random.normal(
            r.test_mean_ret, r.test_std_ret, size=n_total
        )
        equity = np.cumprod(1 + sim_returns)

        label = f"{r.ticker}: {r.description[:35]}... (S={r.test_sharpe:.1f})"
        ax.plot(equity, color=colors[i % len(colors)], linewidth=1.2, label=label)

    ax.set_title("Top Pattern Equity Curves (Simulated from OOS Stats)", fontweight="bold")
    ax.set_xlabel("Trade #")
    ax.set_ylabel("Equity (starting = 1)")
    ax.legend(fontsize=7, loc="upper left")
    ax.grid(True, alpha=0.3)
    ax.axhline(1.0, color="black", linewidth=0.5, linestyle="--")
    plt.tight_layout()
    fig.savefig(OUT / "equity_curves_patterns.png", dpi=150)
    plt.close()
    logger.info("Saved equity_curves_patterns.png")


# ═══════════════════════════════════════════════════════════════════════
# CSV EXPORT
# ═══════════════════════════════════════════════════════════════════════

def export_csv(
    all_results: list[PatternResult],
    significant: list[PatternResult],
):
    """Export all results and significant results to CSV."""
    def _to_rows(results):
        rows = []
        for r in results:
            rows.append({
                "ticker": r.ticker,
                "pattern_type": r.pattern_type,
                "description": r.description,
                "entry": r.entry_label,
                "exit": r.exit_label,
                "condition": r.condition,
                "significant": r.significant,
                "train_n": r.train_n,
                "train_mean_ret_bps": r.train_mean_ret * 10000,
                "train_std_ret_bps": r.train_std_ret * 10000,
                "train_win_rate": r.train_win_rate,
                "train_sharpe": r.train_sharpe,
                "train_p_value": r.train_p_value,
                "fdr_p_value": r.fdr_p_value,
                "test_n": r.test_n,
                "test_mean_ret_bps": r.test_mean_ret * 10000,
                "test_std_ret_bps": r.test_std_ret * 10000,
                "test_win_rate": r.test_win_rate,
                "test_win_ci_lo": r.test_win_ci_lo,
                "test_win_ci_hi": r.test_win_ci_hi,
                "test_sharpe": r.test_sharpe,
                "test_p_value": r.test_p_value,
            })
        return rows

    # All results
    all_df = pd.DataFrame(_to_rows(all_results))
    all_path = CSV_DIR / "pattern_scan_results.csv"
    all_df.to_csv(all_path, index=False)
    console.print(f"  Saved all results: {all_path} ({len(all_df)} rows)")

    # Significant only
    if significant:
        sig_df = pd.DataFrame(_to_rows(significant))
        sig_path = CSV_DIR / "pattern_scan_significant.csv"
        sig_df.to_csv(sig_path, index=False)
        console.print(f"  Saved significant: {sig_path} ({len(sig_df)} rows)")


# ═══════════════════════════════════════════════════════════════════════
# MAIN REPORT
# ═══════════════════════════════════════════════════════════════════════

def generate_full_report(
    all_results: list[PatternResult],
    significant: list[PatternResult],
    tickers: list[str],
):
    """Generate all reports: tables, heatmaps, equity curves, CSV."""
    console.rule("[bold blue]PATTERN SCAN RESULTS")

    # Summary table
    print_scan_summary(all_results, significant)

    # Top patterns table
    print_significant_patterns(significant)

    # Heatmaps for each ticker
    console.rule("[bold blue]HEATMAPS")
    for ticker in tickers:
        ticker_results = [r for r in all_results if r.ticker == ticker]
        if ticker_results:
            plot_dow_heatmap(all_results, ticker)
            plot_hourly_heatmap(all_results, ticker)

    # Equity curves
    console.rule("[bold blue]EQUITY CURVES")
    plot_equity_curve(significant)

    # CSV export
    console.rule("[bold blue]CSV EXPORT")
    export_csv(all_results, significant)
