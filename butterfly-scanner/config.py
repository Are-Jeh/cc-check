"""Configuration for Butterfly Effect Correlation Scanner."""

from pathlib import Path
from datetime import date
import os

# Project paths
BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "butterfly.db"
CACHE_DIR = BASE_DIR / "cache"
CACHE_DIR.mkdir(exist_ok=True)

# Date range
START_DATE = date(2020, 1, 1)
END_DATE = date(2025, 12, 31)

# Cache TTL in seconds (24h)
CACHE_TTL = 86400

# API keys (env vars)
OPENWEATHERMAP_KEY = os.getenv("OPENWEATHERMAP_KEY", "")
OPENAQ_KEY = os.getenv("OPENAQ_KEY", "")

# Market tickers
INDIA_TICKERS = {
    "NIFTY50": "^NSEI",
    "BANKNIFTY": "^NSEBANK",
    "NIFTYIT": "^CNXIT",
    "NIFTYFMCG": "^CNXFMCG",
    "INDIAVIX": "^INDIAVIX",
}

US_TICKERS = {
    "SP500": "^GSPC",
    "DXY": "DX-Y.NYB",
    "CRUDE": "CL=F",
    "GOLD": "GC=F",
    "US10Y": "^TNX",
}

# Google Trends keywords
GTRENDS_KEYWORDS = [
    "stock market crash",
    "mutual fund SIP",
    "gold price",
    "recession India",
    "Nifty",
    "layoffs India",
    "EMI calculator",
    "IPO allotment",
]

# Wikipedia pages
WIKI_PAGES = [
    "Stock_market_crash",
    "Recession",
    "NIFTY_50",
]

# Locations
MUMBAI = {"lat": 19.0760, "lon": 72.8777}
DELHI = {"lat": 28.6139, "lon": 77.2090}

# Analysis parameters
MAX_LAG_DAYS = 30
SIGNIFICANCE_LEVEL = 0.05
GRANGER_MAX_LAG = 30
MI_NOISE_THRESHOLD = 0.02

# Regime detection
REGIME_WINDOW = 60
BULL_THRESHOLD = 0.10
BEAR_THRESHOLD = -0.10
