"""
Property Scanner — Noida / Greater Noida
==========================================
Scans real-estate portals for properties listed significantly below the
area-average price per square foot, then scores them by proximity to
upcoming infrastructure (Noida Metro expansion, Jewar International Airport).

Data sources:
    - 99acres.com — search results page
    - MagicBricks.com — search results page

Both sites aggressively block bots.  For production use, consider:
    1. Their official data feeds / APIs (paid).
    2. A headless browser (Playwright) rotating user agents.
    3. An aggregator API like RealtyMole or similar Indian providers.
"""

from __future__ import annotations

import asyncio
import logging
import math
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import aiohttp
from bs4 import BeautifulSoup

from opportunity_engine.config import PROPERTY as CFG

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class PropertyOpportunity:
    title: str
    area_name: str
    carpet_area_sqft: float
    listed_price: float             # INR
    price_per_sqft: float
    area_avg_per_sqft: float
    discount_pct: float
    location_score: float           # 0-100
    metro_distance_km: float
    airport_distance_km: float
    appreciation_estimate_pct: float
    url: str
    source: str

    def summary(self) -> str:
        return (
            f"{self.title}  ({self.area_name})\n"
            f"  Listed: Rs {self.listed_price:,.0f}  |  Rs {self.price_per_sqft:,.0f}/sqft  "
            f"(area avg: Rs {self.area_avg_per_sqft:,.0f})  |  Discount: {self.discount_pct:.1f}%\n"
            f"  Area: {self.carpet_area_sqft:,.0f} sqft  |  Location score: {self.location_score:.0f}/100\n"
            f"  Metro: {self.metro_distance_km:.1f} km  |  Jewar Airport: {self.airport_distance_km:.1f} km\n"
            f"  Est. appreciation: {self.appreciation_estimate_pct:.1f}%  |  [{self.source}] {self.url}"
        )


# ---------------------------------------------------------------------------
# Geospatial helpers
# ---------------------------------------------------------------------------

# Approximate lat/lon for key Noida locations and infrastructure
_COORDS: Dict[str, Tuple[float, float]] = {
    "Noida Sector 150":             (28.4490, 77.5000),
    "Noida Sector 137":             (28.4810, 77.4210),
    "Noida Sector 128":             (28.5080, 77.3730),
    "Greater Noida West":           (28.5700, 77.4400),
    "Greater Noida Sector Omega":   (28.4580, 77.5200),
    "Yamuna Expressway":            (28.3800, 77.5500),
    "Jewar":                        (28.1300, 77.5500),
    # Infrastructure
    "_aqua_line_terminus":          (28.4700, 77.5100),  # Noida Metro Aqua Line
    "_jewar_airport":               (28.1800, 77.5800),  # Jewar Intl Airport (under construction)
}


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points on Earth in kilometres."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _compute_distances(area_name: str) -> Tuple[float, float]:
    """Return (metro_distance_km, airport_distance_km) for an area."""
    area_coord = _COORDS.get(area_name)
    if not area_coord:
        return 99.0, 99.0
    metro = _haversine_km(*area_coord, *_COORDS["_aqua_line_terminus"])
    airport = _haversine_km(*area_coord, *_COORDS["_jewar_airport"])
    return round(metro, 1), round(airport, 1)


def _location_score(metro_km: float, airport_km: float) -> float:
    """
    0-100 score combining metro and airport proximity.
    Closer = higher score.
    """
    metro_score = max(0, 50 - metro_km * 5)      # within 10 km gets points
    airport_score = max(0, 50 - airport_km * 1)   # within 50 km gets points
    return round(min(100, metro_score + airport_score), 1)


def _appreciation_estimate(metro_km: float, airport_km: float, discount_pct: float) -> float:
    """
    Rough estimate of 2-3 year appreciation potential (%).
    Factors: infra proximity, current discount, general Noida growth.
    """
    base = 8.0  # Noida baseline YoY appreciation %
    metro_bonus = max(0, (10 - metro_km) * 1.5)
    airport_bonus = max(0, (30 - airport_km) * 0.5)
    discount_reversion = discount_pct * 0.4  # part of discount will revert
    return round(base + metro_bonus + airport_bonus + discount_reversion, 1)


# ---------------------------------------------------------------------------
# Scraper — 99acres
# ---------------------------------------------------------------------------

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/121.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-IN,en;q=0.9",
}


