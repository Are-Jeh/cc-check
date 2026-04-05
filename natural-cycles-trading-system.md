# Natural Cycles Trading Indicator — Technical Design Document

**Target Market:** NSE (Nifty 50 + select stocks)
**Trading Frequency:** 2–5 trades/month (swing/positional)
**Core Thesis:** Natural phenomena exhibit correlations with market behavior that, when combined into a composite signal, can identify favorable entry/exit timing.

---

## 1. System Architecture

### Component Overview

```
┌─────────────────────────────────────────────────────────────┐
│                      SIGNAL DASHBOARD                       │
│  (Streamlit app showing today's composite score + breakdown)│
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────┴──────────────────────────────────┐
│                    SIGNAL ENGINE                            │
│  Composite scorer: weighted sum of all sub-signals          │
│  Threshold logic: BUY if score > X, SELL if score < Y      │
│  Confidence level: how many sub-signals agree               │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────┴──────────────────────────────────┐
│                   FEATURE STORE (SQLite / DuckDB)           │
│  Daily table: date | lunar_phase | solar_flux | kp_index |  │
│  sunrise_min | sunset_min | mercury_long | venus_long |     │
│  nifty_close | nifty_return | volume | vix | ...            │
└──────────────────────────┬──────────────────────────────────┘
                           │
          ┌────────────────┼────────────────┐
          │                │                │
┌─────────┴──┐  ┌─────────┴──┐  ┌──────────┴─────────┐
│ ASTRO DATA │  │ MARKET DATA│  │ GEOMAGNETIC / SOLAR│
│  COLLECTOR │  │  COLLECTOR │  │     COLLECTOR      │
│  (ephem /  │  │ (yfinance /│  │  (NOAA APIs /      │
│  skyfield) │  │  Kite API) │  │   SpaceWeather)    │
└────────────┘  └────────────┘  └────────────────────┘
```

### Data Pipeline — Collection Details

#### A. Astronomical Data (computed locally, no API needed)

Source: `skyfield` library (preferred over `ephem` — more accurate, actively maintained).

Computed daily:
- **Lunar phase angle**: 0–360 degrees (continuous). 0 = new moon, 180 = full moon.
- **Lunar declination**: moon's position relative to celestial equator.
- **Planetary longitudes**: Sun, Mercury, Venus, Mars, Jupiter, Saturn ecliptic longitude in degrees.
- **Planetary aspects**: angular separation between planet pairs (conjunction=0, opposition=180, square=90, trine=120). Record the closest major aspect and its orb (deviation from exact).
- **Sunrise/sunset times**: for Mumbai (19.0760 N, 72.8777 E) — NSE's location.
- **Day length**: sunset minus sunrise in minutes.
- **Lunar distance**: Earth-Moon distance in km (perigee vs apogee).

```python
# Core computation — runs once per day, ~200ms
from skyfield.api import load, Topos
from skyfield.almanac import moon_phase

ts = load.timescale()
eph = load('de421.bsp')  # JPL ephemeris, download once (17MB)
mumbai = Topos('19.0760 N', '72.8777 E')

t = ts.utc(2026, 3, 15)
phase_angle = moon_phase(eph, t).degrees  # 0-360 continuous
```

#### B. Solar & Geomagnetic Data (free APIs)

| Data Point | Source | URL | Update Freq |
|---|---|---|---|
| F10.7 solar flux | NOAA SWPC | `services.swpc.noaa.gov/json/solar-cycle/` | Daily |
| Kp index (geomagnetic) | GFZ Potsdam | `kp.gfz-potsdam.de/app/json/` | 3-hourly |
| Sunspot number | SILSO (Royal Observatory Belgium) | `sidc.be/silso/DATA/SN_d_tot_V2.0.csv` | Daily |
| Solar wind speed | NOAA DSCOVR | `services.swpc.noaa.gov/products/solar-wind/` | Real-time |

```python
# Example: Kp index fetch
import requests

def get_kp_index():
    url = "https://kp.gfz-potsdam.de/app/json/?start=2026-03-14&end=2026-03-15"
    resp = requests.get(url)
    data = resp.json()
    # Average the 3-hourly values into a daily Kp
    daily_kp = sum(d['Kp'] for d in data) / len(data)
    return daily_kp
```

#### C. Market Data

| Data Point | Source | Notes |
|---|---|---|
| Nifty 50 OHLCV (historical) | `yfinance` ticker `^NSEI` | Free, reliable, 20+ years |
| Individual stock OHLCV | `yfinance` | Use `.NS` suffix (e.g., `RELIANCE.NS`) |
| India VIX | `yfinance` ticker `^INDIAVIX` | Fear gauge |
| Real-time quotes | Zerodha Kite Connect | Rs 2000/month API plan |
| FII/DII flows | NSE website scraping | `nsetools` or direct CSV downloads |

### Storage

