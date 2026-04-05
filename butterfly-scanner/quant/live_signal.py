#!/usr/bin/env python3
"""
Live Overnight Signal Generator
=================================
Fetches latest market data, trains RF model on all history,
generates TODAY's signal: BUY NIFTY or STAY CASH.

Run daily before 9:15 AM IST.
Usage: python -m quant.live_signal
"""

import sys
import os
import warnings
import logging
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

warnings.filterwarnings("ignore")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("live_signal")

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler

from quant.ohlc_data import fetch_daily_ohlc, TICKERS
from quant.overnight_signal import build_overnight_features, FEATURE_SOURCES

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)
SIGNAL_LOG = OUTPUT_DIR / "live_signals.csv"


def fetch_fresh_data() -> dict[str, pd.DataFrame]:
    """Fetch daily data with force refresh to get latest bars."""
    today = datetime.now()
    results = {}

    for name, sym in TICKERS.items():
        # Only fetch what we need for the overnight model
        if name not in list(FEATURE_SOURCES.values()) + ["nifty50"]:
            continue
        try:
            import yfinance as yf
            df = yf.download(
                sym,
                start="2015-01-01",
                end=(today + timedelta(days=1)).strftime("%Y-%m-%d"),
                progress=False,
                auto_adjust=True,
            )
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            df.index = pd.to_datetime(df.index)
            df.index.name = "date"
            ohlc_cols = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]
            df = df[ohlc_cols].dropna(subset=["Close"])
            if len(df) > 0:
                results[name] = df
                logger.info("Fetched %s: %d bars through %s", name, len(df), df.index[-1].date())
        except Exception as e:
            logger.error("Failed to fetch %s: %s", name, e)

    return results


def generate_signal(daily_data: dict[str, pd.DataFrame]) -> dict:
    """
    Train RF on all available data, predict next trading day direction.

    Returns dict with signal details.
    """
    X, y, nifty_ohlc = build_overnight_features(daily_data)

    if len(X) < 252:
        return {"error": "Not enough data", "n_rows": len(X)}

    # Train on ALL data
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    model = RandomForestClassifier(
        n_estimators=200, max_depth=6, min_samples_leaf=30,
        random_state=42, n_jobs=-1,
    )
    model.fit(X_scaled, y)

    # The LAST row of X already contains YESTERDAY's features
    # (because build_overnight_features shifts by 1)
    # So predicting on the last row = prediction for the LAST date in X
    # We need to predict for TOMORROW = build features from TODAY's data

    # Get TODAY's feature values (the latest available data, NOT shifted)
    features_today = {}
    nifty = daily_data["nifty50"]
    nifty.index = pd.to_datetime(nifty.index)

    for feat_name, source_key in FEATURE_SOURCES.items():
        if source_key not in daily_data:
            features_today[feat_name] = np.nan
            continue

        src = daily_data[source_key].copy()
        src.index = pd.to_datetime(src.index)
        src = src.sort_index()

        if feat_name == "us10y":
            series = src["Close"].diff()
        elif feat_name == "indiavix":
            series = src["Close"]
        else:
            series = src["Close"].pct_change()

        # Use the LATEST value (this is today's data = tomorrow's feature after shift)
        if len(series.dropna()) > 0:
            features_today[feat_name] = float(series.dropna().iloc[-1])
        else:
            features_today[feat_name] = np.nan

    # Build feature vector in correct order
    feature_names = list(FEATURE_SOURCES.keys())
    X_today = np.array([[features_today.get(f, np.nan) for f in feature_names]])

    # Handle any NaN with forward-fill from last known
    for i, f in enumerate(feature_names):
        if np.isnan(X_today[0, i]):
            X_today[0, i] = float(X.iloc[-1][f])

    X_today_scaled = scaler.transform(X_today)
    pred = model.predict(X_today_scaled)[0]
    prob = model.predict_proba(X_today_scaled)[0]
    prob_up = float(prob[1]) if len(prob) > 1 else float(prob[0])

    # Feature importances
    importances = dict(zip(feature_names, model.feature_importances_))
    top_features = sorted(importances.items(), key=lambda x: x[1], reverse=True)[:3]

    # Recent model accuracy (last 60 trading days from walk-forward)
    # Quick check: predict last 60 days using leave-out
    recent_n = min(60, len(X) - 252)
    if recent_n > 0:
        recent_preds = []
        for i in range(len(X) - recent_n, len(X)):
            X_tr = X.iloc[:i]
            y_tr = y.iloc[:i]
            X_te = X.iloc[[i]]
            sc = StandardScaler()
            X_tr_sc = sc.fit_transform(X_tr)
            X_te_sc = sc.transform(X_te)
            m = RandomForestClassifier(
                n_estimators=200, max_depth=6, min_samples_leaf=30,
                random_state=42, n_jobs=-1,
            )
            m.fit(X_tr_sc, y_tr)
            recent_preds.append(int(m.predict(X_te_sc)[0]) == int(y.iloc[i]))
        recent_accuracy = sum(recent_preds) / len(recent_preds)
    else:
        recent_accuracy = None

    # Latest data dates
    latest_dates = {}
    for feat_name, source_key in FEATURE_SOURCES.items():
        if source_key in daily_data:
            src = daily_data[source_key]
            src.index = pd.to_datetime(src.index)
            latest_dates[feat_name] = str(src.index.max().date())

    nifty_last_close = float(nifty.sort_index()["Close"].iloc[-1])
    nifty_last_date = str(nifty.sort_index().index[-1].date())

    result = {
        "timestamp": datetime.now().isoformat(),
        "prediction_for": "next_trading_day",
        "nifty_last_close": nifty_last_close,
        "nifty_last_date": nifty_last_date,
        "signal": "BUY_NIFTY" if pred == 1 else "STAY_CASH",
        "probability_up": round(prob_up, 4),
        "confidence": "HIGH" if abs(prob_up - 0.5) > 0.15 else ("MEDIUM" if abs(prob_up - 0.5) > 0.08 else "LOW"),
        "recent_60d_accuracy": round(recent_accuracy, 3) if recent_accuracy else None,
        "top_drivers": {k: round(v, 4) for k, v in top_features},
        "features_used": features_today,
        "data_freshness": latest_dates,
        "training_samples": len(X),
    }

    return result