async def _scan_99acres(session: aiohttp.ClientSession) -> List[dict]:
    """
    Fetch property listings from 99acres search results.

    Returns raw dicts with keys: title, area_name, carpet_sqft, price, url.

    NOTE: 99acres blocks automated scraping.  For production:
      - Use their paid API or data feed.
      - Or use Playwright with randomised delays and proxy rotation.
    """
    raw: List[dict] = []
    url = CFG.ninety_nine_acres_url

    try:
        async with session.get(url, headers=_HEADERS, timeout=aiohttp.ClientTimeout(total=20)) as resp:
            if resp.status != 200:
                logger.warning("99acres returned %d", resp.status)
                return raw
            html = await resp.text()

        soup = BeautifulSoup(html, "html.parser")

        # 99acres listing cards — selectors may change; update as needed
        cards = soup.select("div[class*='srpTuple'], div[class*='projectTuple'], section[class*='listing']")

        for card in cards:
            title_el = card.select_one("a[class*='body_med'], h2 a, a[title]")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            link = title_el.get("href", "")
            property_url = f"https://www.99acres.com{link}" if link.startswith("/") else link

            # Extract area name from title or locality tag
            locality_el = card.select_one("span[class*='locName'], div[class*='locn']")
            area_text = locality_el.get_text(strip=True) if locality_el else title

            # Match to our target areas
            matched_area = _match_area(area_text)
            if not matched_area:
                continue

            # Extract carpet area
            area_el = card.select_one("span[class*='area'], td[class*='area']")
            carpet_sqft = _parse_area_sqft(area_el.get_text(strip=True) if area_el else "")

            # Extract price
            price_el = card.select_one("span[class*='price'], td[class*='price']")
            price = _parse_price(price_el.get_text(strip=True) if price_el else "")

            if carpet_sqft > 0 and price > 0:
                raw.append({
                    "title": title,
                    "area_name": matched_area,
                    "carpet_sqft": carpet_sqft,
                    "price": price,
                    "url": property_url,
                    "source": "99acres",
                })

        logger.info("99acres: parsed %d listings from %d cards", len(raw), len(cards))

    except Exception as exc:
        logger.error("99acres scrape failed: %s", exc)

    return raw


# ---------------------------------------------------------------------------
# Scraper — MagicBricks
# ---------------------------------------------------------------------------

async def _scan_magicbricks(session: aiohttp.ClientSession) -> List[dict]:
    """
    Fetch property listings from MagicBricks search results.

    Same caveats as 99acres regarding bot detection.
    """
    raw: List[dict] = []
    url = CFG.magicbricks_url

    try:
        async with session.get(url, headers=_HEADERS, timeout=aiohttp.ClientTimeout(total=20)) as resp:
            if resp.status != 200:
                logger.warning("MagicBricks returned %d", resp.status)
                return raw
            html = await resp.text()

        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select("div[class*='SRCard'], div[class*='mb-srp__card'], div.property-card")

        for card in cards:
            title_el = card.select_one("h2 a, a[class*='title'], span[class*='title']")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            link = title_el.get("href", "")
            property_url = link if link.startswith("http") else f"https://www.magicbricks.com{link}"

            locality_el = card.select_one("span[class*='loc'], div[class*='locality']")
            area_text = locality_el.get_text(strip=True) if locality_el else title

            matched_area = _match_area(area_text)
            if not matched_area:
                continue

            area_el = card.select_one("span[class*='carpetArea'], div[class*='area']")
            carpet_sqft = _parse_area_sqft(area_el.get_text(strip=True) if area_el else "")

            price_el = card.select_one("span[class*='price'], div[class*='price']")
            price = _parse_price(price_el.get_text(strip=True) if price_el else "")

            if carpet_sqft > 0 and price > 0:
                raw.append({
                    "title": title,
                    "area_name": matched_area,
                    "carpet_sqft": carpet_sqft,
                    "price": price,
                    "url": property_url,
                    "source": "MagicBricks",
                })

        logger.info("MagicBricks: parsed %d listings from %d cards", len(raw), len(cards))

    except Exception as exc:
        logger.error("MagicBricks scrape failed: %s", exc)

    return raw


# ---------------------------------------------------------------------------
# Parse helpers
# ---------------------------------------------------------------------------

def _match_area(text: str) -> Optional[str]:
    """Match free-form location text to one of our tracked areas."""
    text_lower = text.lower()
    for area in CFG.target_locations:
        # Fuzzy match: area name keywords
        keywords = area.lower().split()
        if all(kw in text_lower for kw in keywords):
            return area
    return None


_AREA_NUM = re.compile(r"([\d,.]+)\s*(sq\.?\s*ft|sqft|sft|square\s*feet)", re.I)
_AREA_NUM_SQMT = re.compile(r"([\d,.]+)\s*(sq\.?\s*m|sqm|square\s*met)", re.I)


def _parse_area_sqft(text: str) -> float:
    """Parse carpet area in square feet from text."""
    m = _AREA_NUM.search(text)
    if m:
        return float(m.group(1).replace(",", ""))
    m = _AREA_NUM_SQMT.search(text)
    if m:
        sqm = float(m.group(1).replace(",", ""))
        return sqm * 10.7639  # convert sq metres to sq feet
    # Last resort: just find a number
    nums = re.findall(r"[\d,.]+", text.replace(",", ""))
    if nums:
        val = float(nums[0])
        if 200 < val < 10000:
            return val
    return 0.0


_PRICE_PATTERN = re.compile(r"([\d,.]+)\s*(cr|crore|lac|lakh|l|k)?\b", re.I)


