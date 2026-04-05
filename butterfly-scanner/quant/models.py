"""Multi-model quant pipeline — test every approach, report what works."""

import logging
import warnings
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Optional

from sklearn.linear_model import LinearRegression, Ridge, Lasso
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.svm import SVR
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
from sklearn.feature_selection import mutual_info_regression
from scipy import stats

warnings.filterwarnings("ignore")
logger = logging.getLogger(__name__)


@dataclass
class ModelResult:
    name: str
    r2_train: float
    r2_test: float
    rmse_test: float
    mae_test: float
    sharpe_ratio: float  # if used as a trading signal
    win_rate: float      # % of correct direction predictions
    profit_factor: float  # gross profits / gross losses
    top_features: list = field(default_factory=list)
    predictions: Optional[pd.Series] = None


# ── Walk-forward validation ──────────────────────────────────────────

def walk_forward_split(X: pd.DataFrame, y: pd.Series,
                       train_pct: float = 0.7,
                       n_splits: int = 5) -> list[tuple]:
    """
    Time-series walk-forward splits.
    No shuffling. No future leakage. The only honest way.

    Returns list of (train_idx, test_idx) tuples.
    """
    n = len(X)
    min_train = int(n * train_pct)
    test_size = (n - min_train) // n_splits

    splits = []
    for i in range(n_splits):
        train_end = min_train + i * test_size
        test_end = min(train_end + test_size, n)
        if test_end <= train_end:
            break
        train_idx = list(range(0, train_end))
        test_idx = list(range(train_end, test_end))
        splits.append((train_idx, test_idx))

    return splits


# ── Trading metrics ──────────────────────────────────────────────────

def compute_trading_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    """Compute metrics that matter for making money."""
    # Direction accuracy
    true_dir = np.sign(y_true)
    pred_dir = np.sign(y_pred)
    correct = (true_dir == pred_dir)
    win_rate = correct.mean()

    # Sharpe: if we go long when prediction > 0, short when < 0
    strategy_returns = y_true * np.sign(y_pred)
    if strategy_returns.std() > 0:
        sharpe = (strategy_returns.mean() / strategy_returns.std()) * np.sqrt(252)
    else:
        sharpe = 0.0

    # Profit factor
    gains = strategy_returns[strategy_returns > 0].sum()
    losses = abs(strategy_returns[strategy_returns < 0].sum())
    profit_factor = gains / losses if losses > 0 else float("inf")

    # Max drawdown
    cum_returns = np.cumprod(1 + strategy_returns)
    rolling_max = np.maximum.accumulate(cum_returns)
    drawdown = (cum_returns - rolling_max) / rolling_max
    max_drawdown = np.min(drawdown)

    # Total return
    total_return = cum_returns[-1] - 1 if len(cum_returns) > 0 else 0

    return {
        "win_rate": win_rate,
        "sharpe": sharpe,
        "profit_factor": profit_factor,
        "max_drawdown": max_drawdown,
        "total_return": total_return,
        "avg_daily_return": strategy_returns.mean(),
        "n_trades": len(y_true),
    }


# ── Feature importance ───────────────────────────────────────────────

def get_feature_importance(model, feature_names: list, method: str = "auto") -> pd.Series:
    """Extract feature importance from any model type."""
    if hasattr(model, "feature_importances_"):
        imp = pd.Series(model.feature_importances_, index=feature_names)
    elif hasattr(model, "coef_"):
        imp = pd.Series(np.abs(model.coef_.flatten()), index=feature_names)
    else:
        imp = pd.Series(dtype=float)
    return imp.sort_values(ascending=False)


# ── Model definitions ────────────────────────────────────────────────

MODELS = {
    "linear": lambda: LinearRegression(),
    "ridge": lambda: Ridge(alpha=1.0),
    "lasso": lambda: Lasso(alpha=0.001),
    "random_forest": lambda: RandomForestRegressor(
        n_estimators=200, max_depth=8, min_samples_leaf=20,
        random_state=42, n_jobs=-1
    ),
    "gradient_boost": lambda: GradientBoostingRegressor(
        n_estimators=200, max_depth=4, learning_rate=0.05,
        min_samples_leaf=20, subsample=0.8, random_state=42
    ),
}


