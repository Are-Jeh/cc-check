"""Digital signals collector — Google Trends, Wikipedia pageviews."""

import logging
import time as _time

import pandas as pd
import requests

from config import START_DATE, END_DATE, GTRENDS_KEYWORDS, WIKI_PAGES
from db import is_cache_valid, load_series, store_series

logger = logging.getLogger(__name__)


def _fetch_google_trends() -> dict[str, pd.Series]:
    """
    Fetch Google Trends interest-over-time for keywords defined in config.

    pytrends returns weekly data; we interpolate to daily after fetching.
    Keywords are batched in groups of 5 (pytrends limit) with sleep
    between requests to avoid rate-limiting (HTTP 429).
    """
    source = "gtrends"
    results: dict[str, pd.Series] = {}

    # Check if all keywords are cached
    all_cached = all(
        is_cache_valid(f"{source}:{kw}") for kw in GTRENDS_KEYWORDS
    )
    if all_cached:
        logger.info("Loading Google Trends from cache")
        for kw in GTRENDS_KEYWORDS:
            series = load_series(source, kw)
            if not series.empty:
                results[f"gtrends_{kw}"] = series
        return results

    try:
        from pytrends.request import TrendReq

        pytrends = TrendReq(hl="en-US", tz=330)  # IST = UTC+5:30 = 330 min
    except ImportError:
        logger.error("pytrends not installed. Install with: pip install pytrends")
        return results
    except Exception as e:
        logger.error("Failed to initialize pytrends: %s", e)
        return results

    timeframe = f"{START_DATE} {END_DATE}"

    # Batch keywords in groups of 5
    batches = [
        GTRENDS_KEYWORDS[i : i + 5]
        for i in range(0, len(GTRENDS_KEYWORDS), 5)
    ]

    for batch_idx, batch in enumerate(batches):
        if batch_idx > 0:
            # Sleep between batches to avoid rate limiting
            logger.info("Sleeping 15s between Google Trends batches...")
            _time.sleep(15)

        try:
            pytrends.build_payload(batch, cat=0, timeframe=timeframe, geo="IN")
            weekly_df = pytrends.interest_over_time()

            if weekly_df.empty:
                logger.warning("No Google Trends data for batch: %s", batch)
                continue

            # Drop the 'isPartial' column if present
            if "isPartial" in weekly_df.columns:
                weekly_df = weekly_df.drop(columns=["isPartial"])

            for kw in batch:
                if kw not in weekly_df.columns:
                    logger.warning("Keyword '%s' not in response", kw)
                    continue

                weekly_series = weekly_df[kw].astype(float)

                # Interpolate weekly -> daily using cubic method
                daily_index = pd.date_range(
                    start=weekly_series.index.min(),
                    end=weekly_series.index.max(),
                    freq="D",
                )
                daily_series = (
                    weekly_series
                    .reindex(daily_index)
                    .interpolate(method="cubic")
                )
                daily_series = daily_series.dropna()

                store_series(source, kw, daily_series)
                results[f"gtrends_{kw}"] = daily_series
                logger.info(
                    "Google Trends '%s': %d daily values", kw, len(daily_series)
                )

        except Exception as e:
            logger.error("Google Trends batch %s failed: %s", batch, e)
            # Sleep extra on error (likely rate-limited)
            _time.sleep(30)

    return results


def _fetch_wikipedia_pageviews() -> dict[str, pd.Series]:
    """
    Fetch daily Wikipedia pageviews for pages defined in config.

    Uses the Wikimedia REST API:
    https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/
        en.wikipedia/all-access/all-agents/{page}/daily/{start}/{end}
    """
    source = "wikipedia"
    results: dict[str, pd.Series] = {}

    # Check cache
    all_cached = all(
        is_cache_valid(f"{source}:{page}") for page in WIKI_PAGES
    )
    if all_cached:
        logger.info("Loading Wikipedia pageviews from cache")
        for page in WIKI_PAGES:
            series = load_series(source, page)
            if not series.empty:
                results[f"wiki_{page}"] = series
        return results

    start_str = START_DATE.strftime("%Y%m%d")
    end_str = END_DATE.strftime("%Y%m%d")

    headers = {
        "User-Agent": "ButterflyScanner/1.0 (research project; contact: none)",
        "Accept": "application/json",
    }

    for page in WIKI_PAGES:
        url = (
            f"https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
            f"en.wikipedia/all-access/all-agents/{page}/daily/{start_str}/{end_str}"
        )

        try:
            logger.info("Fetching Wikipedia pageviews for '%s'", page)
            resp = requests.get(url, headers=headers, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            items = data.get("items", [])
            if not items:
                logger.warning("No pageview data for '%s'", page)
                continue

            records = []
            for item in items:
                try:
                    # timestamp format: "2020010100" (YYYYMMDDHH)
                    dt = pd.to_datetime(item["timestamp"][:8], format="%Y%m%d")
                    views = int(item["views"])
                    records.append({"date": dt, "views": views})
                except (KeyError, ValueError):
                    continue

            if not records:
                continue

            df = pd.DataFrame(records)
            series = df.set_index("date")["views"].sort_index().astype(float)

            store_series(source, page, series)
            results[f"wiki_{page}"] = series
            logger.info("Wikipedia '%s': %d daily values", page, len(series))

        except Exception as e:
            logger.error("Wikipedia pageviews for '%s' failed: %s", page, e)

        # Small delay between requests to be polite
        _time.sleep(1)

    return results


def collect_digital_data() -> dict[str, pd.Series]:
    """
    Collect all digital signal indicators: Google Trends, Wikipedia pageviews.

    Returns dict of indicator_name -> daily pd.Series with DatetimeIndex.
    """
    results: dict[str, pd.Series] = {}

    try:
        trends = _fetch_google_trends()
        results.update(trends)
    except Exception as e:
        logger.error("Google Trends collection failed: %s", e)

    try:
        wiki = _fetch_wikipedia_pageviews()
        results.update(wiki)
    except Exception as e:
        logger.error("Wikipedia pageview collection failed: %s", e)

    logger.info("Digital collector: %d indicators loaded", len(results))
    return results
