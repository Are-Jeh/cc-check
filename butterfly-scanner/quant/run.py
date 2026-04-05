#!/usr/bin/env python3
"""
Butterfly Quant — Nature-Based Market Prediction Pipeline

Computes real astronomical mechanics (distances, tidal forces, vector products),
combines with nature metrics (geomagnetic, seismic, weather, solar),
builds ML models, and reports what actually predicts stock returns.
"""

import sys
import os
import warnings
import logging
import time

# Ensure parent dir is on path so "quant" package is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

warnings.filterwarnings("ignore")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("quant")

from rich.console import Console
console = Console()


def main():
    t0 = time.time()

    # ── Phase 1: Collect Data ─────────────────────────────────────
    console.rule("[bold blue]PHASE 1: Data Collection")

    console.print("  Computing celestial mechanics (10 years)...")
    from quant.celestial_engine import compute_all_celestial, compute_hybrid_indicators
    celestial_raw = compute_all_celestial(start_date="2015-01-01", end_date="2025-12-31")
    celestial_df = compute_hybrid_indicators(celestial_raw)
    console.print(f"    Celestial: {celestial_df.shape[1]} features, {len(celestial_df)} days")

    console.print("  Collecting nature metrics...")
    try:
        from quant.nature_metrics import collect_all_nature_metrics
        nature_df = collect_all_nature_metrics(start_date="2015-01-01", end_date="2025-12-31")
        console.print(f"    Nature: {nature_df.shape[1]} features, {len(nature_df)} days")
    except Exception as e:
        logger.error("Nature metrics failed: %s", e)
        import pandas as pd
        nature_df = pd.DataFrame()
        console.print(f"    [red]Nature metrics failed: {e}[/red]")

    console.print("  Fetching market data (10 years)...")
    from quant.feature_factory import fetch_market_data
    market_prices = fetch_market_data(start="2015-01-01", end="2025-12-31")
    console.print(f"    Market: {market_prices.shape[1]} tickers, {len(market_prices)} days")

    # ── Phase 2: Feature Engineering ──────────────────────────────
    console.rule("[bold blue]PHASE 2: Feature Engineering")

    from quant.feature_factory import build_feature_matrix, create_interaction_features

    targets = ["nifty50", "gold", "banknifty"]
    all_run_results = {}

    for target in targets:
        if target not in market_prices.columns:
            console.print(f"  [yellow]Skipping {target} — not in data[/yellow]")
            continue

        console.print(f"\n  [bold cyan]═══ TARGET: {target} (next-day return) ═══[/bold cyan]")

        X, y = build_feature_matrix(
            celestial_df=celestial_df,
            nature_df=nature_df,
            market_prices=market_prices,
            target_col=target,
            forward_days=1,
        )

        # Add interaction features
        X = create_interaction_features(X, top_n=15)
        console.print(f"    Features: {X.shape[1]} | Rows: {X.shape[0]}")

        # ── Phase 3: Category Analysis ────────────────────────────
        console.rule(f"[bold blue]PHASE 3: Category Analysis — {target}")

        from quant.models import analyze_feature_categories
        category_df = analyze_feature_categories(X, y)

        from quant.report import print_category_table, plot_category_comparison
        print_category_table(category_df)
        plot_category_comparison(category_df)

        # ── Phase 4: Full Model Training ──────────────────────────
        console.rule(f"[bold blue]PHASE 4: Model Training — {target}")

        from quant.models import run_all_models, build_ensemble
        model_results = run_all_models(X, y, n_splits=5, feature_select_k=50)

        from quant.report import print_model_table, plot_feature_importance, plot_equity_curves
        print_model_table(model_results)
        plot_feature_importance(model_results)
        plot_equity_curves(model_results, y)

        # ── Phase 5: Ensemble ─────────────────────────────────────
        console.rule(f"[bold blue]PHASE 5: Ensemble — {target}")

        ensemble = build_ensemble(model_results, y)
        from quant.report import print_ensemble_results
        print_ensemble_results(ensemble)

        all_run_results[target] = {
            "models": model_results,
            "categories": category_df,
            "ensemble": ensemble,
        }

    # ── Phase 6: Celestial Deep Dive Charts ───────────────────────
    console.rule("[bold blue]PHASE 6: Celestial Deep Dive")

    from quant.report import plot_celestial_vs_returns
    plot_celestial_vs_returns(celestial_df, market_prices, target="nifty50")

    # ── Summary ───────────────────────────────────────────────────
    elapsed = time.time() - t0
    console.rule("[bold green]COMPLETE")
    console.print(f"\n  Time: {elapsed:.0f}s")
    console.print(f"  Charts saved to: charts/quant/")

    # Final verdict
    console.print("\n[bold cyan]═══ VERDICT ═══[/bold cyan]")
    for target, res in all_run_results.items():
        best = res["models"][0] if res["models"] else None
        cat = res["categories"]
        cel_row = cat[cat["category"] == "celestial_only"]
        mkt_row = cat[cat["category"] == "market_only"]
        all_row = cat[cat["category"] == "all_features"]

        if best:
            console.print(f"\n  [bold]{target}[/bold]:")
            console.print(f"    Best model: {best.name} | Sharpe={best.sharpe_ratio:.2f} | Win={best.win_rate*100:.1f}%")
            if not cel_row.empty:
                cs = cel_row.iloc[0]["sharpe"]
                console.print(f"    Celestial alone: Sharpe={cs:.2f}")
            if not mkt_row.empty:
                ms = mkt_row.iloc[0]["sharpe"]
                console.print(f"    Market alone: Sharpe={ms:.2f}")
            if not all_row.empty:
                als = all_row.iloc[0]["sharpe"]
                console.print(f"    All combined: Sharpe={als:.2f}")

            if best.top_features:
                cel_in_top = [f for f, _ in best.top_features if f.startswith("cel_")]
                nat_in_top = [f for f, _ in best.top_features if f.startswith("nat_")]
                if cel_in_top:
                    console.print(f"    [bold magenta]Celestial features in top 10: {cel_in_top}[/bold magenta]")
                if nat_in_top:
                    console.print(f"    [bold green]Nature features in top 10: {nat_in_top}[/bold green]")

    console.print("\n  [dim]All results use walk-forward validation. No future leakage.[/dim]")
    console.print("  [dim]Past performance ≠ future results. Trade at your own risk.[/dim]")


if __name__ == "__main__":
    main()
