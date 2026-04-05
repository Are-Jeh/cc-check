"""Mutual information analysis between indicator and market series."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.feature_selection import mutual_info_regression

MIN_OBSERVATIONS = 30
NOISE_SHUFFLES = 100
NOISE_PERCENTILE = 95


def compute_mutual_information(
    indicator: pd.Series,
    market: pd.Series,
    max_lag: int = 30,
) -> list[dict]:
    """Compute mutual information at each lag from 0 to *max_lag*.

    For each lag the indicator is shifted forward and inner-joined with the
    market series.  ``sklearn.feature_selection.mutual_info_regression`` is
    used with the indicator as the single feature (X) and market as the
    continuous target (y).

    A noise baseline is computed by shuffling the indicator 100 times,
    computing MI each time, and taking the 95th percentile.

    Returns a list of dicts with keys ``lag`` and ``mi_score``.  The final
    entry in the list carries an extra key ``baseline_threshold``.
    """
    indicator = indicator.copy()
    market = market.copy()
    indicator.index = pd.to_datetime(indicator.index)
    market.index = pd.to_datetime(market.index)

    results: list[dict] = []
    baseline_threshold: float | None = None

    for lag in range(0, max_lag + 1):
        shifted = indicator.shift(-lag, freq="D") if lag > 0 else indicator

        combined = pd.concat(
            {"indicator": shifted, "market": market}, axis=1, join="inner"
        ).dropna()

        if len(combined) < MIN_OBSERVATIONS:
            continue

        X = combined["indicator"].values.reshape(-1, 1)
        y = combined["market"].values

        mi = mutual_info_regression(X, y, random_state=42)[0]
        results.append({"lag": lag, "mi_score": float(mi)})

        # Compute noise baseline once using the lag-0 alignment (or the first
        # valid lag if lag-0 didn't have enough data).
        if baseline_threshold is None:
            rng = np.random.RandomState(42)
            noise_scores = []
            for _ in range(NOISE_SHUFFLES):
                X_shuffled = rng.permutation(X.ravel()).reshape(-1, 1)
                noise_mi = mutual_info_regression(X_shuffled, y, random_state=42)[0]
                noise_scores.append(noise_mi)
            baseline_threshold = float(np.percentile(noise_scores, NOISE_PERCENTILE))

    # Attach baseline_threshold to every entry for convenience
    for entry in results:
        entry["baseline_threshold"] = baseline_threshold

    return results