Use **DuckDB** (single file, SQL interface, fast analytical queries, zero config):

```python
import duckdb

con = duckdb.connect('natural_cycles.duckdb')
con.execute("""
    CREATE TABLE IF NOT EXISTS daily_features (
        date DATE PRIMARY KEY,
        -- Astronomical
        lunar_phase_deg FLOAT,      -- 0-360
        lunar_distance_km FLOAT,
        day_length_min FLOAT,
        sunrise_minutes_from_midnight FLOAT,
        sunset_minutes_from_midnight FLOAT,
        sun_longitude FLOAT,
        mercury_longitude FLOAT,
        venus_longitude FLOAT,
        mars_longitude FLOAT,
        jupiter_longitude FLOAT,
        saturn_longitude FLOAT,
        -- Solar/Geomagnetic
        solar_flux_f107 FLOAT,
        kp_index FLOAT,
        sunspot_number FLOAT,
        -- Market
        nifty_open FLOAT,
        nifty_high FLOAT,
        nifty_low FLOAT,
        nifty_close FLOAT,
        nifty_volume BIGINT,
        india_vix FLOAT,
        nifty_return_pct FLOAT,     -- daily % change
        nifty_return_5d FLOAT,      -- 5-day forward return (for labeling)
        nifty_return_10d FLOAT      -- 10-day forward return
    )
""")
```

Why DuckDB over SQLite: columnar storage is 5–10x faster for the analytical queries you will run constantly (correlations across columns, rolling windows, aggregations by lunar phase bucket).

---

## 2. Feature Engineering

### 2.1 Lunar Phase — Continuous Circular Encoding

The lunar phase is an angle (0–360). You cannot use the raw number because 359 degrees is close to 1 degree, but numerically they look far apart. Use **sine/cosine encoding**:

```python
import numpy as np

def encode_lunar_phase(phase_degrees):
    """Convert lunar phase angle to two features."""
    rad = np.radians(phase_degrees)
    return {
        'lunar_sin': np.sin(rad),   # ranges -1 to 1
        'lunar_cos': np.cos(rad),   # ranges -1 to 1
    }
    # New moon (0°):   sin=0,  cos=1
    # First quarter (90°): sin=1, cos=0
    # Full moon (180°): sin=0, cos=-1
    # Last quarter (270°): sin=-1, cos=0
```

This preserves the circular nature: nearby phases have nearby feature values.

### 2.2 Time-of-Day Encoding (for intraday session analysis)

Even for daily signals, encoding WHEN during the day the market tends to move matters:

```python
def encode_time_of_day(hour, minute):
    """Circular encoding of 24-hour time."""
    total_minutes = hour * 60 + minute
    fraction = total_minutes / (24 * 60)
    return {
        'time_sin': np.sin(2 * np.pi * fraction),
        'time_cos': np.cos(2 * np.pi * fraction),
    }
```

For daily-level analysis, encode the **market open relative to sunrise**:

```python
def market_sunrise_offset(sunrise_minutes):
    """Minutes between sunrise and market open (9:15 AM IST = 555 min)."""
    return 555 - sunrise_minutes  # positive = sun rose before market
```

### 2.3 Sunrise/Sunset Features

```python
def sun_features(sunrise_minutes, sunset_minutes):
    """Derive trading-relevant features from sun times."""
    day_length = sunset_minutes - sunrise_minutes
    # How much daylight remains after market close (15:30 = 930 min)
    daylight_after_close = sunset_minutes - 930
    # Encode day length change (derivative) — requires yesterday's value
    return {
        'day_length_min': day_length,
        'daylight_after_close': daylight_after_close,
        'market_in_daylight_pct': (930 - 555) / day_length,  # fraction of trading hours in daylight
    }
```

### 2.4 Planetary Aspect Features

```python
def compute_aspects(longitudes_dict):
    """
    Given {'sun': 355.2, 'mercury': 12.1, 'venus': 88.3, ...}
    compute all pairwise angular separations.
    """
    planets = list(longitudes_dict.keys())
    aspects = {}
    major_aspects = {0: 'conjunction', 60: 'sextile', 90: 'square',
                     120: 'trine', 180: 'opposition'}
    orb_tolerance = 8  # degrees

    for i, p1 in enumerate(planets):
        for p2 in planets[i+1:]:
            sep = abs(longitudes_dict[p1] - longitudes_dict[p2]) % 360
            if sep > 180:
                sep = 360 - sep
            # Check proximity to major aspects
            for angle, name in major_aspects.items():
                orb = abs(sep - angle)
                if orb <= orb_tolerance:
                    key = f"{p1}_{p2}_{name}"
                    aspects[key] = 1.0 - (orb / orb_tolerance)  # 1.0 = exact, 0.0 = at tolerance edge
    return aspects
```

### 2.5 Interaction Features

These capture non-linear combinations:

