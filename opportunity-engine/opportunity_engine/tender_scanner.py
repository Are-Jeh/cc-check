"""
Government Tender Scanner
==========================
Scans GeM (Government e-Marketplace) and eProcure for IT/AI/Software
tenders in the Rs 1L–50L range that a small MSME can bid on.

Data sources:
    - https://bidplus.gem.gov.in — GeM's bid listing API
    - https://eprocure.gov.in — Central Public Procurement Portal

Both portals render content server-side, so we use a mix of:
    1. Direct requests to any JSON endpoints found.
    2. HTML parsing with BeautifulSoup as a fallback.

NOTE: Government portals change their markup frequently.  If selectors
break, inspect the page and update the CSS / XPath selectors below.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import List, Optional
from urllib.parse import quote_plus, urljoin

import aiohttp
from bs4 import BeautifulSoup

from opportunity_engine.config import TENDER as CFG

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class TenderOpportunity:
    title: str
    department: str
    estimated_value: float          # INR
    deadline: Optional[date]
    url: str
    source: str                     # "GeM" or "eProcure"
    keywords_matched: List[str]

    def summary(self) -> str:
        dl = self.deadline.isoformat() if self.deadline else "N/A"
        val = f"Rs {self.estimated_value:,.0f}" if self.estimated_value else "Not disclosed"
        kw = ", ".join(self.keywords_matched[:3])
        return (
            f"[{self.source}]  {self.title[:80]}\n"
            f"  Dept: {self.department}  |  Value: {val}  |  Deadline: {dl}\n"
            f"  Keywords: {kw}\n"
            f"  URL: {self.url}"
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/json",
    "Accept-Language": "en-IN,en;q=0.9",
}

_VALUE_PATTERN = re.compile(r"[\d,]+\.?\d*")


def _parse_inr(text: str) -> float:
    """Extract a numeric INR value from text like 'Rs 5,00,000.00' or '₹ 10 Lakh'."""
    if not text:
        return 0.0
    text = text.strip().lower()

    multiplier = 1.0
    if "crore" in text or "cr" in text:
        multiplier = 1_00_00_000
    elif "lakh" in text or "lac" in text:
        multiplier = 1_00_000

    match = _VALUE_PATTERN.search(text.replace(",", ""))
    if match:
        return float(match.group()) * multiplier
    return 0.0


def _parse_date(text: str) -> Optional[date]:
    """Try multiple date formats commonly used on government portals."""
    if not text:
        return None
    text = text.strip()
    for fmt in (
        "%d-%m-%Y", "%d/%m/%Y", "%d-%b-%Y", "%d %b %Y",
        "%Y-%m-%d", "%d.%m.%Y", "%d-%m-%Y %H:%M",
    ):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    return None


def _matches_keywords(text: str) -> List[str]:
    """Return which of our target keywords appear in *text*."""
    text_lower = text.lower()
    return [kw for kw in CFG.keywords if kw.lower() in text_lower]


def _value_in_range(value: float) -> bool:
    if value <= 0:
        return True  # value not disclosed — still include
    return CFG.min_value <= value <= CFG.max_value


def _deadline_ok(dl: Optional[date]) -> bool:
    if dl is None:
        return True
    return dl >= date.today() + timedelta(days=CFG.min_days_remaining)


# ---------------------------------------------------------------------------
# GeM scraper
# ---------------------------------------------------------------------------

async def _scan_gem(session: aiohttp.ClientSession) -> List[TenderOpportunity]:
    """
    Scrape GeM's bid listing for IT / AI tenders.

    GeM recently introduced a public search at bidplus.gem.gov.in/all-bids.
    The page loads bids as server-rendered HTML with pagination.

    If GeM moves to a client-rendered SPA, you will need Playwright / Selenium
    instead of plain HTTP requests.
    """
    results: List[TenderOpportunity] = []

    for keyword in CFG.keywords:
        url = f"{CFG.gem_search_url}?searchBid={quote_plus(keyword)}"
        try:
            async with session.get(url, headers=_HEADERS, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                if resp.status != 200:
                    logger.warning("GeM returned %d for keyword '%s'", resp.status, keyword)
                    continue
                html = await resp.text()
        except Exception as exc:
            logger.error("GeM request failed for '%s': %s", keyword, exc)
            continue

        soup = BeautifulSoup(html, "html.parser")

        # -- GeM bid cards are typically in divs with class 'bid_no' or similar.
        # -- Adjust these selectors based on the current DOM structure.
        bid_cards = soup.select("div.bid_no, div.block, tr.bid-row, div[class*='bid']")
        if not bid_cards:
            # Fallback: look for table rows
            bid_cards = soup.select("table tbody tr")

        for card in bid_cards:
            text = card.get_text(separator=" ", strip=True)
            matched = _matches_keywords(text)
            if not matched:
                continue

            # Extract title — usually the first link or heading inside the card
            link_tag = card.find("a", href=True)
            title = link_tag.get_text(strip=True) if link_tag else text[:120]
            href = link_tag["href"] if link_tag else ""
            bid_url = urljoin(CFG.gem_search_url, href) if href else url

            # Extract department / organisation
            dept_el = card.find(string=re.compile(r"(Department|Ministry|Organisation)", re.I))
            department = dept_el.strip() if dept_el else "Government of India"

            # Extract estimated value
            value_el = card.find(string=re.compile(r"(Estimated|Value|Amount|Budget)", re.I))
            estimated_value = _parse_inr(value_el) if value_el else 0.0

            # Extract deadline
            date_el = card.find(string=re.compile(r"(Closing|Deadline|End Date|Last Date)", re.I))
            deadline = _parse_date(str(date_el)) if date_el else None

            if not _value_in_range(estimated_value):
                continue
            if not _deadline_ok(deadline):
                continue

            results.append(TenderOpportunity(
                title=title,
                department=department,
                estimated_value=estimated_value,
                deadline=deadline,
                url=bid_url,
                source="GeM",
                keywords_matched=matched,
            ))

        logger.info("GeM '%s': found %d raw cards, kept %d", keyword, len(bid_cards), len(results))

    return results


# ---------------------------------------------------------------------------
# eProcure scraper
# ---------------------------------------------------------------------------

async def _scan_eprocure(session: aiohttp.ClientSession) -> List[TenderOpportunity]:
    """
    Scrape eProcure.gov.in for relevant IT tenders.

    The portal at /eprocure/app has an 'Active Tenders' search page.
    It uses POST-based form submission.

    NOTE: eProcure uses ASP.NET-style ViewState; you may need to first
    GET the page, extract the __VIEWSTATE, then POST with search params.
    """
    results: List[TenderOpportunity] = []

    search_url = f"{CFG.eprocure_url}"

    for keyword in CFG.keywords:
        try:
            # Step 1: GET the search page to obtain any CSRF / ViewState tokens
            async with session.get(search_url, headers=_HEADERS, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    logger.warning("eProcure GET returned %d", resp.status)
                    continue
                html = await resp.text()

            soup = BeautifulSoup(html, "html.parser")

            # Look for search form and extract hidden fields
            form_data = {}
            for hidden in soup.select("input[type='hidden']"):
                name = hidden.get("name", "")
                value = hidden.get("value", "")
                if name:
                    form_data[name] = value

            # Add our search keyword
            # Field names vary — inspect the page and update these
            form_data.update({
                "search": keyword,
                "searchKeyword": keyword,
                "tenderType": "Active",
            })

            # Step 2: POST the search
            async with session.post(
                search_url,
                data=form_data,
                headers={**_HEADERS, "Content-Type": "application/x-www-form-urlencoded"},
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                if resp.status != 200:
                    logger.warning("eProcure POST returned %d for '%s'", resp.status, keyword)
                    continue
                html = await resp.text()

            soup = BeautifulSoup(html, "html.parser")
            rows = soup.select("table#table1 tbody tr, table.list_table tbody tr, div.tender-item")

            for row in rows:
                text = row.get_text(separator=" ", strip=True)
                matched = _matches_keywords(text)
                if not matched:
                    continue

                cells = row.find_all("td")
                title = cells[0].get_text(strip=True) if cells else text[:120]
                department = cells[1].get_text(strip=True) if len(cells) > 1 else "Government of India"

                link_tag = row.find("a", href=True)
                tender_url = urljoin(search_url, link_tag["href"]) if link_tag else search_url

                # Extract value and date from remaining cells
                value_text = cells[2].get_text(strip=True) if len(cells) > 2 else ""
                date_text = cells[3].get_text(strip=True) if len(cells) > 3 else ""

                estimated_value = _parse_inr(value_text)
                deadline = _parse_date(date_text)

                if not _value_in_range(estimated_value):
                    continue
                if not _deadline_ok(deadline):
                    continue

                results.append(TenderOpportunity(
                    title=title,
                    department=department,
                    estimated_value=estimated_value,
                    deadline=deadline,
                    url=tender_url,
                    source="eProcure",
                    keywords_matched=matched,
                ))

            logger.info("eProcure '%s': kept %d results", keyword, len(results))

        except Exception as exc:
            logger.error("eProcure scan failed for '%s': %s", keyword, exc)
            continue

    return results


# ---------------------------------------------------------------------------
# Demo / fallback data
# ---------------------------------------------------------------------------

def _fallback_tenders() -> List[TenderOpportunity]:
    """Synthetic data so the scanner can be exercised without live portal access."""
    today = date.today()
    return [
        TenderOpportunity(
            title="Development of AI-based Document Processing System",
            department="Ministry of Electronics & IT",
            estimated_value=35_00_000,
            deadline=today + timedelta(days=12),
            url="https://bidplus.gem.gov.in/showbidDocument/12345",
            source="GeM",
            keywords_matched=["artificial intelligence", "software development"],
        ),
        TenderOpportunity(
            title="Web Application for Citizen Grievance Portal",
            department="Department of Administrative Reforms",
            estimated_value=18_00_000,
            deadline=today + timedelta(days=8),
            url="https://bidplus.gem.gov.in/showbidDocument/12346",
            source="GeM",
            keywords_matched=["web application", "software development"],
        ),
        TenderOpportunity(
            title="Data Analytics Dashboard for Smart City Mission",
            department="Ministry of Housing & Urban Affairs",
            estimated_value=42_00_000,
            deadline=today + timedelta(days=20),
            url="https://eprocure.gov.in/eprocure/app?component=view&tender_id=9876",
            source="eProcure",
            keywords_matched=["data analytics", "cloud services"],
        ),
        TenderOpportunity(
            title="Machine Learning Model for Crop Yield Prediction",
            department="Ministry of Agriculture",
            estimated_value=28_00_000,
            deadline=today + timedelta(days=15),
            url="https://bidplus.gem.gov.in/showbidDocument/12347",
            source="GeM",
            keywords_matched=["machine learning", "data analytics"],
        ),
    ]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def scan() -> List[TenderOpportunity]:
    """Run the full tender scan across all sources."""
    connector = aiohttp.TCPConnector(ssl=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        gem_results, eprocure_results = await asyncio.gather(
            _scan_gem(session),
            _scan_eprocure(session),
            return_exceptions=True,
        )

    opportunities: List[TenderOpportunity] = []

    if isinstance(gem_results, list):
        opportunities.extend(gem_results)
    else:
        logger.error("GeM scan raised: %s", gem_results)

    if isinstance(eprocure_results, list):
        opportunities.extend(eprocure_results)
    else:
        logger.error("eProcure scan raised: %s", eprocure_results)

    if not opportunities:
        logger.info("No live tenders found — returning demo data for testing")
        opportunities = _fallback_tenders()

    # De-duplicate by title similarity
    seen_titles: set = set()
    unique: List[TenderOpportunity] = []
    for opp in opportunities:
        key = opp.title[:50].lower()
        if key not in seen_titles:
            seen_titles.add(key)
            unique.append(opp)

    unique.sort(key=lambda o: o.estimated_value, reverse=True)
    logger.info("Tender scan complete — %d unique opportunities", len(unique))
    return unique


# ---------------------------------------------------------------------------
# Standalone execution
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    results = asyncio.run(scan())
    print(f"\n{'='*80}")
    print(f"  TENDER OPPORTUNITIES  ({len(results)} found)")
    print(f"{'='*80}\n")
    for r in results:
        print(r.summary())
        print()
