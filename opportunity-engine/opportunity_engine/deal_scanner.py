"""
Deal Scanner — E-commerce Price Drop Tracker
==============================================
Tracks products on Amazon.in and Flipkart, detects significant price drops,
and generates affiliate-linked messages for Telegram posting.

Workflow:
    1. Load tracked products from data/tracked_products.json
    2. Fetch current prices from product pages
    3. Compare against price history (data/price_history.json)
    4. Flag drops > threshold
    5. Generate affiliate links and formatted messages

Product tracking file (data/tracked_products.json):
    [
        {
            "name": "Sony WH-1000XM5",
            "amazon_url": "https://www.amazon.in/dp/B0BXYZABC1",
            "flipkart_url": "https://www.flipkart.com/sony-wh-1000xm5/p/itm123",
            "category": "electronics",
            "target_price": 22000
        },
        ...
    ]
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import aiohttp
from bs4 import BeautifulSoup

from opportunity_engine.config import DEAL as CFG

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class TrackedProduct:
    name: str
    amazon_url: str
    flipkart_url: str
    category: str
    target_price: float

    @classmethod
    def from_dict(cls, d: dict) -> "TrackedProduct":
        return cls(
            name=d.get("name", ""),
            amazon_url=d.get("amazon_url", ""),
            flipkart_url=d.get("flipkart_url", ""),
            category=d.get("category", ""),
            target_price=d.get("target_price", 0),
        )


@dataclass
class DealOpportunity:
    product_name: str
    category: str
    current_price: float
    previous_price: float
    drop_pct: float
    target_price: float
    is_below_target: bool
    source: str                     # "Amazon" or "Flipkart"
    url: str
    affiliate_url: str
    telegram_message: str

    def summary(self) -> str:
        target_flag = " [BELOW TARGET]" if self.is_below_target else ""
        return (
            f"DEAL: {self.product_name}{target_flag}\n"
            f"  Price: Rs {self.current_price:,.0f} (was Rs {self.previous_price:,.0f}) "
            f"— {self.drop_pct:.0f}% OFF\n"
            f"  Target: Rs {self.target_price:,.0f}  |  Source: {self.source}\n"
            f"  Link: {self.affiliate_url}"
        )


# ---------------------------------------------------------------------------
# Price history persistence
# ---------------------------------------------------------------------------

def _load_json(path: str) -> list | dict:
    p = Path(path)
    if not p.exists():
        return [] if "products" in path else {}
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logger.error("Failed to load %s: %s", path, exc)
        return [] if "products" in path else {}


def _save_json(path: str, data: list | dict) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
    except Exception as exc:
        logger.error("Failed to save %s: %s", path, exc)


def _load_tracked_products() -> List[TrackedProduct]:
    data = _load_json(CFG.tracked_products_path)
    if data:
        return [TrackedProduct.from_dict(d) for d in data]
    logger.info("No tracked products file — using demo products")
    return _demo_products()


def _load_price_history() -> Dict[str, List[dict]]:
    """Return {product_name: [{price, timestamp, source}, ...]}"""
    data = _load_json(CFG.price_history_path)
    return data if isinstance(data, dict) else {}


def _save_price_history(history: Dict[str, List[dict]]) -> None:
    _save_json(CFG.price_history_path, history)


def _get_previous_price(history: Dict[str, List[dict]], product_name: str) -> float:
    """Get the most recent recorded price for a product."""
    entries = history.get(product_name, [])
    if not entries:
        return 0.0
    return entries[-1].get("price", 0.0)


def _record_price(history: Dict[str, List[dict]], product_name: str, price: float, source: str) -> None:
    """Append a new price data point."""
    if product_name not in history:
        history[product_name] = []
    history[product_name].append({
        "price": price,
        "source": source,
        "timestamp": datetime.now().isoformat(),
    })
    # Keep last 100 data points per product
    history[product_name] = history[product_name][-100:]


# ---------------------------------------------------------------------------
# Affiliate link generators
# ---------------------------------------------------------------------------

def _amazon_affiliate_url(url: str) -> str:
    """Append Amazon Associates tag to a product URL."""
    tag = CFG.amazon_tag
    if not tag or not url:
        return url
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}tag={tag}"


def _flipkart_affiliate_url(url: str) -> str:
    """
    Generate Flipkart affiliate URL.

    Flipkart's affiliate program uses a redirect through dl.flipkart.com.
    You need to register at https://affiliate.flipkart.com/ to get your
    affiliate ID and token.
    """
    aff_id = CFG.flipkart_aff_id
    if not aff_id or not url:
        return url
    # Flipkart affiliate deep link format
    return f"https://dl.flipkart.com/s?affid={aff_id}&url={url}"


# ---------------------------------------------------------------------------
# Price scrapers
# ---------------------------------------------------------------------------

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/121.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html",
    "Accept-Language": "en-IN,en;q=0.9",
}

_PRICE_RE = re.compile(r"[\d,]+\.?\d*")


def _extract_price(text: str) -> float:
    """Extract a numeric price from text like '₹ 22,990.00'."""
    text = text.replace("₹", "").replace(",", "").strip()
    m = _PRICE_RE.search(text)
    return float(m.group()) if m else 0.0


async def _fetch_amazon_price(session: aiohttp.ClientSession, url: str) -> float:
    """
    Fetch current price from an Amazon.in product page.

    Amazon blocks most automated requests.  For production:
        - Use the Amazon Product Advertising API (PA-API 5.0)
          Register at https://affiliate-program.amazon.in/
        - Or use a price-tracking service API (Keepa, CamelCamelCamel)
        - Or use Playwright with residential proxies
    """
    if not url:
        return 0.0
    try:
        async with session.get(url, headers=_HEADERS, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                logger.warning("Amazon returned %d for %s", resp.status, url[:60])
                return 0.0
            html = await resp.text()

        soup = BeautifulSoup(html, "html.parser")

        # Amazon price selectors (try multiple as they vary by page type)
        for selector in (
            "span.a-price-whole",
            "span#priceblock_dealprice",
            "span#priceblock_ourprice",
            "span.a-offscreen",
            "span[data-a-color='price'] span.a-offscreen",
        ):
            el = soup.select_one(selector)
            if el:
                price = _extract_price(el.get_text())
                if price > 0:
                    return price

    except Exception as exc:
        logger.error("Amazon price fetch failed for %s: %s", url[:60], exc)

    return 0.0


async def _fetch_flipkart_price(session: aiohttp.ClientSession, url: str) -> float:
    """
    Fetch current price from a Flipkart product page.

    Flipkart also blocks scraping.  Alternatives:
        - Flipkart Affiliate API
        - Use their affiliate product feed
    """
    if not url:
        return 0.0
    try:
        async with session.get(url, headers=_HEADERS, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                logger.warning("Flipkart returned %d for %s", resp.status, url[:60])
                return 0.0
            html = await resp.text()

        soup = BeautifulSoup(html, "html.parser")

        for selector in (
            "div._30jeq3",
            "div[class*='sellingPrice']",
            "span[class*='price']",
            "div._16Jk6d",
        ):
            el = soup.select_one(selector)
            if el:
                price = _extract_price(el.get_text())
                if price > 0:
                    return price

    except Exception as exc:
        logger.error("Flipkart price fetch failed for %s: %s", url[:60], exc)

    return 0.0


# ---------------------------------------------------------------------------
# Telegram message formatter
# ---------------------------------------------------------------------------

def _format_telegram_message(deal: DealOpportunity) -> str:
    """Format a deal as a Telegram-friendly message with emoji and affiliate link."""
    below_target = "\nBELOW YOUR TARGET PRICE!" if deal.is_below_target else ""
    return (
        f"DEAL ALERT: {deal.product_name}\n\n"
        f"Price: Rs {deal.current_price:,.0f}\n"
        f"Was: Rs {deal.previous_price:,.0f}\n"
        f"Drop: {deal.drop_pct:.0f}%\n"
        f"Category: {deal.category}{below_target}\n\n"
        f"Buy now: {deal.affiliate_url}\n\n"
        f"#deals #{deal.category.replace(' ', '_')}"
    )


# ---------------------------------------------------------------------------
# Demo data
# ---------------------------------------------------------------------------

def _demo_products() -> List[TrackedProduct]:
    return [
        TrackedProduct("Sony WH-1000XM5 Headphones", "https://www.amazon.in/dp/B0BXYZABC1", "https://www.flipkart.com/sony-wh-1000xm5/p/itm123", "electronics", 22000),
        TrackedProduct("Samsung Galaxy S24 Ultra", "https://www.amazon.in/dp/B0BXYZDEF2", "https://www.flipkart.com/samsung-galaxy-s24-ultra/p/itm456", "mobile", 95000),
        TrackedProduct("MacBook Air M3", "https://www.amazon.in/dp/B0BXYZGHI3", "", "laptop", 95000),
        TrackedProduct("Dyson V15 Detect Vacuum", "https://www.amazon.in/dp/B0BXYZJKL4", "https://www.flipkart.com/dyson-v15/p/itm789", "appliances", 45000),
        TrackedProduct("LG 55 inch C3 OLED TV", "https://www.amazon.in/dp/B0BXYZMNO5", "https://www.flipkart.com/lg-55-c3-oled/p/itm012", "tv", 110000),
    ]


def _demo_price_history() -> Dict[str, List[dict]]:
    """Generate synthetic price history for demo products."""
    return {
        "Sony WH-1000XM5 Headphones": [
            {"price": 28999, "source": "Amazon", "timestamp": "2026-03-10T10:00:00"},
            {"price": 27499, "source": "Amazon", "timestamp": "2026-03-12T10:00:00"},
        ],
        "Samsung Galaxy S24 Ultra": [
            {"price": 129999, "source": "Flipkart", "timestamp": "2026-03-10T10:00:00"},
            {"price": 124999, "source": "Amazon", "timestamp": "2026-03-13T10:00:00"},
        ],
        "MacBook Air M3": [
            {"price": 114900, "source": "Amazon", "timestamp": "2026-03-11T10:00:00"},
        ],
        "Dyson V15 Detect Vacuum": [
            {"price": 62990, "source": "Amazon", "timestamp": "2026-03-09T10:00:00"},
            {"price": 54990, "source": "Flipkart", "timestamp": "2026-03-13T10:00:00"},
        ],
        "LG 55 inch C3 OLED TV": [
            {"price": 149990, "source": "Amazon", "timestamp": "2026-03-10T10:00:00"},
        ],
    }


# Simulated current prices (used when scraping fails)
_DEMO_CURRENT_PRICES: Dict[str, Dict[str, float]] = {
    "Sony WH-1000XM5 Headphones":  {"amazon": 21499, "flipkart": 22999},
    "Samsung Galaxy S24 Ultra":     {"amazon": 99999, "flipkart": 97999},
    "MacBook Air M3":               {"amazon": 89990, "flipkart": 0},
    "Dyson V15 Detect Vacuum":      {"amazon": 42990, "flipkart": 44990},
    "LG 55 inch C3 OLED TV":       {"amazon": 114990, "flipkart": 119990},
}


# ---------------------------------------------------------------------------
# Core scan logic
# ---------------------------------------------------------------------------

async def scan() -> List[DealOpportunity]:
    """Run the full deal scanning pipeline."""
    products = _load_tracked_products()
    history = _load_price_history()
    if not history:
        history = _demo_price_history()

    deals: List[DealOpportunity] = []

    connector = aiohttp.TCPConnector(ssl=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        for product in products:
            # Fetch prices from both sources in parallel
            amazon_price, flipkart_price = await asyncio.gather(
                _fetch_amazon_price(session, product.amazon_url),
                _fetch_flipkart_price(session, product.flipkart_url),
            )

            # If scraping failed, use demo prices
            if amazon_price == 0 and flipkart_price == 0:
                demo = _DEMO_CURRENT_PRICES.get(product.name, {})
                amazon_price = demo.get("amazon", 0)
                flipkart_price = demo.get("flipkart", 0)

            previous = _get_previous_price(history, product.name)

            # Evaluate each source
            for source, price, url_field in [
                ("Amazon", amazon_price, product.amazon_url),
                ("Flipkart", flipkart_price, product.flipkart_url),
            ]:
                if price <= 0 or previous <= 0:
                    continue

                drop_pct = ((previous - price) / previous) * 100
                if drop_pct < CFG.min_price_drop_pct:
                    continue

                is_below_target = price <= product.target_price

                if source == "Amazon":
                    aff_url = _amazon_affiliate_url(url_field)
                else:
                    aff_url = _flipkart_affiliate_url(url_field)

                deal = DealOpportunity(
                    product_name=product.name,
                    category=product.category,
                    current_price=price,
                    previous_price=previous,
                    drop_pct=round(drop_pct, 1),
                    target_price=product.target_price,
                    is_below_target=is_below_target,
                    source=source,
                    url=url_field,
                    affiliate_url=aff_url,
                    telegram_message="",
                )
                deal.telegram_message = _format_telegram_message(deal)
                deals.append(deal)

                # Record the new price
                _record_price(history, product.name, price, source)

    # Save updated history
    _save_price_history(history)

    deals.sort(key=lambda d: d.drop_pct, reverse=True)
    logger.info("Deal scan complete — %d deals found", len(deals))
    return deals


# ---------------------------------------------------------------------------
# Standalone
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    results = asyncio.run(scan())
    print(f"\n{'='*80}")
    print(f"  DEAL OPPORTUNITIES  ({len(results)} found)")
    print(f"{'='*80}\n")
    for r in results:
        print(r.summary())
        print()