```python
def interaction_features(row):
    """Combine natural signals with market context."""
    return {
        # Full moon + high VIX = potential reversal?
        'fullmoon_highvix': row['lunar_cos_neg'] * (row['india_vix'] > 20),

        # New moon + low volume = accumulation?
        'newmoon_lowvol': row['lunar_cos_pos'] * (row['volume_zscore'] < -1),

        # High Kp + negative market = potential bounce?
        'geomag_storm_down': (row['kp_index'] > 5) * (row['nifty_return_pct'] < -1),

        # Day length increasing + positive trend
        'daylight_up_trend_up': (row['day_length_change'] > 0) * (row['nifty_sma20_above']),
    }
```

### 2.6 Lag Features

Critical: natural phenomena on day T may affect markets on day T+1, T+2, etc.

```python
def create_lag_features(df, feature_cols, lags=[1, 2, 3, 5]):
    """
    For each natural feature, create lagged versions.
    Example: kp_index_lag2 = kp_index from 2 days ago
    """
    for col in feature_cols:
        for lag in lags:
            df[f'{col}_lag{lag}'] = df[col].shift(lag)
    return df

# Also create FORWARD returns for labeling (target variable)
# IMPORTANT: these are only used during training, never as features
def create_forward_returns(df):
    df['fwd_return_1d'] = df['nifty_close'].pct_change(1).shift(-1)
    df['fwd_return_5d'] = df['nifty_close'].pct_change(5).shift(-5)
    df['fwd_return_10d'] = df['nifty_close'].pct_change(10).shift(-10)
    return df
```

### Complete Feature Vector (per day)

| Category | Features | Count |
|---|---|---|
| Lunar (sin/cos encoded) | phase_sin, phase_cos, distance, distance_change | 4 |
| Solar/Geo | f10.7, kp_index, sunspot_number | 3 |
| Sun timing | day_length, day_length_change, sunrise_offset | 3 |
| Planetary longitudes (sin/cos each) | sun, mercury, venus, mars, jupiter, saturn | 12 |
| Planetary aspects (top 5 most active) | nearest_aspect_strength, aspect_count | ~5 |
| Market context | return_1d, return_5d, sma20_diff, vix, volume_zscore | 5 |
| Lag features (3 lags x ~10 natural features) | various | ~30 |
| Interactions | ~5 hand-crafted | 5 |
| **Total** | | **~67** |

---

## 3. Model Options

### Option A: Weighted Composite Score (No ML)

The simplest approach. Compute a daily score from -100 to +100.

```python
class CompositeScorer:
    """
    Each sub-signal returns a value from -1 (strong sell) to +1 (strong buy).
    The composite is a weighted sum, scaled to -100..+100.
    """

    def __init__(self):
        # Weights determined by historical correlation strength
        # Start equal, then adjust based on backtest
        self.weights = {
            'lunar_signal': 0.20,
            'solar_signal': 0.15,
            'geomagnetic_signal': 0.15,
            'daylight_signal': 0.10,
            'planetary_signal': 0.15,
            'time_of_month_signal': 0.10,
            'vix_regime_signal': 0.15,
        }

    def lunar_signal(self, phase_deg, distance_km):
        """
        Historical tendency: markets slightly bullish around new moon,
        slightly bearish around full moon (Dichev & Janes 2003 found this
        across 25 countries over 100 years — small but nonzero effect).
        """
        # Continuous: +1 at new moon (0°), -1 at full moon (180°)
        signal = np.cos(np.radians(phase_deg))

        # Modulate by lunar distance (supermoon = closer = stronger effect?)
        avg_distance = 384400  # km
        distance_factor = avg_distance / distance_km  # >1 when closer
        signal *= min(distance_factor, 1.1)  # cap the amplification

        return np.clip(signal, -1, 1)

    def geomagnetic_signal(self, kp_index):
        """
        Krivelyova & Robotti (2003): geomagnetic storms (high Kp)
        correlate with lower stock returns in following days.
        High Kp = bearish signal for next 1-3 days.
        """
        if kp_index >= 6:
            return -0.8  # storm
        elif kp_index >= 4:
            return -0.3  # unsettled
        elif kp_index <= 1:
            return 0.3   # very quiet
        else:
            return 0.0   # neutral

    def compute(self, features):
        signals = {
            'lunar_signal': self.lunar_signal(features['lunar_phase_deg'],
                                               features['lunar_distance_km']),
            'geomagnetic_signal': self.geomagnetic_signal(features['kp_index']),
            # ... other sub-signals
        }

        score = sum(self.weights[k] * signals[k] for k in self.weights)
        score_scaled = score * 100  # -100 to +100

        agreement = sum(1 for v in signals.values() if v > 0.2) - \
                    sum(1 for v in signals.values() if v < -0.2)

        return {
            'composite_score': score_scaled,
            'signal_agreement': agreement,  # how many sub-signals agree
            'breakdown': signals,
            'action': 'BUY' if score_scaled > 30 else ('SELL' if score_scaled < -30 else 'HOLD')
        }
```