def log_signal(signal: dict) -> None:
    """Append signal to CSV log."""
    row = {
        "timestamp": signal["timestamp"],
        "nifty_last_date": signal.get("nifty_last_date"),
        "nifty_last_close": signal.get("nifty_last_close"),
        "signal": signal["signal"],
        "prob_up": signal["probability_up"],
        "confidence": signal["confidence"],
        "accuracy_60d": signal.get("recent_60d_accuracy"),
    }
    df = pd.DataFrame([row])

    if SIGNAL_LOG.exists():
        existing = pd.read_csv(SIGNAL_LOG)
        df = pd.concat([existing, df], ignore_index=True)

    df.to_csv(SIGNAL_LOG, index=False)
    logger.info("Signal logged to %s", SIGNAL_LOG)


def main():
    print("=" * 60)
    print("  OVERNIGHT SIGNAL — LIVE PREDICTION")
    print("=" * 60)
    print()

    # Step 1: Fetch fresh data
    print(">> Fetching latest market data...")
    daily_data = fetch_fresh_data()

    required = ["nifty50"] + list(FEATURE_SOURCES.values())
    missing = [k for k in required if k not in daily_data]
    if missing:
        print(f"[ERROR] Missing data for: {missing}")
        print("Cannot generate signal. Check internet connection.")
        sys.exit(1)

    print(f">> All {len(daily_data)} data sources loaded.\n")

    # Step 2: Generate signal
    print(">> Training model & generating prediction...")
    signal = generate_signal(daily_data)

    if "error" in signal:
        print(f"[ERROR] {signal['error']}")
        sys.exit(1)

    # Step 3: Display
    print()
    print("=" * 60)
    if signal["signal"] == "BUY_NIFTY":
        print(f"  SIGNAL:  >>> BUY NIFTY <<<")
    else:
        print(f"  SIGNAL:  >>> STAY CASH <<<")
    print(f"  Probability UP: {signal['probability_up']*100:.1f}%")
    print(f"  Confidence:     {signal['confidence']}")
    print(f"  Nifty Close:    {signal['nifty_last_close']:.2f} ({signal['nifty_last_date']})")
    if signal["recent_60d_accuracy"]:
        print(f"  60-day Accuracy: {signal['recent_60d_accuracy']*100:.1f}%")
    print("=" * 60)
    print()

    print("  Top signal drivers:")
    for feat, imp in signal["top_drivers"].items():
        val = signal["features_used"].get(feat)
        if val is not None:
            print(f"    {feat:12s} importance={imp:.3f}  value={val:+.4f}")
    print()

    print("  Data freshness:")
    for feat, dt in signal["data_freshness"].items():
        print(f"    {feat:12s} → {dt}")
    print()

    # Step 4: Log
    log_signal(signal)
    print(f"  Signal saved to {SIGNAL_LOG}")
    print()
    print("  [!] This is a statistical model. Past performance ≠ future results.")
    print("  [!] Always use proper position sizing and risk management.")


if __name__ == "__main__":
    main()