def _parse_price(text: str) -> float:
    """Parse price from text like '85 L', '1.2 Cr', '45,00,000'."""
    text = text.replace("₹", "").replace("Rs", "").replace("INR", "").strip()
    m = _PRICE_PATTERN.search(text)
    if not m:
        return 0.0
    value = float(m.group(1).replace(",", ""))
    unit = (m.group(2) or "").lower()
    if unit in ("cr", "crore"):
        return value * 1_00_00_000
    if unit in ("lac", "lakh", "l"):
        return value * 1_00_000
    if unit == "k":
        return value * 1_000
    # If the number is small it's probably in lakhs
    if value < 500:
        return value * 1_00_000
    return value


# ---------------------------------------------------------------------------
# Fallback data
# ---------------------------------------------------------------------------

def _fallback_properties() -> List[dict]:
    """Synthetic data for testing without live scraping."""
    return [
        {
            "title": "3 BHK Flat in ATS Pristine, Sector 150",
            "area_name": "Noida Sector 150",
            "carpet_sqft": 1450,
            "price": 88_00_000,
            "url": "https://www.99acres.com/3bhk-ats-pristine-sector150",
            "source": "99acres-demo",
        },
        {
            "title": "2 BHK Apartment, Jaypee Greens, Yamuna Expressway",
            "area_name": "Yamuna Expressway",
            "carpet_sqft": 1050,
            "price": 32_00_000,
            "url": "https://www.magicbricks.com/2bhk-jaypee-yamuna",
            "source": "MagicBricks-demo",
        },
        {
            "title": "3 BHK in Gaur Yamuna City, Greater Noida West",
            "area_name": "Greater Noida West",
            "carpet_sqft": 1350,
            "price": 55_00_000,
            "url": "https://www.99acres.com/3bhk-gaur-yamuna-city",
            "source": "99acres-demo",
        },
        {
            "title": "2 BHK Flat near Jewar Airport, Jewar",
            "area_name": "Jewar",
            "carpet_sqft": 900,
            "price": 24_00_000,
            "url": "https://www.magicbricks.com/2bhk-jewar-airport",
            "source": "MagicBricks-demo",
        },
        {
            "title": "4 BHK Penthouse, Supertech ORB, Sector 137",
            "area_name": "Noida Sector 137",
            "carpet_sqft": 2200,
            "price": 1_45_00_000,
            "url": "https://www.99acres.com/4bhk-supertech-orb-137",
            "source": "99acres-demo",
        },
    ]


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def _analyze(raw_listings: List[dict]) -> List[PropertyOpportunity]:
    """Compare listings against area averages and score them."""
    opportunities: List[PropertyOpportunity] = []
    avg_prices = CFG.area_avg_price_per_sqft

    for prop in raw_listings:
        area_name: str = prop["area_name"]
        carpet: float = prop["carpet_sqft"]
        price: float = prop["price"]
        price_per_sqft = price / carpet if carpet > 0 else 0
        avg = avg_prices.get(area_name, 0)

        if avg <= 0 or price_per_sqft <= 0:
            continue

        discount_pct = ((avg - price_per_sqft) / avg) * 100
        if discount_pct < CFG.min_discount_pct:
            continue

        metro_km, airport_km = _compute_distances(area_name)
        loc_score = _location_score(metro_km, airport_km)
        appreciation = _appreciation_estimate(metro_km, airport_km, discount_pct)

        opportunities.append(PropertyOpportunity(
            title=prop["title"],
            area_name=area_name,
            carpet_area_sqft=carpet,
            listed_price=price,
            price_per_sqft=round(price_per_sqft, 0),
            area_avg_per_sqft=avg,
            discount_pct=round(discount_pct, 1),
            location_score=loc_score,
            metro_distance_km=metro_km,
            airport_distance_km=airport_km,
            appreciation_estimate_pct=appreciation,
            url=prop["url"],
            source=prop["source"],
        ))

    opportunities.sort(key=lambda o: o.discount_pct, reverse=True)
    return opportunities


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def scan() -> List[PropertyOpportunity]:
    """Run the full property scan."""
    connector = aiohttp.TCPConnector(ssl=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        results_99, results_mb = await asyncio.gather(
            _scan_99acres(session),
            _scan_magicbricks(session),
            return_exceptions=True,
        )

    raw: List[dict] = []
    if isinstance(results_99, list):
        raw.extend(results_99)
    else:
        logger.error("99acres raised: %s", results_99)

    if isinstance(results_mb, list):
        raw.extend(results_mb)
    else:
        logger.error("MagicBricks raised: %s", results_mb)

    if not raw:
        logger.info("No live property data — using demo listings")
        raw = _fallback_properties()

    opportunities = _analyze(raw)
    logger.info("Property scan complete — %d opportunities", len(opportunities))
    return opportunities


# ---------------------------------------------------------------------------
# Standalone
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    results = asyncio.run(scan())
    print(f"\n{'='*90}")
    print(f"  PROPERTY OPPORTUNITIES  ({len(results)} found)")
    print(f"{'='*90}\n")
    for r in results:
        print(r.summary())
        print()
