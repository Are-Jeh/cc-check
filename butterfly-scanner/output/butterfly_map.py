"""Output modules — the butterfly map and regime report."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from rich.console import Console
from rich.table import Table

from config import SIGNIFICANCE_LEVEL, BASE_DIR

console = Console()

# Categories inferred from indicator name prefixes
_CATEGORY_PREFIXES = {
    "market": "market",
    "ret_": "market",
    "celestial": "celestial",
    "lunar": "celestial",
    "solar": "celestial",
    "planet": "celestial",
    "mercury": "celestial",
    "weather": "weather",
    "temp": "weather",
    "humid": "weather",
    "rain": "weather",
    "aqi": "weather",
    "wind": "weather",
    "digital": "digital",
    "gtrends": "digital",
    "wiki": "digital",
    "reddit": "digital",
    "twitter": "digital",
    "economic": "economic",
    "gdp": "economic",
    "cpi": "economic",
    "iip": "economic",
    "wpi": "economic",
    "unemployment": "economic",
    "agricultural": "agricultural",
    "crop": "agricultural",
    "msp": "agricultural",
    "monsoon": "agricultural",
    "reservoir": "agricultural",
}

_UNEXPECTED_CATEGORIES = {"celestial", "weather", "agricultural"}


def _categorize(indicator_name: str) -> str:
    """Infer a category from the indicator name."""
    lower = indicator_name.lower()
    for prefix, category in _CATEGORY_PREFIXES.items():
        if lower.startswith(prefix):
            return category
    return "other"


def _fmt_r(val: float | None) -> str:
    if val is None or pd.isna(val):
        return "-"
    return f"{val:+.3f}"


def _fmt_p(val: float | None) -> str:
    if val is None or pd.isna(val):
        return "-"
    return f"{val:.2e}"


def _p_style(val: float | None) -> str:
    """Return a rich style string depending on p-value significance."""
    if val is None or pd.isna(val):
        return "dim"
    if val < SIGNIFICANCE_LEVEL:
        return "bold green"
    if val < SIGNIFICANCE_LEVEL * 2:
        return "yellow"
    return "white"


def generate_butterfly_map(analysis_df: pd.DataFrame) -> None:
    """Print and save the butterfly correlation map.

    *analysis_df* is the full results DataFrame as returned by
    ``db.load_all_analysis()``.
    """
    if analysis_df.empty:
        console.print("[yellow]No analysis results to map.[/yellow]")
        return

    # Work only with the "all" regime
    df = analysis_df[analysis_df["regime"] == "all"].copy()

    if df.empty:
        console.print("[yellow]No 'all'-regime results found.[/yellow]")
        return

    # For each (indicator, market) pair find the lag with the strongest signal
    # (lowest minimum p-value across the three correlation types).
    df["min_p"] = df[["pearson_p", "spearman_p", "kendall_p"]].min(axis=1)

    # Drop groups that are entirely NaN (no valid correlations computed)
    valid = df.dropna(subset=["min_p"])
    if valid.empty:
        console.print("[yellow]All p-values are NaN — no valid correlations.[/yellow]")
        return

    best_idx = valid.groupby(["indicator", "market"])["min_p"].idxmin()
    best = df.loc[best_idx].copy()

    # Add derived columns
    best["category"] = best["indicator"].apply(_categorize)
    best["is_significant"] = best["min_p"] < SIGNIFICANCE_LEVEL
    best["unexpected"] = best.apply(
        lambda row: row["is_significant"] and row["category"] in _UNEXPECTED_CATEGORIES,
        axis=1,
    )
    best["abs_pearson"] = best["pearson_r"].abs()

    # Sort: significant first, then by absolute correlation strength
    best = best.sort_values(
        ["is_significant", "abs_pearson"], ascending=[False, False]
    ).reset_index(drop=True)

    # Build rich table
    table = Table(
        title="Butterfly Effect Correlation Map",
        show_lines=True,
        header_style="bold cyan",
    )
    table.add_column("Rank", justify="right", style="dim", width=5)
    table.add_column("Indicator", min_width=20)
    table.add_column("Market", min_width=12)
    table.add_column("Best Lag (days)", justify="center", width=15)
    table.add_column("Pearson r", justify="center", width=10)
    table.add_column("Spearman r", justify="center", width=10)
    table.add_column("Granger p", justify="center", width=10)
    table.add_column("MI Score", justify="center", width=10)
    table.add_column("Category", justify="center", width=14)
    table.add_column("Unexpected?", justify="center", width=12)

    for rank, (_, row) in enumerate(best.iterrows(), start=1):
        p_style = _p_style(row.get("min_p"))
        unexpected_flag = "[bold red]YES[/bold red]" if row["unexpected"] else "no"

        table.add_row(
            str(rank),
            f"[{p_style}]{row['indicator']}[/{p_style}]",
            row["market"],
            str(int(row["lag_days"])),
            _fmt_r(row.get("pearson_r")),
            _fmt_r(row.get("spearman_r")),
            _fmt_p(row.get("granger_p")),
            f"{row['mutual_info']:.4f}" if pd.notna(row.get("mutual_info")) else "-",
            row["category"],
            unexpected_flag,
        )

    console.print(table)

    # Save CSV
    csv_path = BASE_DIR / "output" / "butterfly_map.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    best.to_csv(csv_path, index=False)
    console.print(f"\n  Saved CSV to [cyan]{csv_path}[/cyan]")


def generate_regime_report(regime_results: dict) -> None:
    """Print a rich table showing regime-conditional correlations.

    *regime_results* is a dict mapping ``"indicator -> market"`` to
    ``{regime: {"r": float, "p": float, "n": int}}``.
    """
    if not regime_results:
        console.print("[yellow]No regime results to report.[/yellow]")
        return

    table = Table(
        title="Regime-Conditional Correlations",
        show_lines=True,
        header_style="bold magenta",
    )
    table.add_column("Pair", min_width=30)
    table.add_column("Bull r (p)", justify="center", width=16)
    table.add_column("Bear r (p)", justify="center", width=16)
    table.add_column("Sideways r (p)", justify="center", width=16)
    table.add_column("Regime-Specific?", justify="center", width=16)

    for pair_name, regimes in regime_results.items():
        cells: dict[str, str] = {}
        sig_flags: dict[str, bool] = {}

        for regime_label in ("bull", "bear", "sideways"):
            stats = regimes.get(regime_label, {})
            r_val = stats.get("r")
            p_val = stats.get("p")
            n_val = stats.get("n", 0)
            style = _p_style(p_val)
            is_sig = p_val is not None and not pd.isna(p_val) and p_val < SIGNIFICANCE_LEVEL
            sig_flags[regime_label] = is_sig

            if r_val is not None and not pd.isna(r_val):
                cells[regime_label] = (
                    f"[{style}]{r_val:+.3f} ({_fmt_p(p_val)})[/{style}]  n={n_val}"
                )
            else:
                cells[regime_label] = f"[dim]n/a  n={n_val}[/dim]"

        # Regime-specific: significant in some regimes but not all
        sig_count = sum(sig_flags.values())
        regime_specific = 0 < sig_count < 3
        rs_text = "[bold yellow]YES[/bold yellow]" if regime_specific else "no"

        table.add_row(
            pair_name,
            cells.get("bull", "-"),
            cells.get("bear", "-"),
            cells.get("sideways", "-"),
            rs_text,
        )

    console.print(table)
