"""Report generator — charts and tables for the quant pipeline results."""

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from pathlib import Path
from rich.console import Console
from rich.table import Table

console = Console()
OUT = Path(__file__).parent.parent / "charts" / "quant"
OUT.mkdir(parents=True, exist_ok=True)


def plot_feature_importance(model_results, top_n=20):
    """Bar chart of top features from the best model."""
    best = model_results[0]  # sorted by Sharpe
    if not best.top_features:
        return

    names = [f[0] for f in best.top_features[:top_n]]
    values = [f[1] for f in best.top_features[:top_n]]

    # Color by category
    colors = []
    for n in names:
        if n.startswith("cel_"):
            colors.append("#9B59B6")  # purple = celestial
        elif n.startswith("nat_"):
            colors.append("#2ECC71")  # green = nature
        elif n.startswith("ix_"):
            colors.append("#E74C3C")  # red = interaction
        elif any(n.startswith(p) for p in ["day_", "month", "week_", "is_", "dow_", "dom_", "quarter"]):
            colors.append("#F39C12")  # orange = calendar
        else:
            colors.append("#3498DB")  # blue = market

    fig, ax = plt.subplots(figsize=(14, 8))
    bars = ax.barh(range(len(names)), values, color=colors, edgecolor="black", linewidth=0.3)
    ax.set_yticks(range(len(names)))
    ax.set_yticklabels(names, fontsize=9)
    ax.invert_yaxis()
    ax.set_xlabel("Importance")
    ax.set_title(f"Top {top_n} Features — {best.name} (Sharpe={best.sharpe_ratio:.2f})",
                 fontsize=14, fontweight="bold")

    # Legend
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor="#9B59B6", label="Celestial"),
        Patch(facecolor="#2ECC71", label="Nature"),
        Patch(facecolor="#3498DB", label="Market"),
        Patch(facecolor="#F39C12", label="Calendar"),
        Patch(facecolor="#E74C3C", label="Interaction"),
    ]
    ax.legend(handles=legend_elements, loc="lower right")
    ax.grid(True, alpha=0.3, axis="x")
    plt.tight_layout()
    fig.savefig(OUT / "feature_importance.png", dpi=150)
    plt.close()
    console.print(f"  Saved feature_importance.png")


def plot_equity_curves(model_results, y_true):
    """Plot cumulative returns for each model's strategy."""
    fig, ax = plt.subplots(figsize=(16, 8))

    # Buy and hold
    common_idx = None
    for r in model_results:
        if r.predictions is not None:
            common_idx = r.predictions.index
            break
    if common_idx is None:
        return

    bh = y_true.loc[common_idx]
    bh_cum = (1 + bh).cumprod()
    ax.plot(bh_cum.index, bh_cum.values, "k--", linewidth=1.5, alpha=0.5, label="Buy & Hold")

    colors = ["#E74C3C", "#3498DB", "#2ECC71", "#F39C12", "#9B59B6"]
    for i, r in enumerate(model_results):
        if r.predictions is None:
            continue
        common = r.predictions.index.intersection(y_true.index)
        strat_ret = y_true.loc[common] * np.sign(r.predictions.loc[common])
        cum = (1 + strat_ret).cumprod()
        color = colors[i % len(colors)]
        ax.plot(cum.index, cum.values, linewidth=1.5, color=color,
                label=f"{r.name} (S={r.sharpe_ratio:.2f})")

    ax.set_title("Equity Curves — Model Strategies vs Buy & Hold", fontsize=16, fontweight="bold")
    ax.set_ylabel("Cumulative Return")
    ax.legend(loc="upper left")
    ax.grid(True, alpha=0.3)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=6))
    plt.xticks(rotation=45)
    plt.tight_layout()
    fig.savefig(OUT / "equity_curves.png", dpi=150)
    plt.close()
    console.print(f"  Saved equity_curves.png")