### Option B: Logistic Regression

```python
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

# Target: 1 if 5-day forward return > 0, else 0
y = (df['fwd_return_5d'] > 0).astype(int)
X = df[feature_columns]

scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)

model = LogisticRegression(C=0.1, penalty='l1', solver='saga')
# L1 penalty forces sparsity — irrelevant features get zero weight
# This tells you which natural features actually matter
model.fit(X_scaled, y)

# Inspect which features survived L1 regularization
important = [(name, coef) for name, coef in zip(feature_columns, model.coef_[0])
             if abs(coef) > 0.01]
```

### Option C: XGBoost

```python
import xgboost as xgb

# Target: classify next 5 trading days as UP (>1%), DOWN (<-1%), or FLAT
def classify_return(r):
    if r > 0.01: return 2   # up
    elif r < -0.01: return 0  # down
    else: return 1            # flat

y = df['fwd_return_5d'].apply(classify_return)

model = xgb.XGBClassifier(
    n_estimators=200,
    max_depth=4,           # shallow trees — avoid overfitting
    learning_rate=0.05,
    subsample=0.8,
    colsample_bytree=0.7,  # use only 70% of features per tree
    reg_alpha=1.0,          # L1 regularization
    reg_lambda=1.0,         # L2 regularization
)
```

### Option D: Bayesian Approach

```python
import pymc as pm

with pm.Model() as lunar_model:
    # Prior: lunar effect is probably very small
    lunar_effect = pm.Normal('lunar_effect', mu=0, sigma=0.005)
    # Prior: geomagnetic effect is probably very small
    geo_effect = pm.Normal('geo_effect', mu=0, sigma=0.005)

    # Expected return = baseline + effects
    baseline = pm.Normal('baseline', mu=0.0005, sigma=0.001)  # ~0.05% daily
    mu = baseline + lunar_effect * lunar_features + geo_effect * geo_features

    # Market returns are fat-tailed
    volatility = pm.HalfNormal('volatility', sigma=0.02)
    nu = pm.Exponential('nu', 1/30)  # degrees of freedom for Student-t

    returns = pm.StudentT('returns', nu=nu, mu=mu, sigma=volatility,
                          observed=observed_returns)

    trace = pm.sample(2000, tune=1000)

# Now you get posterior distributions:
# P(lunar_effect > 0) tells you confidence that the effect exists
# The width of the posterior tells you how uncertain you are
```

### Recommendation: Start with Option A, validate with Option B

**Why Option A first:**
- Transparent: you see exactly why a signal fired.
- No overfitting risk: the rules are explicit, not learned from data.
- Fast to iterate: change a weight, re-run backtest, see results in seconds.
- You can run it for weeks in paper-trading mode immediately.

**Why Option B second:**
- L1 logistic regression will tell you which features have ANY predictive power at all.
- If the L1 model zeroes out all natural features, the whole thesis is questionable — and you know early before wasting more time.
- It gives a proper probability output: P(market up) = 0.63, which is useful for position sizing.

**Skip C and D initially.** XGBoost will overfit on 67 features with only ~5000 training samples (20 years of daily data). Bayesian is the most intellectually honest but requires more setup. Move to these only after A and B show some evidence of signal.

---

## 4. Backtesting Framework

### 4.1 Walk-Forward Validation (the only valid approach)

**Never** fit on the full dataset and then test on the same data. Use expanding or rolling window:

```python
class WalkForwardBacktest:
    """
    Walk-forward: train on data up to time T, predict T+1 to T+N,
    then expand training window and repeat.
    """

    def __init__(self, df, min_train_days=750, test_window=63):
        """
        min_train_days: 3 years minimum before first prediction
        test_window: predict 63 trading days (~3 months) at a time
        """
        self.df = df
        self.min_train_days = min_train_days
        self.test_window = test_window

    def run(self, model_factory, feature_cols, target_col):
        results = []
        n = len(self.df)

        for start_test in range(self.min_train_days, n - self.test_window, self.test_window):
            end_test = min(start_test + self.test_window, n)

            train = self.df.iloc[:start_test]
            test = self.df.iloc[start_test:end_test]

            # Fit model ONLY on training data
            model = model_factory()
            model.fit(train[feature_cols], train[target_col])

            # Predict on test data
            preds = model.predict(test[feature_cols])

            for i, (idx, row) in enumerate(test.iterrows()):
                results.append({
                    'date': row['date'],
                    'prediction': preds[i],
                    'actual_return': row['fwd_return_5d'],
                    'fold': start_test,  # which fold this came from
                })

        return pd.DataFrame(results)
```

### 4.2 Avoiding Lookahead Bias — Checklist

