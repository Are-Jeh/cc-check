"""Feature Factory — combine celestial, nature, and market data into model-ready features."""

import logging
import numpy as np
import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

# ── Market data fetcher ──────────────────────────────────────────────

TICKERS = {
    # Indian indices
    "nifty50": "^NSEI",
    "banknifty": "^NSEBANK",
    "niftyit": "^CNXIT",
    "niftyfmcg": "^CNXFMCG",
    "indiavix": "^INDIAVIX",
    # Commodities & FX
    "gold": "GC=F",
    "silver": "SI=F",
    "crude": "CL=F",
    "usdinr": "INR=X",
    # Global
    "sp500": "^GSPC",
    "dxy": "DX-Y.NYB",
    "us10y": "^TNX",
}


def fetch_market_data(start="2015-01-01", end="2025-12-31") -> pd.DataFrame:
    """Fetch daily close prices for all tickers."""
    frames = {}
    for name, sym in TICKERS.items():
        try:
            df = yf.download(sym, start=start, end=end, progress=False, auto_adjust=True)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            s = df["Close"].squeeze()
            s.index = pd.to_datetime(s.index)
            frames[name] = s
            logger.info("Fetched %s: %d rows", name, len(s))
        except Exception as e:
            logger.error("Failed %s: %s", name, e)
    return pd.DataFrame(frames)


def compute_market_features(prices: pd.DataFrame) -> pd.DataFrame:
    """Compute returns, volatility, momentum, and cross-asset features."""
    features = pd.DataFrame(index=prices.index)

    for col in prices.columns:
        # Daily returns
        features[f"{col}_ret1"] = prices[col].pct_change()
        # 5-day return
        features[f"{col}_ret5"] = prices[col].pct_change(5)
        # 20-day return (monthly momentum)
        features[f"{col}_ret20"] = prices[col].pct_change(20)
        # 5-day rolling volatility
        features[f"{col}_vol5"] = features[f"{col}_ret1"].rolling(5).std()
        # 20-day rolling volatility
        features[f"{col}_vol20"] = features[f"{col}_ret1"].rolling(20).std()
        # RSI (14-day)
        features[f"{col}_rsi14"] = _rsi(prices[col], 14)
        # Distance from 20-day SMA (mean reversion signal)
        sma20 = prices[col].rolling(20).mean()
        features[f"{col}_sma20_dist"] = (prices[col] - sma20) / sma20

    # Cross-asset spreads
    if "gold" in prices.columns and "silver" in prices.columns:
        features["gold_silver_ratio"] = prices["gold"] / prices["silver"]
    if "indiavix" in prices.columns and "nifty50" in prices.columns:
        features["vix_nifty_ratio"] = prices["indiavix"] / prices["nifty50"]

    return features


def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


# ── Calendar features ────────────────────────────────────────────────

def compute_calendar_features(index: pd.DatetimeIndex) -> pd.DataFrame:
    """Calendar-based features for the given date range."""
    df = pd.DataFrame(index=index)
    df["day_of_week"] = index.dayofweek  # 0=Mon
    df["day_of_month"] = index.day
    df["month"] = index.month
    df["week_of_year"] = index.isocalendar().week.values.astype(int)
    df["quarter"] = index.quarter
    df["is_month_start"] = (index.day <= 3).astype(int)
    df["is_month_end"] = (index.day >= 27).astype(int)
    df["is_monday"] = (index.dayofweek == 0).astype(int)
    df["is_friday"] = (index.dayofweek == 4).astype(int)
    # Expiry week proxy (last Thursday of month)
    df["is_expiry_week"] = ((index.day >= 22) & (index.dayofweek <= 4)).astype(int)
    # Cyclical encoding
    df["month_sin"] = np.sin(2 * np.pi * index.month / 12)
    df["month_cos"] = np.cos(2 * np.pi * index.month / 12)
    df["dow_sin"] = np.sin(2 * np.pi * index.dayofweek / 5)
    df["dow_cos"] = np.cos(2 * np.pi * index.dayofweek / 5)
    df["dom_sin"] = np.sin(2 * np.pi * index.day / 31)
    df["dom_cos"] = np.cos(2 * np.pi * index.day / 31)
    return df


