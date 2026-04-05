"""
Central configuration for the Opportunity Engine.

All secrets are loaded from environment variables (use a .env file locally).
Scanner thresholds and filters are defined here so they can be tuned in one place.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from dotenv import load_dotenv

# Load .env from project root
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_ENV_PATH)


def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default)


def _env_int(key: str, default: int = 0) -> int:
    raw = os.getenv(key, "")
    if raw.isdigit():
        return int(raw)
    return default


def _env_float(key: str, default: float = 0.0) -> float:
    raw = os.getenv(key, "")
    try:
        return float(raw)
    except ValueError:
        return default


# ---------------------------------------------------------------------------
# API Keys & Tokens
# ---------------------------------------------------------------------------

TELEGRAM_BOT_TOKEN: str = _env("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHANNEL_ID: str = _env("TELEGRAM_CHANNEL_ID")  # e.g. "@my_opportunity_alerts"

RAZORPAY_KEY_ID: str = _env("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET: str = _env("RAZORPAY_KEY_SECRET")

GOLD_API_KEY: str = _env("GOLD_API_KEY")  # goldapi.io or metals-api.com
AMAZON_AFFILIATE_TAG: str = _env("AMAZON_AFFILIATE_TAG", "myaff-21")
FLIPKART_AFFILIATE_ID: str = _env("FLIPKART_AFFILIATE_ID")
FLIPKART_AFFILIATE_TOKEN: str = _env("FLIPKART_AFFILIATE_TOKEN")


# ---------------------------------------------------------------------------
# SGB Scanner
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SGBConfig:
    # Minimum discount (%) below gold NAV to flag as opportunity
    min_discount_pct: float = 3.0
    # Gold price API endpoint — replace with your preferred provider
    # Option A: https://www.goldapi.io/api/XAU/INR  (needs header: x-access-token)
    # Option B: https://metals-api.com/api/latest?access_key=KEY&base=XAU&symbols=INR
    gold_price_api_url: str = "https://www.goldapi.io/api/XAU/INR"
    # NSE corporate-bond / SGB listing page (publicly available JSON endpoint)
    nse_sgb_url: str = "https://www.nseindia.com/api/liveBonds-traded-in-capital-market?type=gsec&segment=sgb"
    # Fallback: grams-per-bond constant used by RBI for SGBs
    grams_per_bond: float = 1.0
    # Annual coupon rate (%) paid by RBI on SGBs
    coupon_rate: float = 2.5


SGB = SGBConfig(
    min_discount_pct=_env_float("SGB_MIN_DISCOUNT_PCT", 3.0),
)


# ---------------------------------------------------------------------------
# Tender Scanner
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TenderConfig:
    # GeM search URL template — filters are appended as query params
    gem_search_url: str = "https://bidplus.gem.gov.in/all-bids"
    # Central Public Procurement Portal
    eprocure_url: str = "https://eprocure.gov.in/eprocure/app"
    # Keywords to search for
    keywords: tuple = (
        "software development",
        "IT services",
        "artificial intelligence",
        "machine learning",
        "data analytics",
        "web application",
        "mobile application",
        "cloud services",
    )
    # Budget range in INR
    min_value: int = 100_000       # 1 lakh
    max_value: int = 50_00_000     # 50 lakh
    # Only show tenders with deadline > N days away
    min_days_remaining: int = 3


TENDER = TenderConfig(
    min_value=_env_int("TENDER_MIN_VALUE", 100_000),
    max_value=_env_int("TENDER_MAX_VALUE", 50_00_000),
)


# ---------------------------------------------------------------------------
# Property Scanner
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PropertyConfig:
    # Minimum discount (%) below area average to flag
    min_discount_pct: float = 10.0
    # Target locations (sector / area names)
    target_locations: tuple = (
        "Noida Sector 150",
        "Noida Sector 137",
        "Noida Sector 128",
        "Greater Noida West",
        "Greater Noida Sector Omega",
        "Yamuna Expressway",
        "Jewar",
    )
    # Area average price per sqft (INR) — update periodically or pull from API
    # These are approximate 2025 numbers; tune to real data.
    area_avg_price_per_sqft: dict = field(default_factory=lambda: {
        "Noida Sector 150": 7500,
        "Noida Sector 137": 8200,
        "Noida Sector 128": 9500,
        "Greater Noida West": 5200,
        "Greater Noida Sector Omega": 4800,
        "Yamuna Expressway": 3800,
        "Jewar": 3500,
    })
    # Proximity bonus multipliers
    metro_proximity_km: float = 5.0
    airport_proximity_km: float = 15.0
    # Placeholder scraping URLs
    ninety_nine_acres_url: str = "https://www.99acres.com/search/property/buy/noida?city=18&preference=S&area_unit=1&budget_min=20&budget_max=200"
    magicbricks_url: str = "https://www.magicbricks.com/property-for-sale/residential-real-estate?bedroom=2,3&proptype=Multistorey-Apartment,Builder-Floor-Apartment&cityName=Noida"


PROPERTY = PropertyConfig(
    min_discount_pct=_env_float("PROPERTY_MIN_DISCOUNT_PCT", 10.0),
)


# ---------------------------------------------------------------------------
# Job Matcher
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class JobMatcherConfig:
    # Path to local contacts JSON database
    contacts_db_path: str = str(Path(__file__).resolve().parent / "data" / "contacts.json")
    # Minimum match score (0-100) to surface an opportunity
    min_match_score: int = 60
    # Referral bonus estimates by company tier
    referral_bonus_estimates: dict = field(default_factory=lambda: {
        "tier1": 50_000,   # FAANG etc.
        "tier2": 25_000,   # good startups / mid-size
        "tier3": 10_000,   # others
    })
    # LinkedIn job search (requires LinkedIn API or scraping)
    linkedin_job_search_url: str = "https://www.linkedin.com/jobs/search/?keywords={keywords}&location=India"
    # Keywords to search
    keywords: tuple = (
        "Python Developer",
        "Data Scientist",
        "ML Engineer",
        "Backend Engineer",
        "Full Stack Developer",
        "DevOps Engineer",
    )


JOB = JobMatcherConfig(
    min_match_score=_env_int("JOB_MIN_MATCH_SCORE", 60),
)


# ---------------------------------------------------------------------------
# Deal Scanner
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DealConfig:
    # Minimum price-drop percentage to surface
    min_price_drop_pct: float = 20.0
    # Product tracking list path
    tracked_products_path: str = str(Path(__file__).resolve().parent / "data" / "tracked_products.json")
    # Price history path
    price_history_path: str = str(Path(__file__).resolve().parent / "data" / "price_history.json")
    # Amazon affiliate tag
    amazon_tag: str = AMAZON_AFFILIATE_TAG
    # Flipkart affiliate
    flipkart_aff_id: str = FLIPKART_AFFILIATE_ID


DEAL = DealConfig(
    min_price_drop_pct=_env_float("DEAL_MIN_PRICE_DROP_PCT", 20.0),
)


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SchedulerConfig:
    sgb_interval_hours: int = 4
    sgb_market_start_hour: int = 9
    sgb_market_end_hour: int = 16
    tender_times: tuple = ("08:00", "18:00")
    property_time: str = "07:00"
    job_time: str = "09:00"
    deal_interval_hours: int = 2


SCHEDULER = SchedulerConfig()


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

LOG_LEVEL: str = _env("LOG_LEVEL", "INFO")
LOG_FILE: str = _env("LOG_FILE", str(Path(__file__).resolve().parent.parent / "opportunity_engine.log"))