| Trap | How to Avoid |
|---|---|
| Using future returns as features | Forward returns are ONLY targets, never in X |
| Calculating indicators on full dataset | Compute rolling indicators inside training loop |
| Using data announced after market close for same-day signal | Kp index at 3PM IST uses only values published before 9AM IST |
| Optimizing weights on full history | Walk-forward: only optimize on past data |
| Survivorship bias in stock selection | Use Nifty 50 index first (no survivorship issue) |
| Selecting the model that "worked best" on test data | Pre-register your hypothesis before looking at results |

### 4.3 Benchmarks

| Benchmark | Description |
|---|---|
| Buy-and-hold Nifty 50 | Baseline. If you can't beat this risk-adjusted, stop. |
| Random entry/exit | Same number of trades, random timing. Run 1000 simulations. Your strategy must beat the 95th percentile of random. |
| Monthly SIP equivalent | Invest same total amount via monthly SIP. |

### 4.4 Performance Metrics

```python
def compute_metrics(returns_series, risk_free_rate=0.065):
    """
    returns_series: daily returns of the strategy
    risk_free_rate: annualized (use India 10Y govt bond ~6.5%)
    """
    daily_rf = (1 + risk_free_rate) ** (1/252) - 1
    excess = returns_series - daily_rf

    sharpe = np.sqrt(252) * excess.mean() / excess.std()

    cumulative = (1 + returns_series).cumprod()
    rolling_max = cumulative.expanding().max()
    drawdown = (cumulative - rolling_max) / rolling_max
    max_drawdown = drawdown.min()

    # Win rate (only on days when a trade is active)
    trade_returns = returns_series[returns_series != 0]
    win_rate = (trade_returns > 0).mean()

    # Profit factor = gross profits / gross losses
    gross_profit = trade_returns[trade_returns > 0].sum()
    gross_loss = abs(trade_returns[trade_returns < 0].sum())
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

    # CAGR
    total_days = len(returns_series)
    total_return = cumulative.iloc[-1] - 1
    cagr = (1 + total_return) ** (252 / total_days) - 1

    return {
        'sharpe_ratio': sharpe,         # want > 1.0
        'max_drawdown': max_drawdown,   # want > -15%
        'win_rate': win_rate,           # want > 55%
        'profit_factor': profit_factor, # want > 1.5
        'cagr': cagr,
        'total_trades': len(trade_returns),
        'avg_trade_return': trade_returns.mean(),
    }
```

### Minimum Acceptable Performance

To conclude "this works," the strategy must:
1. Sharpe ratio > 0.8 (after transaction costs of 0.1% per trade round-trip for Zerodha).
2. Outperform buy-and-hold Nifty on risk-adjusted basis over at least 3 different walk-forward folds.
3. Beat 95th percentile of 1000 random-timing simulations.

If it doesn't meet all three, the natural cycles hypothesis is not tradeable.

---

## 5. Risk Management

### 5.1 Position Sizing

```python
class PositionSizer:
    def __init__(self, total_capital, max_risk_per_trade=0.02, max_portfolio_risk=0.06):
        """
        max_risk_per_trade: never risk more than 2% of capital on one trade
        max_portfolio_risk: never have more than 6% total at risk
        """
        self.capital = total_capital
        self.max_risk_per_trade = max_risk_per_trade
        self.max_portfolio_risk = max_portfolio_risk

    def calculate_position(self, signal_score, signal_agreement, entry_price, stop_loss_price):
        """
        signal_score: -100 to +100 from composite scorer
        signal_agreement: how many sub-signals agree (0 to 7)
        """
        # Base risk: 2% of capital
        base_risk = self.capital * self.max_risk_per_trade

        # Confidence multiplier based on signal strength and agreement
        confidence = self._confidence_multiplier(signal_score, signal_agreement)

        # Actual risk amount
        risk_amount = base_risk * confidence

        # Position size from stop-loss distance
        stop_distance_pct = abs(entry_price - stop_loss_price) / entry_price
        position_value = risk_amount / stop_distance_pct

        # Cap at 25% of capital in any single position
        max_position = self.capital * 0.25
        position_value = min(position_value, max_position)

        shares = int(position_value / entry_price)

        return {
            'shares': shares,
            'position_value': shares * entry_price,
            'risk_amount': shares * abs(entry_price - stop_loss_price),
            'confidence': confidence,
        }

    def _confidence_multiplier(self, score, agreement):
        """
        Scale position based on conviction level.
        """
        abs_score = abs(score)

        if abs_score >= 60 and agreement >= 5:
            return 1.0    # full size — strong signal, high agreement
        elif abs_score >= 40 and agreement >= 3:
            return 0.6    # moderate conviction
        elif abs_score >= 30:
            return 0.3    # minimum size — just above threshold
        else:
            return 0.0    # no trade
```

### 5.2 Risk Rules (Hard-Coded, Non-Negotiable)

