"""
SGB (Sovereign Gold Bond) Scanner
==================================
Fetches live gold price and NSE-listed SGB prices, then flags any series
trading at a significant discount to the underlying gold NAV.

Data flow:
    1. Get current gold price per gram in INR.
    2. Derive NAV per SGB bond (1 gram gold + accrued coupon).
    3. Pull SGB market prices from NSE.
    4. Compare and flag discounts above threshold.

API keys required:
    - GOLD_API_KEY  (goldapi.io — free tier gives 10 req/day)
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import List, Optional

import aiohttp

from opportunity_engine.config import SGB as CFG, GOLD_API_KEY

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class SGBOpportunity:
    series_name: str
    current_price: float          # market price on NSE (INR)
    gold_nav: float               # theoretical fair value (INR)
    discount_pct: float           # how far below NAV the bond trades
    maturity_date: Optional[date] = None
    annualized_return_pct: float = 0.0
    coupon_rate: float = CFG.coupon_rate
    isin: str = ""

    def summary(self) -> str:
        mat = self.maturity_date.isoformat() if self.maturity_date else "N/A"
        return (
            f"SGB {self.series_name}  |  Price: Rs {self.current_price:,.0f}  |  "
            f"NAV: Rs {self.gold_nav:,.0f}  |  Discount: {self.discount_pct:.1f}%  |  "
            f"Maturity: {mat}  |  Est. annual return: {self.annualized_return_pct:.1f}%"
        )


# ---------------------------------------------------------------------------
# Gold price fetcher
# ---------------------------------------------------------------------------

async def fetch_gold_price_per_gram(session: aiohttp.ClientSession) -> float:
    """
    Return the current price of 1 gram of 24k gold in INR.

    Uses goldapi.io — sign up at https://www.goldapi.io/ for a free key,
    then set GOLD_API_KEY in your .env file.
    """
    url = CFG.gold_price_api_url
    headers = {
        "x-access-token": GOLD_API_KEY,
        "Content-Type": "application/json",
    }

    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                logger.warning("Gold API returned status %d — falling back to manual price", resp.status)
                return _fallback_gold_price()
            data = await resp.json()
            # goldapi.io returns price per troy ounce; convert to grams
            # 1 troy ounce = 31.1035 grams
            price_per_ounce_inr: float = data.get("price", 0.0)
            if price_per_ounce_inr <= 0:
                logger.warning("Invalid gold price from API: %s", data)
                return _fallback_gold_price()
            price_per_gram = price_per_ounce_inr / 31.1035
            logger.info("Gold price fetched: Rs %.2f / gram", price_per_gram)
            return price_per_gram
    except Exception as exc:
        logger.error("Failed to fetch gold price: %s", exc)
        return _fallback_gold_price()


def _fallback_gold_price() -> float:
    """
    Hardcoded fallback so the scanner can still demonstrate its logic
    even without a live API key.  Update this periodically or replace
    with a second API source.
    """
    # Approximate gold price in INR per gram as of early 2026
    FALLBACK_PRICE = 7800.0
    logger.info("Using fallback gold price: Rs %.2f / gram", FALLBACK_PRICE)
    return FALLBACK_PRICE


# ---------------------------------------------------------------------------
# NSE SGB price fetcher
# ---------------------------------------------------------------------------

@dataclass
class SGBListing:
    series_name: str
    isin: str
    last_price: float
    maturity_date: Optional[date]

    @classmethod
    def from_nse_row(cls, row: dict) -> Optional["SGBListing"]:
        """Parse a single row from the NSE bonds JSON response."""
        try:
            series = row.get("symbol", row.get("series", "UNKNOWN"))
            isin = row.get("isin", row.get("meta", {}).get("isin", ""))
            price_str = str(row.get("ltP", row.get("lastPrice", "0")))
            price = float(price_str.replace(",", ""))

            mat_str = row.get("matDt", row.get("maturityDate", ""))
            mat_date = None
            if mat_str:
                for fmt in ("%d-%b-%Y", "%d-%m-%Y", "%Y-%m-%d", "%d %b %Y"):
                    try:
                        mat_date = datetime.strptime(mat_str, fmt).date()
                        break
                    except ValueError:
                        continue

            if price <= 0:
                return None
            return cls(series_name=series, isin=isin, last_price=price, maturity_date=mat_date)
        except Exception as exc:
            logger.debug("Skipping malformed NSE row: %s — %s", row, exc)
            return None


async def fetch_sgb_listings(session: aiohttp.ClientSession) -> List[SGBListing]:
    """
    Fetch SGB listings from NSE.

    NSE's public API at /api/liveBonds-traded-in-capital-market returns
    a JSON array.  A browser-like User-Agent and prior cookie from the
    homepage may be needed to avoid 403s.

    NOTE: NSE aggressively blocks non-browser requests.  If you get
    403/empty responses, consider:
      1. Using a Selenium / Playwright headless browser to get the cookie.
      2. Using an unofficial NSE data provider (e.g., jugaad-data, nsetools).
      3. Maintaining a local CSV of SGB ISIN codes and scraping individual
         quote pages.
    """
    url = CFG.nse_sgb_url
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
    }

    listings: List[SGBListing] = []

    try:
        # Step 1: Hit NSE homepage to get cookies (required)
        async with session.get(
            "https://www.nseindia.com",
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=10),
            allow_redirects=True,
        ) as _:
            pass  # we just need the cookies stored in the session

        # Step 2: Fetch SGB data
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                logger.warning("NSE returned status %d for SGB listing", resp.status)
                return _fallback_sgb_listings()
            data = await resp.json(content_type=None)

            rows = data if isinstance(data, list) else data.get("data", [])
            for row in rows:
                listing = SGBListing.from_nse_row(row)
                if listing:
                    listings.append(listing)

        logger.info("Fetched %d SGB listings from NSE", len(listings))
    except Exception as exc:
        logger.error("NSE SGB fetch failed: %s — using fallback data", exc)
        return _fallback_sgb_listings()

    return listings if listings else _fallback_sgb_listings()


def _fallback_sgb_listings() -> List[SGBListing]:
    """
    Demo / fallback data so the scanner logic can be exercised
    without a live NSE connection.  Replace with real data or
    a local CSV of SGB series.
    """
    return [
        SGBListing("SGBAUG27", "INE002A23014", 5450, date(2027, 8, 5)),
        SGBListing("SGBNOV27", "INE002A23022", 5380, date(2027, 11, 15)),
        SGBListing("SGBFEB28", "INE002A23030", 5520, date(2028, 2, 10)),
        SGBListing("SGBJUN28", "INE002A23048", 5600, date(2028, 6, 20)),
        SGBListing("SGBSEP28", "INE002A23055", 5300, date(2028, 9, 12)),
        SGBListing("SGBMAR29", "INE002A23063", 5700, date(2029, 3, 1)),
        SGBListing("SGBJUL29", "INE002A23071", 5250, date(2029, 7, 18)),
    ]


# ---------------------------------------------------------------------------
# Core analysis
# ---------------------------------------------------------------------------

def _annualized_return(
    buy_price: float,
    gold_nav: float,
    coupon_rate: float,
    maturity_date: Optional[date],
) -> float:
    """
    Estimate annualized return if you buy the SGB at *buy_price* and hold
    to maturity (redeemed at gold_nav equivalent at that time).

    Simplified model:
        Total gain  = (gold_nav - buy_price) + (coupon_rate * gold_nav * years)
        Annualized  = total_gain / buy_price / years * 100

    This is a rough estimate — real returns depend on gold price at maturity.
    """
    if maturity_date is None:
        return 0.0
    today = date.today()
    if maturity_date <= today:
        return 0.0
    years = (maturity_date - today).days / 365.25
    if years <= 0 or buy_price <= 0:
        return 0.0

    capital_gain = gold_nav - buy_price
    coupon_income = coupon_rate / 100 * gold_nav * years
    total_gain = capital_gain + coupon_income
    annualized = (total_gain / buy_price) / years * 100
    return round(annualized, 2)


async def scan() -> List[SGBOpportunity]:
    """
    Main entry point.  Run the full SGB scan and return a list of
    opportunities (SGBs trading below gold NAV by more than the threshold).
    """
    opportunities: List[SGBOpportunity] = []

    connector = aiohttp.TCPConnector(ssl=False)
    cookie_jar = aiohttp.CookieJar(unsafe=True)
    async with aiohttp.ClientSession(connector=connector, cookie_jar=cookie_jar) as session:
        gold_price_per_gram, listings = await asyncio.gather(
            fetch_gold_price_per_gram(session),
            fetch_sgb_listings(session),
        )

    if gold_price_per_gram <= 0:
        logger.error("Gold price unavailable — aborting SGB scan")
        return opportunities

    # Each SGB represents CFG.grams_per_bond grams of gold
    gold_nav = gold_price_per_gram * CFG.grams_per_bond

    for listing in listings:
        if listing.last_price <= 0:
            continue
        discount_pct = ((gold_nav - listing.last_price) / gold_nav) * 100
        if discount_pct < CFG.min_discount_pct:
            continue

        ann_return = _annualized_return(
            buy_price=listing.last_price,
            gold_nav=gold_nav,
            coupon_rate=CFG.coupon_rate,
            maturity_date=listing.maturity_date,
        )

        opp = SGBOpportunity(
            series_name=listing.series_name,
            current_price=listing.last_price,
            gold_nav=gold_nav,
            discount_pct=round(discount_pct, 2),
            maturity_date=listing.maturity_date,
            annualized_return_pct=ann_return,
            isin=listing.isin,
        )
        opportunities.append(opp)
        logger.info("SGB opportunity: %s", opp.summary())

    opportunities.sort(key=lambda o: o.discount_pct, reverse=True)
    logger.info("SGB scan complete — %d opportunities found", len(opportunities))
    return opportunities


# ---------------------------------------------------------------------------
# Standalone execution
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    results = asyncio.run(scan())
    if not results:
        print("No SGB opportunities found at this time.")
    for r in results:
        print(r.summary())
