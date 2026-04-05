"""
Overnight Signal Predictor & Backtester
========================================
Multi-market feature model: predict next-day Nifty direction from
overnight global cues (S&P 500, DXY, Gold, Crude, US10Y, India VIX, USD/INR).

Gap-fade strategy: exploit overnight gap mean-reversion patterns.

STRICT no-lookahead: all features are PREVIOUS trading day values.
Walk-forward validation: expanding window, min 252 days training.
"""

from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score

warnings.filterwarnings("ignore")
logger = logging.getLogger(__name__)


# ── Data structures ──────────────────────────────────────────────────

@dataclass
class OvernightModelResult:
    """Walk-forward result for a single classifier."""
    name: str
    accuracy: float
    accuracy_by_year: dict[int, float]
    sharpe: float
    cagr: float
    max_drawdown: float
    total_return: float
    n_predictions: int
    predictions: Optional[pd.DataFrame] = None  # date, pred, actual, return


@dataclass
class GapFadeResult:
    """Gap-fade strategy backtest result for a gap-size bucket."""
    bucket: str
    n_trades: int
    fill_rate: float
    win_rate: float
    avg_return: float
    total_return: float
    sharpe: float


# ── Feature alignment ────────────────────────────────────────────────

FEATURE_SOURCES = {
    "sp500":    "sp500",
    "dxy":      "dxy",
    "gold":     "gold",
    "crude":    "crude",
    "us10y":    "us10y",
    "indiavix": "indiavix",
    "usdinr":   "usdinr",
}


def build_overnight_features(
    daily_data: dict[str, pd.DataFrame],
) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame]:
    """
    Build feature matrix from cached daily parquets.

    Returns
    -------
    X : feature DataFrame (each row = features from PREVIOUS day, indexed by prediction date)
    y : target Series (1 = Nifty up, 0 = Nifty down)
    nifty_ohlc : Nifty OHLC aligned to same dates (for gap-fade and backtest)
    """
    if "nifty50" not in daily_data:
        raise ValueError("nifty50 data required but missing")

    nifty = daily_data["nifty50"].copy()
    nifty.index = pd.to_datetime(nifty.index)
    nifty = nifty.sort_index()

    # Nifty daily return (close-to-close)
    nifty_ret = nifty["Close"].pct_change()
    # Target: 1 if today's return > 0, else 0
    target = (nifty_ret > 0).astype(int)
    target.name = "nifty_up"

    # Build features from PREVIOUS day values
    features = pd.DataFrame(index=nifty.index)

    for feat_name, source_key in FEATURE_SOURCES.items():
        if source_key not in daily_data:
            logger.warning("Missing data for %s — will be NaN", source_key)
            continue

        src = daily_data[source_key].copy()
        src.index = pd.to_datetime(src.index)
        src = src.sort_index()

        if feat_name == "us10y":
            # Yield: use level change (basis points)
            series = src["Close"].diff()
        elif feat_name == "indiavix":
            # VIX: use level (not return)
            series = src["Close"]
        else:
            # Return
            series = src["Close"].pct_change()

        series.name = feat_name

        # Forward-fill to handle different holiday calendars, then
        # reindex to Nifty trading dates
        series = series.reindex(nifty.index, method="ffill")

        # SHIFT by 1: use PREVIOUS day's value as feature for TODAY's prediction
        features[feat_name] = series.shift(1)

    # Drop rows where target or all features are NaN
    valid = features.dropna(how="all").index.intersection(target.dropna().index)
    features = features.loc[valid]
    target = target.loc[valid]

    # Forward-fill remaining NaN within features (some markets closed)
    features = features.ffill().bfill()

    # Drop any remaining NaN rows
    mask = features.notna().all(axis=1) & target.notna()
    features = features.loc[mask]
    target = target.loc[mask]

    # Align nifty OHLC
    nifty_ohlc = nifty.loc[nifty.index.isin(features.index)].copy()
    features = features.loc[features.index.isin(nifty_ohlc.index)]
    target = target.loc[target.index.isin(nifty_ohlc.index)]

    logger.info(
        "Overnight features: %d rows x %d features, date range %s to %s",
        len(features), features.shape[1],
        features.index[0].date(), features.index[-1].date(),
    )
    return features, target, nifty_ohlc


# ── Walk-forward classifier ─────────────────────────────────────────

CLASSIFIERS = {
    "logistic_regression": lambda: LogisticRegression(
        C=1.0, max_iter=1000, random_state=42,
    ),
    "random_forest": lambda: RandomForestClassifier(
        n_estimators=200, max_depth=6, min_samples_leaf=30,
        random_state=42, n_jobs=-1,
    ),
}