# ── Main runner ──────────────────────────────────────────────────────

def run_all_models(
    X: pd.DataFrame,
    y: pd.Series,
    n_splits: int = 5,
    feature_select_k: int = 50,
) -> list[ModelResult]:
    """
    Run all models with walk-forward validation.

    Returns sorted list of ModelResult (best Sharpe first).
    """
    logger.info("Running %d models with %d walk-forward splits", len(MODELS), n_splits)
    logger.info("Feature matrix: %d x %d", X.shape[0], X.shape[1])

    # Feature selection using mutual information (on first 70% only!)
    train_cutoff = int(len(X) * 0.7)
    X_train_sel = X.iloc[:train_cutoff]
    y_train_sel = y.iloc[:train_cutoff]

    logger.info("Computing mutual information for feature selection...")
    mi_scores = mutual_info_regression(
        X_train_sel.fillna(0).values,
        y_train_sel.values,
        random_state=42,
        n_neighbors=5,
    )
    mi_series = pd.Series(mi_scores, index=X.columns).sort_values(ascending=False)
    top_features = mi_series.head(feature_select_k).index.tolist()
    logger.info("Top %d features selected by MI. Top 10: %s", feature_select_k,
                mi_series.head(10).to_dict())

    X_selected = X[top_features]
    splits = walk_forward_split(X_selected, y, n_splits=n_splits)

    results = []
    for model_name, model_fn in MODELS.items():
        logger.info("Training %s...", model_name)

        all_y_true = []
        all_y_pred = []
        all_dates = []

        for fold_i, (train_idx, test_idx) in enumerate(splits):
            X_train = X_selected.iloc[train_idx]
            y_train = y.iloc[train_idx]
            X_test = X_selected.iloc[test_idx]
            y_test = y.iloc[test_idx]

            # Scale
            scaler = StandardScaler()
            X_train_sc = scaler.fit_transform(X_train)
            X_test_sc = scaler.transform(X_test)

            # Train
            model = model_fn()
            model.fit(X_train_sc, y_train)

            # Predict
            y_pred = model.predict(X_test_sc)

            all_y_true.extend(y_test.values)
            all_y_pred.extend(y_pred)
            all_dates.extend(y_test.index)

        all_y_true = np.array(all_y_true)
        all_y_pred = np.array(all_y_pred)

        # Compute metrics
        r2_test = r2_score(all_y_true, all_y_pred)
        rmse = np.sqrt(mean_squared_error(all_y_true, all_y_pred))
        mae = mean_absolute_error(all_y_true, all_y_pred)
        trading = compute_trading_metrics(all_y_true, all_y_pred)

        # Get feature importance from last fold's model
        importance = get_feature_importance(model, top_features)
        top_10 = [(f, round(v, 6)) for f, v in importance.head(10).items()]

        # Train metrics (last fold)
        y_train_pred = model.predict(scaler.transform(X_selected.iloc[train_idx]))
        r2_train = r2_score(y.iloc[train_idx], y_train_pred)

        result = ModelResult(
            name=model_name,
            r2_train=r2_train,
            r2_test=r2_test,
            rmse_test=rmse,
            mae_test=mae,
            sharpe_ratio=trading["sharpe"],
            win_rate=trading["win_rate"],
            profit_factor=trading["profit_factor"],
            top_features=top_10,
            predictions=pd.Series(all_y_pred, index=all_dates),
        )
        results.append(result)

        logger.info(
            "%s — R²=%.4f | Sharpe=%.2f | WinRate=%.1f%% | PF=%.2f",
            model_name, r2_test, trading["sharpe"],
            trading["win_rate"] * 100, trading["profit_factor"],
        )

    # Sort by Sharpe ratio
    results.sort(key=lambda r: r.sharpe_ratio, reverse=True)
    return results


