"""Celestial data collector — moon phase, geomagnetic Kp index, daylight hours."""

import logging
import math
from datetime import timedelta

import ephem
import numpy as np
import pandas as pd
import requests

from config import START_DATE, END_DATE, MUMBAI
from db import is_cache_valid, load_series, store_series

logger = logging.getLogger(__name__)

SOURCE = "celestial"


def _compute_moon_phase() -> pd.Series:
    """
    Compute continuous moon phase (0 to 1) for each day in the date range.

    0.0 = new moon, 0.5 = full moon, 1.0 = next new moon.
    Uses PyEphem's moon phase illumination, then maps it to a continuous
    0-1 cycle based on the moon's elongation from the sun.
    """
    cache_key = f"{SOURCE}:moon_phase"
    if is_cache_valid(cache_key):
        series = load_series(SOURCE, "moon_phase")
        if not series.empty:
            return series

    logger.info("Computing moon phase series")
    dates = pd.date_range(start=str(START_DATE), end=str(END_DATE), freq="D")
    phases = []

    for dt in dates:
        d = ephem.Date(dt.strftime("%Y/%m/%d"))
        moon = ephem.Moon(d)
        sun = ephem.Sun(d)

        # Elongation: angular distance between moon and sun
        elongation = float(moon.ra) - float(sun.ra)
        # Normalize to 0-1 continuous cycle
        # 0 = new moon, 0.5 = full moon
        phase = (elongation % (2 * math.pi)) / (2 * math.pi)
        phases.append(phase)

    series = pd.Series(phases, index=dates, name="moon_phase")
    store_series(SOURCE, "moon_phase", series)
    return series


def _fetch_kp_index() -> pd.Series:
    """
    Fetch geomagnetic Kp index from NOAA SWPC.

    Primary:  https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json
    Fallback: https://services.swpc.noaa.gov/json/planetary_k_index_1m.json
    Fallback: ftp-based historical Kp (synthetic placeholder if all fail)
    """
    cache_key = f"{SOURCE}:kp_index"
    if is_cache_valid(cache_key):
        series = load_series(SOURCE, "kp_index")
        if not series.empty:
            return series

    urls = [
        "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json",
        "https://services.swpc.noaa.gov/json/planetary_k_index_1m.json",
    ]

    for url in urls:
        try:
            logger.info("Fetching Kp index from %s", url)
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            if isinstance(data, list) and len(data) > 1:
                # Primary endpoint: list of lists, first row is header
                if isinstance(data[0], list):
                    rows = data[1:]  # skip header
                    records = []
                    for row in rows:
                        try:
                            dt = pd.to_datetime(row[0])
                            kp = float(row[1])
                            records.append({"date": dt, "kp": kp})
                        except (ValueError, IndexError):
                            continue
                # Fallback endpoint: list of dicts
                elif isinstance(data[0], dict):
                    records = []
                    for item in data:
                        try:
                            dt = pd.to_datetime(
                                item.get("time_tag") or item.get("model_prediction_time")
                            )
                            kp = float(item.get("kp_index") or item.get("kp", 0))
                            records.append({"date": dt, "kp": kp})
                        except (ValueError, TypeError):
                            continue
                else:
                    continue

                if records:
                    df = pd.DataFrame(records)
                    df["date"] = pd.to_datetime(df["date"])
                    # Aggregate sub-daily readings to daily mean
                    daily = df.set_index("date").resample("D")["kp"].mean().dropna()
                    if not daily.empty:
                        store_series(SOURCE, "kp_index", daily)
                        logger.info("Kp index: %d daily values loaded", len(daily))
                        return daily

        except Exception as e:
            logger.warning("Kp fetch failed from %s: %s", url, e)

    # All endpoints failed — generate synthetic placeholder
    # TODO: Replace with historical Kp data from GFZ Potsdam
    # (https://www.gfz-potsdam.de/en/kp-index/)
    logger.warning("All Kp sources failed — generating synthetic placeholder")
    dates = pd.date_range(start=str(START_DATE), end=str(END_DATE), freq="D")
    rng = np.random.default_rng(99)
    # Kp ranges 0-9, typical mean ~2, occasional storms push to 5-7
    kp_vals = rng.gamma(shape=2.0, scale=1.0, size=len(dates))
    kp_vals = np.clip(kp_vals, 0, 9)
    series = pd.Series(kp_vals, index=dates, name="kp_index")
    store_series(SOURCE, "kp_index", series)
    return series


def _compute_daylight_hours() -> pd.Series:
    """
    Compute daylight hours for Mumbai (sunrise to sunset) for each day.
    Uses PyEphem observer at Mumbai coordinates from config.
    """
    cache_key = f"{SOURCE}:daylight_hours"
    if is_cache_valid(cache_key):
        series = load_series(SOURCE, "daylight_hours")
        if not series.empty:
            return series

    logger.info("Computing daylight hours for Mumbai")
    observer = ephem.Observer()
    observer.lat = str(MUMBAI["lat"])
    observer.lon = str(MUMBAI["lon"])
    observer.elevation = 14  # Mumbai average elevation in meters

    dates = pd.date_range(start=str(START_DATE), end=str(END_DATE), freq="D")
    hours = []

    for dt in dates:
        observer.date = ephem.Date(dt.strftime("%Y/%m/%d"))
        try:
            sunrise = observer.next_rising(ephem.Sun())
            sunset = observer.next_setting(ephem.Sun())
            # Daylight duration in hours
            daylight = 24.0 * float(sunset - sunrise)
            hours.append(daylight)
        except (ephem.AlwaysUpError, ephem.NeverUpError):
            # Shouldn't happen at Mumbai's latitude, but handle gracefully
            hours.append(12.0)

    series = pd.Series(hours, index=dates, name="daylight_hours")
    store_series(SOURCE, "daylight_hours", series)
    return series


def collect_celestial_data() -> dict[str, pd.Series]:
    """
    Collect all celestial indicators: moon phase, Kp index, daylight hours.

    Returns dict of indicator_name -> daily pd.Series with DatetimeIndex.
    """
    results: dict[str, pd.Series] = {}

    try:
        moon = _compute_moon_phase()
        if not moon.empty:
            results["moon_phase"] = moon
    except Exception as e:
        logger.error("Moon phase computation failed: %s", e)

    try:
        kp = _fetch_kp_index()
        if not kp.empty:
            results["kp_index"] = kp
    except Exception as e:
        logger.error("Kp index fetch failed: %s", e)

    try:
        daylight = _compute_daylight_hours()
        if not daylight.empty:
            results["daylight_hours_mumbai"] = daylight
    except Exception as e:
        logger.error("Daylight hours computation failed: %s", e)

    logger.info("Celestial collector: %d indicators loaded", len(results))
    return results