# ── Master feature builder ───────────────────────────────────────────

def build_feature_matrix(
    celestial_df: pd.DataFrame,
    nature_df: pd.DataFrame,
    market_prices: pd.DataFrame,
    target_col: str = "nifty50",
    forward_days: int = 1,
) -> tuple[pd.DataFrame, pd.Series]:
    """
    Combine all data sources into a single feature matrix + target.

    Parameters
    ----------
    celestial_df : output of celestial_engine.compute_all_celestial() + compute_hybrid_indicators()
    nature_df    : output of nature_metrics.collect_all_nature_metrics()
    market_prices: output of fetch_market_data()
    target_col   : which market series to predict
    forward_days : predict N-day forward return (1=next day, 5=next week)

    Returns
    -------
    X : feature DataFrame (aligned, no future leakage)
    y : target Series (forward return)
    """
    logger.info("Building feature matrix for target=%s, forward=%d days", target_col, forward_days)

    # Target: forward return (what we're predicting)
    if target_col not in market_prices.columns:
        raise ValueError(f"Target {target_col} not in market data")

    target = market_prices[target_col].pct_change(forward_days).shift(-forward_days)
    target.name = f"{target_col}_fwd{forward_days}d"

    # Market features (LAGGED — no future data)
    market_features = compute_market_features(market_prices)

    # Calendar features
    calendar_features = compute_calendar_features(market_prices.index)

    # Combine all feature sources
    all_features = [market_features, calendar_features]

    if celestial_df is not None and not celestial_df.empty:
        # Prefix celestial columns
        cel = celestial_df.copy()
        cel.columns = [f"cel_{c}" if not c.startswith("cel_") else c for c in cel.columns]
        all_features.append(cel)

    if nature_df is not None and not nature_df.empty:
        # Prefix nature columns
        nat = nature_df.copy()
        nat.columns = [f"nat_{c}" if not c.startswith("nat_") else c for c in nat.columns]
        all_features.append(nat)

    # Merge everything on date index
    X = all_features[0]
    for feat_df in all_features[1:]:
        X = X.join(feat_df, how="left")

    # Align X and y
    common_idx = X.index.intersection(target.dropna().index)
    X = X.loc[common_idx]
    y = target.loc[common_idx]

    # Drop rows with too many NaN features (>50%)
    nan_threshold = 0.5
    X = X.loc[X.notna().mean(axis=1) > nan_threshold]
    y = y.loc[X.index]

    # Fill remaining NaN with forward fill then 0
    X = X.ffill().fillna(0)

    # Replace inf
    X = X.replace([np.inf, -np.inf], 0)

    logger.info("Feature matrix: %d rows x %d features", X.shape[0], X.shape[1])
    logger.info("Target: %d values, mean=%.6f, std=%.6f", len(y), y.mean(), y.std())

    return X, y


def create_interaction_features(X: pd.DataFrame, top_n: int = 20) -> pd.DataFrame:
    """Create interaction features between the top_n most important celestial/nature features."""
    # Select celestial and nature columns only
    cel_nat_cols = [c for c in X.columns if c.startswith(("cel_", "nat_"))]
    if len(cel_nat_cols) < 2:
        return X

    # Use variance as a simple proxy for "interesting" features
    variances = X[cel_nat_cols].var().sort_values(ascending=False)
    top_cols = variances.head(top_n).index.tolist()

    interactions = pd.DataFrame(index=X.index)
    for i in range(len(top_cols)):
        for j in range(i + 1, min(i + 5, len(top_cols))):
            col_a, col_b = top_cols[i], top_cols[j]
            name_a = col_a.replace("cel_", "").replace("nat_", "")[:15]
            name_b = col_b.replace("cel_", "").replace("nat_", "")[:15]
            # Multiplication interaction
            interactions[f"ix_{name_a}_x_{name_b}"] = X[col_a] * X[col_b]

    return pd.concat([X, interactions], axis=1)