# ── Feature category analysis ────────────────────────────────────────

def analyze_feature_categories(X: pd.DataFrame, y: pd.Series) -> pd.DataFrame:
    """
    Test each category of features ALONE to see which category matters.
    Categories: celestial, nature, market, calendar, interaction
    """
    categories = {
        "celestial_only": [c for c in X.columns if c.startswith("cel_")],
        "nature_only": [c for c in X.columns if c.startswith("nat_")],
        "market_only": [c for c in X.columns if any(
            c.startswith(f"{t}_") for t in ["nifty50", "banknifty", "gold", "silver",
                                             "crude", "usdinr", "sp500", "dxy", "us10y",
                                             "niftyit", "niftyfmcg", "indiavix",
                                             "gold_silver", "vix_nifty"])],
        "calendar_only": [c for c in X.columns if any(
            c.startswith(p) for p in ["day_", "month", "week_", "quarter", "is_",
                                       "dow_", "dom_"])],
        "interactions_only": [c for c in X.columns if c.startswith("ix_")],
        "celestial+nature": [c for c in X.columns if c.startswith(("cel_", "nat_"))],
        "all_features": list(X.columns),
    }

    results = []
    for cat_name, cols in categories.items():
        if not cols:
            continue
        logger.info("Testing category: %s (%d features)", cat_name, len(cols))

        X_cat = X[cols]
        # Use simple Ridge for speed
        train_end = int(len(X) * 0.7)
        scaler = StandardScaler()
        X_train = scaler.fit_transform(X_cat.iloc[:train_end])
        X_test = scaler.transform(X_cat.iloc[train_end:])
        y_train = y.iloc[:train_end]
        y_test = y.iloc[train_end:]

        model = Ridge(alpha=1.0)
        model.fit(X_train, y_train)
        y_pred = model.predict(X_test)

        trading = compute_trading_metrics(y_test.values, y_pred)

        results.append({
            "category": cat_name,
            "n_features": len(cols),
            "r2": r2_score(y_test, y_pred),
            "sharpe": trading["sharpe"],
            "win_rate": trading["win_rate"],
            "profit_factor": trading["profit_factor"],
            "total_return": trading["total_return"],
        })

    return pd.DataFrame(results).sort_values("sharpe", ascending=False)


# ── Ensemble ─────────────────────────────────────────────────────────

def build_ensemble(model_results: list[ModelResult], y_true: pd.Series) -> dict:
    """
    Build a simple weighted ensemble from the top models.
    Weight by Sharpe ratio.
    """
    # Only use models with positive Sharpe
    good_models = [r for r in model_results if r.sharpe_ratio > 0 and r.predictions is not None]
    if not good_models:
        logger.warning("No models with positive Sharpe ratio")
        return {}

    total_sharpe = sum(r.sharpe_ratio for r in good_models)
    if total_sharpe == 0:
        return {}

    # Weighted average prediction
    ensemble_pred = pd.Series(0.0, index=good_models[0].predictions.index)
    for r in good_models:
        weight = r.sharpe_ratio / total_sharpe
        # Align indices
        common = ensemble_pred.index.intersection(r.predictions.index)
        ensemble_pred.loc[common] += weight * r.predictions.loc[common]

    # Evaluate ensemble
    common = ensemble_pred.index.intersection(y_true.index)
    trading = compute_trading_metrics(
        y_true.loc[common].values,
        ensemble_pred.loc[common].values,
    )

    return {
        "models_used": [r.name for r in good_models],
        "weights": {r.name: r.sharpe_ratio / total_sharpe for r in good_models},
        "ensemble_sharpe": trading["sharpe"],
        "ensemble_win_rate": trading["win_rate"],
        "ensemble_profit_factor": trading["profit_factor"],
        "ensemble_total_return": trading["total_return"],
        "predictions": ensemble_pred,
    }