def walk_forward_predict(
    X: pd.DataFrame,
    y: pd.Series,
    model_fn,
    min_train: int = 252,
) -> pd.DataFrame:
    """
    Walk-forward: train on expanding window (min_train days), predict next day.

    Returns DataFrame with columns: date, pred, actual, prob_up
    """
    records = []
    dates = X.index.tolist()
    n = len(dates)

    scaler = StandardScaler()

    for i in range(min_train, n):
        X_train = X.iloc[:i]
        y_train = y.iloc[:i]
        X_test = X.iloc[[i]]

        # Scale
        X_train_sc = scaler.fit_transform(X_train)
        X_test_sc = scaler.transform(X_test)

        # Train and predict
        model = model_fn()
        model.fit(X_train_sc, y_train)

        pred = model.predict(X_test_sc)[0]
        prob = model.predict_proba(X_test_sc)[0]
        prob_up = prob[1] if len(prob) > 1 else prob[0]

        records.append({
            "date": dates[i],
            "pred": int(pred),
            "actual": int(y.iloc[i]),
            "prob_up": float(prob_up),
        })

    return pd.DataFrame(records)


def backtest_signal(
    predictions: pd.DataFrame,
    nifty_ohlc: pd.DataFrame,
) -> dict:
    """
    Backtest: if model says UP, hold long close-to-close. If DOWN, cash.

    Signal generated end-of-day T-1 → position held from close T-1 to close T.
    Uses close-to-close returns (captures overnight premium).

    Returns dict with strategy daily returns aligned to dates.
    """
    nifty_ohlc = nifty_ohlc.copy()
    nifty_ohlc.index = pd.to_datetime(nifty_ohlc.index)

    # Close-to-close return (captures overnight + intraday)
    close_ret = nifty_ohlc["Close"].pct_change()

    strategy_returns = []
    bh_returns = []
    dates_out = []

    for _, row in predictions.iterrows():
        dt = pd.Timestamp(row["date"])
        if dt not in close_ret.index:
            continue
        ret = close_ret.loc[dt]
        if pd.isna(ret):
            continue

        dates_out.append(dt)
        bh_returns.append(ret)

        if row["pred"] == 1:
            strategy_returns.append(ret)  # long
        else:
            strategy_returns.append(0.0)  # cash

    return {
        "dates": dates_out,
        "strategy_returns": np.array(strategy_returns),
        "bh_returns": np.array(bh_returns),
    }


def compute_performance(
    returns: np.ndarray,
    dates: list,
    trading_days_per_year: int = 252,
) -> dict:
    """Compute CAGR, Sharpe, max drawdown from daily return array."""
    if len(returns) == 0:
        return {"cagr": 0.0, "sharpe": 0.0, "max_drawdown": 0.0, "total_return": 0.0}

    cum = np.cumprod(1 + returns)
    total_return = cum[-1] - 1

    # CAGR
    n_years = len(returns) / trading_days_per_year
    if n_years > 0 and cum[-1] > 0:
        cagr = (cum[-1]) ** (1 / n_years) - 1
    else:
        cagr = 0.0

    # Sharpe
    if returns.std() > 0:
        sharpe = (returns.mean() / returns.std()) * np.sqrt(trading_days_per_year)
    else:
        sharpe = 0.0

    # Max drawdown
    rolling_max = np.maximum.accumulate(cum)
    drawdown = (cum - rolling_max) / rolling_max
    max_drawdown = float(np.min(drawdown))

    return {
        "cagr": float(cagr),
        "sharpe": float(sharpe),
        "max_drawdown": float(max_drawdown),
        "total_return": float(total_return),
    }


def run_overnight_models(
    daily_data: dict[str, pd.DataFrame],
) -> list[OvernightModelResult]:
    """
    Run all overnight signal models with walk-forward validation.

    Returns list of OvernightModelResult sorted by Sharpe.
    """
    X, y, nifty_ohlc = build_overnight_features(daily_data)

    results = []
    for model_name, model_fn in CLASSIFIERS.items():
        logger.info("Walk-forward: %s (%d prediction days)", model_name, len(X) - 252)

        preds = walk_forward_predict(X, y, model_fn, min_train=252)

        if preds.empty:
            logger.warning("No predictions for %s", model_name)
            continue

        # Accuracy
        acc = accuracy_score(preds["actual"], preds["pred"])

        # Accuracy by year
        preds["year"] = pd.to_datetime(preds["date"]).dt.year
        acc_by_year = {}
        for yr, grp in preds.groupby("year"):
            acc_by_year[int(yr)] = float(accuracy_score(grp["actual"], grp["pred"]))

        # Backtest
        bt = backtest_signal(preds, nifty_ohlc)
        perf = compute_performance(bt["strategy_returns"], bt["dates"])
        bh_perf = compute_performance(bt["bh_returns"], bt["dates"])

        result = OvernightModelResult(
            name=model_name,
            accuracy=acc,
            accuracy_by_year=acc_by_year,
            sharpe=perf["sharpe"],
            cagr=perf["cagr"],
            max_drawdown=perf["max_drawdown"],
            total_return=perf["total_return"],
            n_predictions=len(preds),
            predictions=preds,
        )
        results.append(result)

        logger.info(
            "%s — Acc=%.1f%% | Sharpe=%.2f | CAGR=%.1f%% | MaxDD=%.1f%%",
            model_name, acc * 100, perf["sharpe"],
            perf["cagr"] * 100, perf["max_drawdown"] * 100,
        )

    results.sort(key=lambda r: r.sharpe, reverse=True)
    return results