def plot_category_comparison(category_df):
    """Bar chart comparing feature categories."""
    fig, axes = plt.subplots(1, 3, figsize=(18, 6))
    fig.suptitle("Which Feature Category Predicts Best?", fontsize=16, fontweight="bold")

    cats = category_df["category"].values
    x = range(len(cats))

    # Sharpe
    colors = ["green" if v > 0 else "red" for v in category_df["sharpe"]]
    axes[0].bar(x, category_df["sharpe"], color=colors, edgecolor="black", linewidth=0.3)
    axes[0].set_xticks(x)
    axes[0].set_xticklabels(cats, rotation=45, ha="right", fontsize=8)
    axes[0].set_ylabel("Sharpe Ratio")
    axes[0].set_title("Sharpe Ratio by Category")
    axes[0].axhline(y=0, color="black", linewidth=0.5)
    axes[0].grid(True, alpha=0.3, axis="y")

    # Win Rate
    colors = ["green" if v > 0.5 else "red" for v in category_df["win_rate"]]
    axes[1].bar(x, category_df["win_rate"] * 100, color=colors, edgecolor="black", linewidth=0.3)
    axes[1].set_xticks(x)
    axes[1].set_xticklabels(cats, rotation=45, ha="right", fontsize=8)
    axes[1].set_ylabel("Win Rate (%)")
    axes[1].set_title("Direction Accuracy")
    axes[1].axhline(y=50, color="red", linewidth=0.8, linestyle="--")
    axes[1].grid(True, alpha=0.3, axis="y")

    # Total Return
    colors = ["green" if v > 0 else "red" for v in category_df["total_return"]]
    axes[2].bar(x, category_df["total_return"] * 100, color=colors, edgecolor="black", linewidth=0.3)
    axes[2].set_xticks(x)
    axes[2].set_xticklabels(cats, rotation=45, ha="right", fontsize=8)
    axes[2].set_ylabel("Total Return (%)")
    axes[2].set_title("Strategy Total Return")
    axes[2].axhline(y=0, color="black", linewidth=0.5)
    axes[2].grid(True, alpha=0.3, axis="y")

    plt.tight_layout()
    fig.savefig(OUT / "category_comparison.png", dpi=150)
    plt.close()
    console.print(f"  Saved category_comparison.png")


def plot_celestial_vs_returns(celestial_df, market_prices, target="nifty50"):
    """Scatter + overlay plots of key celestial indicators vs market."""
    if target not in market_prices.columns:
        return

    returns = market_prices[target].pct_change().dropna()

    key_indicators = [
        ("earth_moon_dist_km", "Earth-Moon Distance"),
        ("earth_sun_dist_km", "Earth-Sun Distance"),
        ("sun_moon_dist_km", "Sun-Moon Distance"),
        ("tidal_force_moon", "Moon Tidal Force"),
        ("tidal_force_combined", "Combined Tidal Force"),
        ("sun_moon_dot_product", "Sun-Moon Dot Product"),
        ("sun_moon_cross_mag", "Sun-Moon Cross Product Mag"),
        ("sun_moon_angle_deg", "Sun-Moon Angle"),
        ("moon_phase", "Moon Phase"),
    ]

    # Filter to indicators that exist
    available = [(col, label) for col, label in key_indicators if col in celestial_df.columns]
    if not available:
        return

    n = len(available)
    cols = 3
    rows = (n + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(18, 5 * rows))
    fig.suptitle(f"Celestial Indicators vs {target} Daily Returns — Scatter", fontsize=16, fontweight="bold")

    if rows == 1:
        axes = [axes]
    axes_flat = [ax for row in axes for ax in (row if hasattr(row, '__len__') else [row])]

    for idx, (col, label) in enumerate(available):
        ax = axes_flat[idx]
        combined = pd.concat({"x": celestial_df[col], "y": returns}, axis=1, join="inner").dropna()
        if len(combined) < 30:
            ax.set_title(f"{label}\n(insufficient data)")
            continue

        ax.scatter(combined["x"], combined["y"], alpha=0.1, s=5, c="teal")
        # Trend line
        z = np.polyfit(combined["x"], combined["y"], 1)
        p = np.poly1d(z)
        xr = np.linspace(combined["x"].min(), combined["x"].max(), 100)
        ax.plot(xr, p(xr), "r-", linewidth=2)
        r = combined["x"].corr(combined["y"])
        ax.set_title(f"{label}\nr = {r:.4f}", fontsize=10)
        ax.set_xlabel(label, fontsize=8)
        ax.set_ylabel("Return", fontsize=8)
        ax.grid(True, alpha=0.3)

    # Hide empty subplots
    for idx in range(len(available), len(axes_flat)):
        axes_flat[idx].set_visible(False)

    plt.tight_layout()
    fig.savefig(OUT / "celestial_vs_returns.png", dpi=150)
    plt.close()
    console.print(f"  Saved celestial_vs_returns.png")