```python
RISK_RULES = {
    'max_risk_per_trade_pct': 2.0,       # never risk > 2% on any trade
    'max_open_positions': 3,              # max 3 concurrent positions
    'max_portfolio_risk_pct': 6.0,        # total risk across all positions
    'max_correlation_overlap': 2,          # max 2 positions in same sector
    'stop_loss_mandatory': True,           # every trade MUST have a stop
    'max_holding_days': 30,                # exit after 30 days regardless
    'min_signal_agreement': 3,             # need at least 3/7 sub-signals aligned
    'no_trade_around_events': ['budget', 'rbi_policy', 'election_results'],
    'no_trade_30min_after_open': True,     # avoid opening volatility
}
```

### 5.3 Signal Agreement Matrix

| Signals Agreeing | Confidence | Position Size | Action |
|---|---|---|---|
| 6-7 of 7 | Very High | 100% of base | Enter immediately at market |
| 4-5 of 7 | High | 60% of base | Enter with limit order |
| 3 of 7 | Moderate | 30% of base | Enter only if price confirms |
| 0-2 of 7 | Low | 0% | No trade |

---

## 6. Technology Stack

### Core Libraries

```
# requirements.txt
# Data & Computation
pandas==2.2.0
numpy==1.26.0
duckdb==0.10.0
scipy==1.12.0

# Astronomy
skyfield==1.48           # celestial mechanics (preferred)
ephem==4.1.5             # backup / validation
astropy==6.0.0           # coordinate transforms if needed

# Machine Learning
scikit-learn==1.4.0
xgboost==2.0.3
# pymc==5.10.0           # only if doing Bayesian (Option D)

# Backtesting
backtrader==1.9.78       # or use custom loop above
# zipline-reloaded==3.0  # alternative, heavier

# Market Data
yfinance==0.2.36
# nsetools==1.0.11       # NSE-specific data (optional)

# Broker Integration
kiteconnect==5.0.0       # Zerodha API

# Visualization & Dashboard
streamlit==1.31.0
plotly==5.18.0
matplotlib==3.8.0

# Scheduling
apscheduler==3.10.4

# HTTP
requests==2.31.0
```

### Project Structure

```
natural-cycles-trading/
├── config.yaml                  # API keys, thresholds, weights
├── requirements.txt
├── data/
│   ├── de421.bsp               # JPL ephemeris (downloaded once)
│   └── natural_cycles.duckdb   # all historical data
├── collectors/
│   ├── astro_collector.py      # skyfield-based calculations
│   ├── solar_collector.py      # NOAA API fetchers
│   └── market_collector.py     # yfinance + Kite wrapper
├── features/
│   ├── encoders.py             # sin/cos encoding, circular features
│   ├── interactions.py         # interaction & lag features
│   └── feature_pipeline.py     # orchestrates all feature creation
├── models/
│   ├── composite_scorer.py     # Option A: weighted scoring
│   ├── logistic_model.py       # Option B: sklearn logistic
│   └── xgboost_model.py       # Option C: XGBoost
├── backtest/
│   ├── walk_forward.py         # walk-forward engine
│   ├── metrics.py              # sharpe, drawdown, etc.
│   └── random_baseline.py      # random entry/exit simulator
├── risk/
│   ├── position_sizer.py       # position sizing logic
│   └── risk_rules.py           # hard-coded risk rules
├── trading/
│   ├── signal_generator.py     # daily signal computation
│   ├── order_manager.py        # Zerodha Kite integration
│   └── portfolio_tracker.py    # track open positions
├── dashboard/
│   └── app.py                  # Streamlit dashboard
├── scripts/
│   ├── backfill_history.py     # one-time: build historical DB
│   ├── daily_update.py         # cron: fetch today's data + signal
│   └── run_backtest.py         # run full walk-forward backtest
└── notebooks/
    ├── 01_eda_lunar_returns.ipynb    # explore lunar-market correlation
    ├── 02_eda_geomagnetic.ipynb      # explore Kp-market correlation
    └── 03_full_backtest.ipynb        # interactive backtest analysis
```

### Broker Integration (Zerodha Kite)

```python
from kiteconnect import KiteConnect

class ZerodhaTrader:
    def __init__(self, api_key, access_token):
        self.kite = KiteConnect(api_key=api_key)
        self.kite.set_access_token(access_token)

    def place_signal_order(self, signal, instrument, position_size):
        """Place order based on composite signal."""
        if signal['action'] == 'BUY':
            order_id = self.kite.place_order(
                variety=self.kite.VARIETY_REGULAR,
                exchange=self.kite.EXCHANGE_NSE,
                tradingsymbol=instrument,
                transaction_type=self.kite.TRANSACTION_TYPE_BUY,
                quantity=position_size['shares'],
                product=self.kite.PRODUCT_CNC,   # delivery (not intraday)
                order_type=self.kite.ORDER_TYPE_LIMIT,
                price=position_size['entry_price'],
                validity=self.kite.VALIDITY_DAY,
            )
            return order_id

    def get_token(self):
        """
        Kite requires daily re-authentication via browser login.
        Flow: redirect user to login URL -> get request_token -> exchange for access_token.
        Automate with selenium or use Kite's totp-based login.
        """
        login_url = self.kite.login_url()
        print(f"Login here: {login_url}")
        request_token = input("Enter request_token from redirect URL: ")
        data = self.kite.generate_session(request_token, api_secret="your_secret")
        return data['access_token']
```

