#!/usr/bin/env python3
"""Butterfly Effect Correlation Scanner — Main Orchestrator."""

import sys
import logging
import pandas as pd
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

# Setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("butterfly")
console = Console()


def main():
    from db import init_db, get_all_indicators, load_series, store_analysis
    from collectors.market import collect_market_data
    from collectors.celestial import collect_celestial_data
    from collectors.weather import collect_weather_data
    from collectors.digital import collect_digital_data
    from collectors.economic import collect_economic_data
    from collectors.agricultural import collect_agricultural_data
    from analysis.correlations import compute_lagged_correlations
    from analysis.granger import granger_causality_test
    from analysis.mutual_info import compute_mutual_information
    from analysis.regime import detect_regimes, test_regime_stability
    from output.butterfly_map import generate_butterfly_map, generate_regime_report
    from config import MAX_LAG_DAYS, SIGNIFICANCE_LEVEL

    init_db()

    # PHASE 1: Data Collection
    console.rule("[bold blue]PHASE 1: Data Collection")

    all_indicators = {}
    market_data = {}

    collectors = [
        ("Market", collect_market_data),
        ("Celestial", collect_celestial_data),
        ("Weather", collect_weather_data),
        ("Digital", collect_digital_data),
        ("Economic", collect_economic_data),
        ("Agricultural", collect_agricultural_data),
    ]

    for name, collector_fn in collectors:
        console.print(f"  Collecting [cyan]{name}[/cyan] data...")
        try:
            data = collector_fn()
            if name == "Market":
                # Separate market returns (targets) from indicators
                for k, v in data.items():
                    if k.startswith("ret_"):
                        market_data[k] = v
                    else:
                        all_indicators[k] = v
            else:
                all_indicators.update(data)
            console.print(f"    Got {len(data)} series")
        except Exception as e:
            logger.error(f"Collector {name} failed: {e}")
            console.print(f"    [red]Failed: {e}[/red]")

    if not market_data:
        console.print("[red]No market data collected. Cannot proceed.[/red]")
        sys.exit(1)

    console.print(f"\n  Total indicators: {len(all_indicators)}")
    console.print(f"  Market series: {len(market_data)}")

    # PHASE 2: Correlation Analysis
    console.rule("[bold blue]PHASE 2: Correlation Analysis")

    all_results = []
    total_pairs = len(all_indicators) * len(market_data)

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
        task = progress.add_task("Analyzing...", total=total_pairs)

        for ind_name, ind_series in all_indicators.items():
            for mkt_name, mkt_series in market_data.items():
                progress.update(task, description=f"{ind_name} vs {mkt_name}")

                # Correlations
                corr_results = compute_lagged_correlations(ind_series, mkt_series, MAX_LAG_DAYS)

                # Granger
                granger_result = granger_causality_test(ind_series, mkt_series, MAX_LAG_DAYS)

                # Mutual Information
                mi_results = compute_mutual_information(ind_series, mkt_series, MAX_LAG_DAYS)

                # Merge results per lag
                for corr in corr_results:
                    lag = corr["lag"]
                    mi_entry = next((m for m in mi_results if m["lag"] == lag), {})

                    result = {
                        "indicator": ind_name,
                        "market": mkt_name,
                        "lag_days": lag,
                        "pearson_r": corr.get("pearson_r"),
                        "pearson_p": corr.get("pearson_p"),
                        "spearman_r": corr.get("spearman_r"),
                        "spearman_p": corr.get("spearman_p"),
                        "kendall_r": corr.get("kendall_r"),
                        "kendall_p": corr.get("kendall_p"),
                        "granger_p": granger_result.get("all_results", {}).get(lag) if granger_result else None,
                        "mutual_info": mi_entry.get("mi_score"),
                        "regime": "all",
                    }
                    all_results.append(result)

                progress.advance(task)

    # Store results
    console.print(f"  Storing {len(all_results)} analysis results...")
    store_analysis(all_results)

    # PHASE 3: Butterfly Map
    console.rule("[bold blue]PHASE 3: Butterfly Map")
    from db import load_all_analysis
    analysis_df = load_all_analysis()
    generate_butterfly_map(analysis_df)

    # PHASE 4: Regime Conditioning
    console.rule("[bold blue]PHASE 4: Regime Conditioning")

    # Find top 20 indicators by significance
    all_regime = analysis_df[analysis_df["regime"] == "all"].dropna(subset=["pearson_p"]).copy()
    if all_regime.empty:
        console.print("[yellow]No valid results for regime analysis.[/yellow]")
        generate_regime_report({})
        console.rule("[bold green]SCAN COMPLETE")
        console.print("Results saved to butterfly.db and output/butterfly_map.csv")
        return

    best_idx = all_regime.groupby(["indicator", "market"])["pearson_p"].idxmin()
    best_per_indicator = all_regime.loc[best_idx].sort_values("pearson_p").head(20)

    # Detect regimes for each market
    regime_results = {}
    for mkt_name, mkt_series in market_data.items():
        regimes = detect_regimes(mkt_series)

        for _, row in best_per_indicator.iterrows():
            if row["market"] != mkt_name:
                continue
            ind_name = row["indicator"]
            if ind_name not in all_indicators:
                continue
            best_lag = int(row["lag_days"])
            stability = test_regime_stability(
                all_indicators[ind_name], mkt_series, regimes, best_lag
            )
            regime_results[f"{ind_name} -> {mkt_name}"] = stability

            # Store regime-specific results
            for regime_name, regime_stats in stability.items():
                store_analysis([{
                    "indicator": ind_name,
                    "market": mkt_name,
                    "lag_days": best_lag,
                    "pearson_r": regime_stats.get("r"),
                    "pearson_p": regime_stats.get("p"),
                    "regime": regime_name,
                }])

    generate_regime_report(regime_results)

    console.rule("[bold green]SCAN COMPLETE")
    console.print("Results saved to butterfly.db and output/butterfly_map.csv")


if __name__ == "__main__":
    main()