def print_model_table(model_results):
    """Rich table of all model results."""
    table = Table(title="Model Comparison — Walk-Forward Results",
                  show_lines=True, header_style="bold cyan")
    table.add_column("Rank", justify="right", width=5)
    table.add_column("Model", min_width=18)
    table.add_column("R² (test)", justify="center", width=10)
    table.add_column("Sharpe", justify="center", width=10)
    table.add_column("Win Rate", justify="center", width=10)
    table.add_column("Profit Factor", justify="center", width=13)
    table.add_column("Top Feature", min_width=25)

    for i, r in enumerate(model_results):
        sharpe_style = "bold green" if r.sharpe_ratio > 0.5 else ("yellow" if r.sharpe_ratio > 0 else "red")
        wr_style = "green" if r.win_rate > 0.52 else ("yellow" if r.win_rate > 0.5 else "red")
        top_feat = r.top_features[0][0] if r.top_features else "-"

        table.add_row(
            str(i + 1),
            r.name,
            f"{r.r2_test:.4f}",
            f"[{sharpe_style}]{r.sharpe_ratio:.2f}[/{sharpe_style}]",
            f"[{wr_style}]{r.win_rate*100:.1f}%[/{wr_style}]",
            f"{r.profit_factor:.2f}",
            top_feat,
        )

    console.print(table)


def print_category_table(category_df):
    """Rich table of category comparison."""
    table = Table(title="Feature Category Showdown",
                  show_lines=True, header_style="bold magenta")
    table.add_column("Category", min_width=20)
    table.add_column("# Features", justify="center", width=10)
    table.add_column("Sharpe", justify="center", width=10)
    table.add_column("Win Rate", justify="center", width=10)
    table.add_column("Total Return", justify="center", width=13)

    for _, row in category_df.iterrows():
        s_style = "bold green" if row["sharpe"] > 0.5 else ("yellow" if row["sharpe"] > 0 else "red")
        table.add_row(
            row["category"],
            str(int(row["n_features"])),
            f"[{s_style}]{row['sharpe']:.2f}[/{s_style}]",
            f"{row['win_rate']*100:.1f}%",
            f"{row['total_return']*100:.1f}%",
        )

    console.print(table)


def print_ensemble_results(ensemble):
    """Print ensemble summary."""
    if not ensemble:
        console.print("[yellow]No ensemble built (no profitable models).[/yellow]")
        return

    console.print("\n[bold cyan]ENSEMBLE RESULTS[/bold cyan]")
    console.print(f"  Models: {', '.join(ensemble['models_used'])}")
    console.print(f"  Weights: {ensemble['weights']}")
    s = ensemble['ensemble_sharpe']
    s_style = "bold green" if s > 0.5 else ("yellow" if s > 0 else "red")
    console.print(f"  Sharpe: [{s_style}]{s:.2f}[/{s_style}]")
    console.print(f"  Win Rate: {ensemble['ensemble_win_rate']*100:.1f}%")
    console.print(f"  Profit Factor: {ensemble['ensemble_profit_factor']:.2f}")
    console.print(f"  Total Return: {ensemble['ensemble_total_return']*100:.1f}%")
