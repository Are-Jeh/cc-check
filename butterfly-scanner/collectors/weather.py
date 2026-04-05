"""Weather data collector — Mumbai temperature/humidity, Delhi AQI."""

import logging
from datetime import datetime

import pandas as pd
import requests

from config import START_DATE, END_DATE, MUMBAI, DELHI, OPENAQ_KEY
from db import is_cache_valid, load_series, store_series

logger = logging.getLogger(__name__)

SOURCE = "weather"


def _fetch_mumbai_weather() -> dict[str, pd.Series]:
    """
    Fetch daily temperature and humidity for Mumbai using meteostat.

    Uses meteostat.Point for Mumbai coordinates and meteostat.Daily
    for the date range defined in config.
    """
    results: dict[str, pd.Series] = {}

    temp_cached = is_cache_valid(f"{SOURCE}:mumbai_temp")
    hum_cached = is_cache_valid(f"{SOURCE}:mumbai_humidity")

    if temp_cached and hum_cached:
        logger.info("Loading Mumbai weather from cache")
        temp = load_series(SOURCE, "mumbai_temp")
        hum = load_series(SOURCE, "mumbai_humidity")
        if not temp.empty:
            results["mumbai_temp"] = temp
        if not hum.empty:
            results["mumbai_humidity"] = hum
        return results

    try:
        from meteostat import Point, Daily

        mumbai_point = Point(MUMBAI["lat"], MUMBAI["lon"], 14)

        data = Daily(
            mumbai_point,
            start=datetime(START_DATE.year, START_DATE.month, START_DATE.day),
            end=datetime(END_DATE.year, END_DATE.month, END_DATE.day),
        )
        df = data.fetch()

        if df.empty:
            logger.warning("Meteostat returned no data for Mumbai")
            return results

        # tavg = average daily temperature (C)
        if "tavg" in df.columns:
            temp_series = df["tavg"].dropna()
            temp_series.index = pd.to_datetime(temp_series.index)
            store_series(SOURCE, "mumbai_temp", temp_series)
            results["mumbai_temp"] = temp_series
            logger.info("Mumbai temp: %d daily values", len(temp_series))

        # rhum = relative humidity (%)
        # meteostat may not always have humidity; fall back to other columns
        hum_col = None
        for col in ["rhum", "humidity"]:
            if col in df.columns:
                hum_col = col
                break

        if hum_col is not None:
            hum_series = df[hum_col].dropna()
            hum_series.index = pd.to_datetime(hum_series.index)
            store_series(SOURCE, "mumbai_humidity", hum_series)
            results["mumbai_humidity"] = hum_series
            logger.info("Mumbai humidity: %d daily values", len(hum_series))
        else:
            logger.warning("No humidity column found in meteostat data")

    except ImportError:
        logger.error(
            "meteostat not installed. Install with: pip install meteostat"
        )
    except Exception as e:
        logger.error("Mumbai weather fetch failed: %s", e)

    return results


def _fetch_delhi_aqi() -> pd.Series:
    """
    Fetch Delhi AQI (PM2.5) from OpenAQ API v2.

    Uses /v2/measurements endpoint. If OPENAQ_KEY is set, uses it;
    otherwise tries unauthenticated (rate-limited).
    """
    cache_key = f"{SOURCE}:delhi_aqi"
    if is_cache_valid(cache_key):
        series = load_series(SOURCE, "delhi_aqi")
        if not series.empty:
            return series

    logger.info("Fetching Delhi AQI from OpenAQ")

    headers = {"Accept": "application/json"}
    if OPENAQ_KEY:
        headers["X-API-Key"] = OPENAQ_KEY

    all_records = []
    base_url = "https://api.openaq.org/v2/measurements"

    # OpenAQ paginates, fetch in chunks by date range to stay within limits
    # Process year by year to avoid huge payloads
    current_start = START_DATE
    while current_start < END_DATE:
        # Chunk by 90 days to keep responses manageable
        chunk_end = min(
            current_start + pd.Timedelta(days=90),
            pd.Timestamp(str(END_DATE)),
        )

        params = {
            "city": "Delhi",
            "country": "IN",
            "parameter": "pm25",
            "date_from": str(current_start),
            "date_to": str(chunk_end.date() if hasattr(chunk_end, "date") else chunk_end),
            "limit": 10000,
            "order_by": "datetime",
            "sort": "asc",
        }

        try:
            resp = requests.get(base_url, params=params, headers=headers, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            for result in data.get("results", []):
                try:
                    dt = pd.to_datetime(result["date"]["utc"]).date()
                    val = float(result["value"])
                    if val >= 0:  # filter negative readings
                        all_records.append({"date": dt, "pm25": val})
                except (KeyError, ValueError, TypeError):
                    continue

        except Exception as e:
            logger.warning(
                "OpenAQ fetch failed for %s to %s: %s",
                current_start, chunk_end, e,
            )

        current_start = chunk_end
        if hasattr(current_start, "date"):
            current_start = current_start.date()

    if not all_records:
        logger.warning("No Delhi AQI data retrieved from OpenAQ")
        return pd.Series(dtype=float)

    df = pd.DataFrame(all_records)
    df["date"] = pd.to_datetime(df["date"])
    # Average multiple readings per day
    daily = df.groupby("date")["pm25"].mean()
    daily.index = pd.to_datetime(daily.index)
    daily = daily.sort_index()

    store_series(SOURCE, "delhi_aqi", daily)
    logger.info("Delhi AQI: %d daily values", len(daily))
    return daily


def collect_weather_data() -> dict[str, pd.Series]:
    """
    Collect all weather indicators: Mumbai temp/humidity, Delhi AQI.

    Returns dict of indicator_name -> daily pd.Series with DatetimeIndex.
    If any API fails, logs a warning and returns whatever data was collected
    (never crashes).
    """
    results: dict[str, pd.Series] = {}

    # Mumbai weather
    try:
        mumbai = _fetch_mumbai_weather()
        results.update(mumbai)
    except Exception as e:
        logger.error("Mumbai weather collection failed: %s", e)

    # Delhi AQI
    try:
        aqi = _fetch_delhi_aqi()
        if not aqi.empty:
            results["delhi_aqi_pm25"] = aqi
    except Exception as e:
        logger.error("Delhi AQI collection failed: %s", e)

    logger.info("Weather collector: %d indicators loaded", len(results))
    return results