### Daily Cron Job

```python
# scripts/daily_update.py — run via cron at 8:30 AM IST (before market open)
"""
30 8 * * 1-5 /usr/bin/python3 /path/to/scripts/daily_update.py
"""

from collectors.astro_collector import compute_today_astro
from collectors.solar_collector import fetch_solar_data
from collectors.market_collector import fetch_yesterday_market
from features.feature_pipeline import build_features
from models.composite_scorer import CompositeScorer

def main():
    # 1. Collect today's astronomical data (computed instantly)
    astro = compute_today_astro()

    # 2. Fetch latest solar/geomagnetic data
    solar = fetch_solar_data()

    # 3. Fetch yesterday's market close
    market = fetch_yesterday_market()

    # 4. Build feature vector
    features = build_features(astro, solar, market)

    # 5. Compute signal
    scorer = CompositeScorer()
    signal = scorer.compute(features)

    # 6. Log and notify
    print(f"Date: {features['date']}")
    print(f"Composite Score: {signal['composite_score']:.1f}")
    print(f"Action: {signal['action']}")
    print(f"Agreement: {signal['signal_agreement']}/7")
    print(f"Breakdown: {signal['breakdown']}")

    # 7. Send Telegram/email notification if signal is actionable
    if signal['action'] != 'HOLD':
        send_notification(signal)

if __name__ == '__main__':
    main()
```

---

## 7. MVP Specification

### The Absolute Minimum Viable Test

**Goal:** Determine in 1 week of work whether ANY natural cycle feature has a statistically significant correlation with Nifty 50 returns.

#### Step 1: Build the historical dataset (Day 1-2)

```python
# scripts/backfill_history.py
import yfinance as yf
from skyfield.api import load, Topos
from skyfield.almanac import moon_phase
import pandas as pd
import numpy as np

# 1. Get 20 years of Nifty daily data
nifty = yf.download('^NSEI', start='2005-01-01', end='2026-03-15')
nifty['return_1d'] = nifty['Close'].pct_change()
nifty['return_5d'] = nifty['Close'].pct_change(5).shift(-5)
nifty['return_10d'] = nifty['Close'].pct_change(10).shift(-10)

# 2. Compute lunar phase for every day
ts = load.timescale()
eph = load('de421.bsp')

dates = pd.date_range('2005-01-01', '2026-03-15')
lunar_data = []
for d in dates:
    t = ts.utc(d.year, d.month, d.day)
    phase = moon_phase(eph, t).degrees
    lunar_data.append({'date': d, 'lunar_phase_deg': phase,
                       'lunar_sin': np.sin(np.radians(phase)),
                       'lunar_cos': np.cos(np.radians(phase))})

lunar_df = pd.DataFrame(lunar_data)

# 3. Merge on date
df = nifty.merge(lunar_df, left_index=True, right_on='date')

# 4. Save
df.to_parquet('data/nifty_lunar_20yr.parquet')
```

Data requirement: **Minimum 10 years** (roughly 130 lunar cycles). 20 years is better. Nifty data goes back to 1999 on yfinance.

#### Step 2: Run the first correlation test (Day 2-3)

```python
# notebooks/01_eda_lunar_returns.ipynb

import pandas as pd
import numpy as np
from scipy import stats

df = pd.read_parquet('data/nifty_lunar_20yr.parquet')

# ---- TEST 1: Returns by lunar phase bucket ----
df['lunar_bucket'] = pd.cut(df['lunar_phase_deg'],
                            bins=[0, 45, 90, 135, 180, 225, 270, 315, 360],
                            labels=['New', 'Wax-Cres', 'First-Q', 'Wax-Gib',
                                    'Full', 'Wan-Gib', 'Last-Q', 'Wan-Cres'])

bucket_returns = df.groupby('lunar_bucket')['return_5d'].agg(['mean', 'std', 'count'])
print(bucket_returns)
# If the means differ meaningfully (e.g., new moon bucket has higher
# mean return than full moon bucket), there may be a signal.

# ---- TEST 2: Statistical significance ----
new_moon_returns = df[df['lunar_phase_deg'] < 45]['return_5d'].dropna()
full_moon_returns = df[(df['lunar_phase_deg'] > 135) &
                       (df['lunar_phase_deg'] < 225)]['return_5d'].dropna()

t_stat, p_value = stats.ttest_ind(new_moon_returns, full_moon_returns)
print(f"T-stat: {t_stat:.3f}, P-value: {p_value:.4f}")
# p < 0.05 = statistically significant difference

# ---- TEST 3: Continuous correlation ----
corr, p = stats.pearsonr(df['lunar_cos'].dropna(), df['return_5d'].dropna())
print(f"Lunar cos vs 5d return: r={corr:.4f}, p={p:.4f}")

# ---- TEST 4: Visual inspection ----
import matplotlib.pyplot as plt

fig, ax = plt.subplots(figsize=(10, 5))
df.groupby(df['lunar_phase_deg'].round(-1))['return_5d'].mean().plot(ax=ax)
ax.set_xlabel('Lunar Phase (degrees)')
ax.set_ylabel('Mean 5-day Return')
ax.set_title('Nifty 50: Average 5-Day Return by Lunar Phase (2005-2026)')
ax.axhline(y=0, color='gray', linestyle='--')
plt.savefig('output/lunar_return_curve.png', dpi=150)
```

