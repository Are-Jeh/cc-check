"""
Job Matcher
============
Scans job boards for openings and matches them against a local contacts
database to find referral opportunities.

Data sources:
    - LinkedIn Jobs (via unofficial scraping — requires careful handling)
    - Company career pages (configurable list)
    - Naukri / Indeed (optional, same scraping approach)

The contacts database is a JSON file at data/contacts.json with the structure:
    [
        {
            "name": "Priya Sharma",
            "skills": ["Python", "Django", "AWS", "ML"],
            "experience_years": 5,
            "current_company": "Infosys",
            "preferred_locations": ["Bangalore", "Hyderabad", "Remote"],
            "email": "priya@example.com",
            "open_to_switch": true,
            "tier_preference": "tier1"
        },
        ...
    ]
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set

import aiohttp
from bs4 import BeautifulSoup

from opportunity_engine.config import JOB as CFG

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class Contact:
    name: str
    skills: List[str]
    experience_years: int
    current_company: str
    preferred_locations: List[str]
    email: str
    open_to_switch: bool = True
    tier_preference: str = "any"

    @classmethod
    def from_dict(cls, d: dict) -> "Contact":
        return cls(
            name=d.get("name", ""),
            skills=[s.lower() for s in d.get("skills", [])],
            experience_years=d.get("experience_years", 0),
            current_company=d.get("current_company", ""),
            preferred_locations=[loc.lower() for loc in d.get("preferred_locations", [])],
            email=d.get("email", ""),
            open_to_switch=d.get("open_to_switch", True),
            tier_preference=d.get("tier_preference", "any"),
        )


@dataclass
class JobListing:
    title: str
    company: str
    location: str
    required_skills: List[str]
    experience_range: tuple          # (min_years, max_years)
    url: str
    company_tier: str = "tier3"     # tier1 / tier2 / tier3
    source: str = "LinkedIn"

    @property
    def required_skills_lower(self) -> Set[str]:
        return {s.lower() for s in self.required_skills}


@dataclass
class JobMatchOpportunity:
    job_title: str
    company: str
    job_url: str
    candidate_name: str
    candidate_email: str
    match_score: int               # 0-100
    skill_overlap: List[str]
    estimated_referral_bonus: int  # INR
    match_details: str

    def summary(self) -> str:
        skills = ", ".join(self.skill_overlap[:5])
        return (
            f"JOB: {self.job_title} @ {self.company}\n"
            f"  Candidate: {self.candidate_name} ({self.candidate_email})\n"
            f"  Match score: {self.match_score}/100  |  Skills: {skills}\n"
            f"  Est. referral bonus: Rs {self.estimated_referral_bonus:,}\n"
            f"  {self.match_details}\n"
            f"  URL: {self.job_url}"
        )


# ---------------------------------------------------------------------------
# Contact database
# ---------------------------------------------------------------------------

def _load_contacts() -> List[Contact]:
    """Load contacts from the JSON database file."""
    path = Path(CFG.contacts_db_path)
    if not path.exists():
        logger.warning("Contacts DB not found at %s — using demo contacts", path)
        return _demo_contacts()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        contacts = [Contact.from_dict(d) for d in data if d.get("open_to_switch", True)]
        logger.info("Loaded %d contacts from %s", len(contacts), path)
        return contacts
    except Exception as exc:
        logger.error("Failed to load contacts: %s", exc)
        return _demo_contacts()


def _demo_contacts() -> List[Contact]:
    return [
        Contact("Aarav Mehta", ["python", "django", "aws", "docker"], 4, "TCS", ["bangalore", "remote"], "aarav@example.com"),
        Contact("Priya Sharma", ["python", "ml", "tensorflow", "data science"], 6, "Infosys", ["bangalore", "hyderabad"], "priya@example.com"),
        Contact("Rohan Gupta", ["react", "node.js", "typescript", "aws"], 3, "Wipro", ["noida", "gurgaon", "remote"], "rohan@example.com"),
        Contact("Sneha Reddy", ["java", "spring boot", "microservices", "kubernetes"], 7, "Cognizant", ["hyderabad", "bangalore"], "sneha@example.com"),
        Contact("Vikram Singh", ["devops", "terraform", "kubernetes", "aws", "gcp"], 5, "Accenture", ["pune", "remote"], "vikram@example.com"),
        Contact("Ananya Joshi", ["python", "fastapi", "postgresql", "redis"], 3, "Startup", ["bangalore", "remote"], "ananya@example.com"),
        Contact("Karan Patel", ["data engineering", "spark", "airflow", "python", "sql"], 5, "Amazon", ["bangalore"], "karan@example.com", tier_preference="tier1"),
    ]


# ---------------------------------------------------------------------------
# Company tier classification
# ---------------------------------------------------------------------------

_TIER1_COMPANIES: Set[str] = {
    "google", "meta", "amazon", "microsoft", "apple", "netflix",
    "uber", "stripe", "airbnb", "linkedin", "twitter", "x",
    "flipkart", "swiggy", "cred", "razorpay", "phonepe",
    "nvidia", "adobe", "salesforce", "oracle", "sap",
}

_TIER2_COMPANIES: Set[str] = {
    "atlassian", "thoughtspot", "freshworks", "zoho", "paytm",
    "ola", "meesho", "groww", "zerodha", "dream11",
    "postman", "browserstack", "hasura", "chargebee",
    "gojek", "grab", "shopify", "datadog", "cloudflare",
}


def _classify_tier(company: str) -> str:
    company_lower = company.lower().strip()
    for name in _TIER1_COMPANIES:
        if name in company_lower:
            return "tier1"
    for name in _TIER2_COMPANIES:
        if name in company_lower:
            return "tier2"
    return "tier3"


# ---------------------------------------------------------------------------
# LinkedIn scraper
# ---------------------------------------------------------------------------

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/121.0.0.0 Safari/537.36"
    ),
}


async def _fetch_linkedin_jobs(session: aiohttp.ClientSession) -> List[JobListing]:
    """
    Scrape LinkedIn's public jobs page (no login required for basic listings).

    LinkedIn's public job search at linkedin.com/jobs/search returns
    server-rendered HTML.  Logged-in API access would require OAuth or
    their official API partnership.

    For more reliable scraping, consider:
        - LinkedIn's official Jobs API (partner access required)
        - RapidAPI LinkedIn scrapers
        - Naukri.com or Indeed as alternatives
    """
    jobs: List[JobListing] = []

    for keyword in CFG.keywords:
        url = CFG.linkedin_job_search_url.format(keywords=keyword.replace(" ", "%20"))
        try:
            async with session.get(url, headers=_HEADERS, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    logger.warning("LinkedIn returned %d for '%s'", resp.status, keyword)
                    continue
                html = await resp.text()

            soup = BeautifulSoup(html, "html.parser")

            # LinkedIn public job cards
            cards = soup.select(
                "div.base-card, "
                "li.jobs-search__result-card, "
                "div[class*='job-search-card']"
            )

            for card in cards:
                title_el = card.select_one("h3, a[class*='title']")
                company_el = card.select_one("h4, a[class*='subtitle'], span[class*='company']")
                location_el = card.select_one("span[class*='location']")
                link_el = card.select_one("a[href*='/jobs/view']")

                if not title_el:
                    continue

                title = title_el.get_text(strip=True)
                company = company_el.get_text(strip=True) if company_el else "Unknown"
                location = location_el.get_text(strip=True) if location_el else "India"
                job_url = link_el.get("href", "") if link_el else ""

                # Infer required skills from job title and keyword
                inferred_skills = _infer_skills(title, keyword)

                tier = _classify_tier(company)

                jobs.append(JobListing(
                    title=title,
                    company=company,
                    location=location,
                    required_skills=inferred_skills,
                    experience_range=(2, 8),
                    url=job_url,
                    company_tier=tier,
                    source="LinkedIn",
                ))

            logger.info("LinkedIn '%s': found %d jobs", keyword, len(cards))

        except Exception as exc:
            logger.error("LinkedIn scrape failed for '%s': %s", keyword, exc)

    return jobs


def _infer_skills(title: str, search_keyword: str) -> List[str]:
    """Infer likely required skills from job title and search keyword."""
    skills: List[str] = []
    combined = f"{title} {search_keyword}".lower()

    skill_keywords = {
        "python": "python", "java": "java", "javascript": "javascript",
        "react": "react", "node": "node.js", "django": "django",
        "fastapi": "fastapi", "spring": "spring boot", "go ": "golang",
        "rust": "rust", "ml": "ml", "machine learning": "ml",
        "data scien": "data science", "devops": "devops",
        "kubernetes": "kubernetes", "docker": "docker",
        "aws": "aws", "gcp": "gcp", "azure": "azure",
        "terraform": "terraform", "sql": "sql", "spark": "spark",
        "tensorflow": "tensorflow", "pytorch": "pytorch",
        "typescript": "typescript", "full stack": "full stack",
        "backend": "backend", "frontend": "frontend",
    }

    for trigger, skill in skill_keywords.items():
        if trigger in combined:
            skills.append(skill)

    return skills if skills else [search_keyword.lower()]


# ---------------------------------------------------------------------------
# Fallback jobs
# ---------------------------------------------------------------------------

def _fallback_jobs() -> List[JobListing]:
    return [
        JobListing("Senior Python Developer", "Google", "Bangalore", ["python", "django", "aws", "docker"], (4, 8), "https://careers.google.com/jobs/123", "tier1"),
        JobListing("ML Engineer", "Flipkart", "Bangalore", ["python", "ml", "tensorflow", "data science"], (3, 7), "https://www.flipkartcareers.com/jobs/456", "tier1"),
        JobListing("Full Stack Developer", "Razorpay", "Bangalore, Remote", ["react", "node.js", "typescript", "aws"], (2, 5), "https://razorpay.com/careers/789", "tier1"),
        JobListing("Backend Engineer", "Groww", "Bangalore", ["java", "spring boot", "microservices", "kubernetes"], (3, 6), "https://groww.in/careers/101", "tier2"),
        JobListing("DevOps Engineer", "Meesho", "Bangalore, Remote", ["devops", "terraform", "kubernetes", "aws"], (3, 6), "https://meesho.io/careers/102", "tier2"),
        JobListing("Data Engineer", "PhonePe", "Bangalore", ["data engineering", "spark", "airflow", "python", "sql"], (4, 7), "https://phonepe.com/careers/103", "tier1"),
        JobListing("Python Backend Developer", "Postman", "Noida, Remote", ["python", "fastapi", "postgresql", "redis"], (2, 5), "https://postman.com/careers/104", "tier2"),
    ]


# ---------------------------------------------------------------------------
# Matching engine
# ---------------------------------------------------------------------------

def _match_score(contact: Contact, job: JobListing) -> int:
    """
    Compute a 0-100 match score between a contact and a job listing.

    Scoring breakdown:
        - Skill overlap:        0-50 points
        - Experience fit:       0-20 points
        - Location match:       0-20 points
        - Tier preference:      0-10 points
    """
    score = 0

    # Skill overlap (50 points max)
    job_skills = job.required_skills_lower
    contact_skills = set(contact.skills)
    if job_skills:
        overlap = contact_skills & job_skills
        skill_ratio = len(overlap) / len(job_skills)
        score += int(skill_ratio * 50)

    # Experience fit (20 points max)
    min_exp, max_exp = job.experience_range
    if min_exp <= contact.experience_years <= max_exp:
        score += 20
    elif contact.experience_years < min_exp:
        gap = min_exp - contact.experience_years
        score += max(0, 20 - gap * 7)
    else:
        gap = contact.experience_years - max_exp
        score += max(0, 20 - gap * 5)

    # Location match (20 points max)
    job_loc_lower = job.location.lower()
    if "remote" in job_loc_lower or any(loc in job_loc_lower for loc in contact.preferred_locations):
        score += 20
    elif any(loc in job_loc_lower for loc in ("india", "anywhere")):
        score += 10

    # Tier preference (10 points max)
    if contact.tier_preference == "any" or contact.tier_preference == job.company_tier:
        score += 10
    elif contact.tier_preference == "tier1" and job.company_tier == "tier2":
        score += 5

    return min(100, score)


def _match_all(contacts: List[Contact], jobs: List[JobListing]) -> List[JobMatchOpportunity]:
    """Match all contacts against all jobs, returning high-scoring pairs."""
    matches: List[JobMatchOpportunity] = []

    for job in jobs:
        best_contact: Optional[Contact] = None
        best_score = 0
        best_overlap: List[str] = []

        for contact in contacts:
            if not contact.open_to_switch:
                continue
            # Skip if candidate already works at this company
            if contact.current_company.lower() in job.company.lower():
                continue

            sc = _match_score(contact, job)
            if sc > best_score:
                best_score = sc
                best_contact = contact
                job_skills_lower = job.required_skills_lower
                best_overlap = [s for s in contact.skills if s in job_skills_lower]

        if best_contact and best_score >= CFG.min_match_score:
            bonus = CFG.referral_bonus_estimates.get(job.company_tier, 10_000)

            details_parts = []
            if best_score >= 80:
                details_parts.append("Strong match")
            elif best_score >= 60:
                details_parts.append("Good match")
            details_parts.append(f"{best_contact.experience_years}y exp at {best_contact.current_company}")

            matches.append(JobMatchOpportunity(
                job_title=job.title,
                company=job.company,
                job_url=job.url,
                candidate_name=best_contact.name,
                candidate_email=best_contact.email,
                match_score=best_score,
                skill_overlap=best_overlap,
                estimated_referral_bonus=bonus,
                match_details=" | ".join(details_parts),
            ))

    matches.sort(key=lambda m: m.match_score, reverse=True)
    return matches


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def scan() -> List[JobMatchOpportunity]:
    """Run the full job matching pipeline."""
    contacts = _load_contacts()
    if not contacts:
        logger.warning("No contacts loaded — nothing to match")
        return []

    connector = aiohttp.TCPConnector(ssl=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        jobs = await _fetch_linkedin_jobs(session)

    if not jobs:
        logger.info("No live jobs fetched — using demo job listings")
        jobs = _fallback_jobs()

    matches = _match_all(contacts, jobs)
    logger.info("Job matcher complete — %d matches above threshold", len(matches))
    return matches


# ---------------------------------------------------------------------------
# Standalone
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    results = asyncio.run(scan())
    print(f"\n{'='*80}")
    print(f"  JOB MATCH OPPORTUNITIES  ({len(results)} found)")
    print(f"{'='*80}\n")
    for r in results:
        print(r.summary())
        print()