# ── Gap-fade strategy ────────────────────────────────────────────────

GAP_BUCKETS = [
    ("tiny_fade",     0.001, 0.003, "fade"),    # 0.1%–0.3%: fade
    ("optimal_fade",  0.003, 0.008, "fade"),    # 0.3%–0.8%: optimal fade zone
    ("medium_fade",   0.008, 0.015, "fade"),    # 0.8%–1.5%: fade
    ("large_ride",    0.015, 0.050, "ride"),    # >1.5%: ride the gap
]


def run_gap_fade_backtest(
    daily_data: dict[str, pd.DataFrame],
) -> tuple[list[GapFadeResult], pd.DataFrame]:
    """
    Backtest gap-fade / gap-ride strategies.

    Returns
    -------
    results : list of GapFadeResult per bucket
    gap_df  : DataFrame with per-day gap analysis
    """
    if "nifty50" not in daily_data:
        raise ValueError("nifty50 data required")

    nifty = daily_data["nifty50"].copy()
    nifty.index = pd.to_datetime(nifty.index)
    nifty = nifty.sort_index()

    if "Open" not in nifty.columns or "Close" not in nifty.columns:
        raise ValueError("Nifty data missing Open/Close columns")

    prev_close = nifty["Close"].shift(1)
    gap = (nifty["Open"] - prev_close) / prev_close
    intraday_ret = (nifty["Close"] - nifty["Open"]) / nifty["Open"]

    # Gap fill: did the gap close during the day?
    # Gap up filled if Low <= prev_close; gap down filled if High >= prev_close
    gap_filled = pd.Series(False, index=nifty.index)
    for i in range(1, len(nifty)):
        g = gap.iloc[i]
        if pd.isna(g):
            continue
        if g > 0:  # gap up
            gap_filled.iloc[i] = nifty["Low"].iloc[i] <= prev_close.iloc[i]
        elif g < 0:  # gap down
            gap_filled.iloc[i] = nifty["High"].iloc[i] >= prev_close.iloc[i]

    # Build per-day DataFrame
    gap_df = pd.DataFrame({
        "date": nifty.index,
        "gap_pct": gap.values,
        "abs_gap_pct": gap.abs().values,
        "intraday_return": intraday_ret.values,
        "gap_filled": gap_filled.values,
        "gap_direction": np.sign(gap.values),
    }).dropna(subset=["gap_pct"])
    gap_df = gap_df.set_index("date")

    # Backtest each bucket
    results = []
    for bucket_name, lo, hi, action in GAP_BUCKETS:
        mask = (gap_df["abs_gap_pct"] >= lo) & (gap_df["abs_gap_pct"] < hi)
        bucket = gap_df.loc[mask].copy()

        if len(bucket) == 0:
            results.append(GapFadeResult(
                bucket=bucket_name, n_trades=0, fill_rate=0.0,
                win_rate=0.0, avg_return=0.0, total_return=0.0, sharpe=0.0,
            ))
            continue

        fill_rate = bucket["gap_filled"].mean()

        if action == "fade":
            # Fade = go opposite to gap direction
            # If gap up, short (expect price to come back down) => return = -intraday_return
            # If gap down, long (expect price to bounce up) => return = +intraday_return
            strategy_ret = -bucket["gap_direction"] * bucket["intraday_return"]
        else:
            # Ride = go with gap direction
            strategy_ret = bucket["gap_direction"] * bucket["intraday_return"]

        win_rate = (strategy_ret > 0).mean()
        avg_return = strategy_ret.mean()
        total_return = (1 + strategy_ret).prod() - 1

        if strategy_ret.std() > 0:
            sharpe = (strategy_ret.mean() / strategy_ret.std()) * np.sqrt(252)
        else:
            sharpe = 0.0

        results.append(GapFadeResult(
            bucket=bucket_name,
            n_trades=len(bucket),
            fill_rate=float(fill_rate),
            win_rate=float(win_rate),
            avg_return=float(avg_return),
            total_return=float(total_return),
            sharpe=float(sharpe),
        ))

        logger.info(
            "Gap %s: %d trades | Fill=%.0f%% | Win=%.0f%% | AvgRet=%.3f%% | Sharpe=%.2f",
            bucket_name, len(bucket), fill_rate * 100, win_rate * 100,
            avg_return * 100, sharpe,
        )

    return results, gap_df