#### Step 3: Expand to other features if Step 2 shows signal (Day 3-5)

Add Kp index and solar flux to the dataset (historical data available from NOAA/GFZ going back decades). Repeat correlation analysis.

#### Step 4: Simple backtest of composite score (Day 5-7)

```python
# Minimal backtest: Option A composite scorer
# Trade rule: BUY when score > 30, SELL when score < -30 or after 10 days

trades = []
position = None

for i, row in df.iterrows():
    score = compute_composite_score(row)  # using only features known at time i

    if position is None and score > 30:
        position = {'entry_date': row['date'], 'entry_price': row['Close'],
                     'score': score}
    elif position is not None:
        days_held = (row['date'] - position['entry_date']).days
        if score < -30 or days_held >= 10:
            ret = (row['Close'] - position['entry_price']) / position['entry_price']
            trades.append({**position, 'exit_date': row['date'],
                           'exit_price': row['Close'], 'return': ret})
            position = None

trades_df = pd.DataFrame(trades)
print(f"Total trades: {len(trades_df)}")
print(f"Win rate: {(trades_df['return'] > 0).mean():.1%}")
print(f"Avg return per trade: {trades_df['return'].mean():.2%}")
print(f"Avg return (wins): {trades_df[trades_df['return']>0]['return'].mean():.2%}")
print(f"Avg return (losses): {trades_df[trades_df['return']<0]['return'].mean():.2%}")
```

### MVP Success Criteria

After 1 week, you should have answers to:

| Question | What "success" looks like |
|---|---|
| Does lunar phase correlate with Nifty 5-day returns? | p-value < 0.05 in t-test, or visible pattern in phase-return chart |
| Does Kp index correlate with next-day returns? | Negative correlation with p < 0.05 |
| Does the composite scorer backtest beat buy-and-hold? | Sharpe > 0.8, win rate > 55% |
| Is the effect robust across time periods? | Works in 2005-2015 AND 2015-2025, not just one era |

**If none of these pass:** the natural cycles hypothesis is not tradeable for Indian markets. This is a valid and useful finding. Do not proceed to building the full system.

**If some pass:** proceed to walk-forward validation, add more features, and paper-trade for 3 months before risking real capital.

---

## Appendix A: Academic References

These are real published papers that found small but statistically significant effects:

1. **Dichev & Janes (2003)** — "Lunar cycle effects in stock returns." *Journal of Private Equity*. Found returns are lower around full moon across 25 stock markets over 100 years.
2. **Krivelyova & Robotti (2003)** — "Playing the field: Geomagnetic storms and the stock market." *Federal Reserve Bank of Atlanta Working Paper*. Geomagnetic storms predict lower returns 1-3 days later.
3. **Kamstra, Kramer & Levi (2003)** — "Winter Blues: A SAD Stock Market Cycle." *American Economic Review*. Seasonal daylight changes affect investor mood and returns.
4. **Yuan, Zheng & Zhu (2006)** — "Are investors moonstruck? Lunar cycle and stock returns." *Journal of Empirical Finance*. Confirmed lunar cycle effect across 48 countries.

**Important caveat:** These effects are small (2-5 basis points per day), may have weakened since publication due to traders acting on them, and are not guaranteed to persist. That is why backtesting with walk-forward validation and rigorous benchmarking is essential before trading real money.

---

## Appendix B: Quick Start Commands

```bash
# Setup
mkdir natural-cycles-trading && cd natural-cycles-trading
python3 -m venv venv && source venv/bin/activate
pip install pandas numpy duckdb skyfield yfinance scipy matplotlib streamlit

# Download ephemeris (one-time, 17MB)
python3 -c "from skyfield.api import load; load('de421.bsp')"

# Run MVP data collection
python3 scripts/backfill_history.py

# Launch EDA notebook
jupyter notebook notebooks/01_eda_lunar_returns.ipynb

# Run backtest
python3 scripts/run_backtest.py

# Launch dashboard
streamlit run dashboard/app.py
```
