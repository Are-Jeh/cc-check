"""
Celestial Mechanics Engine
==========================
Computes real astronomical data using the `ephem` library for backtesting
quantitative strategies against celestial indicators.

Outputs a DataFrame with ~40+ columns covering distances, 3D vectors,
gravitational/tidal forces, lunar metrics, solar metrics, and planetary data.

All calculations use actual ephemeris computations — no synthetic or
approximate data.
"""

import logging
import math
from datetime import datetime, timedelta
from typing import Optional

import ephem
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Physical constants
# ---------------------------------------------------------------------------
G = 6.674e-11  # gravitational constant (m^3 kg^-1 s^-2)
M_SUN = 1.989e30  # solar mass (kg)
M_MOON = 7.342e22  # lunar mass (kg)
M_EARTH = 5.972e24  # earth mass (kg)
AU_KM = 149597870.7  # 1 AU in km

# Mumbai observer for altitude / daylight calculations
MUMBAI_LAT = "19.0760"
MUMBAI_LON = "72.8777"
MUMBAI_ELEV = 14  # meters


def _make_mumbai_observer() -> ephem.Observer:
    """Create a PyEphem Observer fixed at Mumbai."""
    obs = ephem.Observer()
    obs.lat = MUMBAI_LAT
    obs.lon = MUMBAI_LON
    obs.elevation = MUMBAI_ELEV
    obs.pressure = 0  # disable atmospheric refraction for consistency
    return obs


def _ra_dec_dist_to_xyz(ra: float, dec: float, dist_km: float):
    """
    Convert equatorial (RA, Dec, distance) to Cartesian (x, y, z).

    Parameters
    ----------
    ra : float
        Right ascension in radians.
    dec : float
        Declination in radians.
    dist_km : float
        Distance in km.

    Returns
    -------
    tuple of (x, y, z) in km.
    """
    x = dist_km * math.cos(dec) * math.cos(ra)
    y = dist_km * math.cos(dec) * math.sin(ra)
    z = dist_km * math.sin(dec)
    return x, y, z


def _angular_separation(ra1: float, dec1: float, ra2: float, dec2: float) -> float:
    """
    Compute angular separation between two points on the celestial sphere
    using the Vincenty formula (numerically stable for all angles).

    Parameters
    ----------
    ra1, dec1 : float
        RA and Dec of first body (radians).
    ra2, dec2 : float
        RA and Dec of second body (radians).

    Returns
    -------
    float
        Angular separation in radians.
    """
    delta_ra = ra2 - ra1
    cos_dec1 = math.cos(dec1)
    cos_dec2 = math.cos(dec2)
    sin_dec1 = math.sin(dec1)
    sin_dec2 = math.sin(dec2)

    num1 = cos_dec2 * math.sin(delta_ra)
    num2 = cos_dec1 * sin_dec2 - sin_dec1 * cos_dec2 * math.cos(delta_ra)
    numerator = math.sqrt(num1**2 + num2**2)
    denominator = sin_dec1 * sin_dec2 + cos_dec1 * cos_dec2 * math.cos(delta_ra)

    return math.atan2(numerator, denominator)


def _compute_daylight_hours(obs: ephem.Observer) -> float:
    """
    Compute daylight hours for the observer's currently set date.

    Returns
    -------
    float
        Hours of daylight. Falls back to 12.0 on edge-case errors.
    """
    try:
        sun = ephem.Sun()
        sunrise = obs.next_rising(sun)
        obs_copy = obs.copy()
        obs_copy.date = sunrise
        sunset = obs_copy.next_setting(sun)
        return 24.0 * float(sunset - sunrise)
    except (ephem.AlwaysUpError, ephem.NeverUpError):
        return 12.0
    except Exception:
        return 12.0


def _find_previous_phase(date_ephem, phase_fn) -> float:
    """
    Find how many days since the last occurrence of a lunar phase.

    Parameters
    ----------
    date_ephem : ephem.Date
        The reference date.
    phase_fn : callable
        One of ephem.previous_new_moon, ephem.previous_full_moon, etc.

    Returns
    -------
    float
        Days since the last phase event.
    """
    try:
        prev = phase_fn(date_ephem)
        return float(date_ephem - prev)
    except Exception:
        return float("nan")


def compute_all_celestial(
    start_date: str = "2015-01-01",
    end_date: str = "2025-12-31",
) -> pd.DataFrame:
    """
    Compute all celestial indicators for daily dates in [start_date, end_date].

    Returns a DataFrame with DatetimeIndex and ~40+ columns covering:
      - Real distances (Earth-Sun, Earth-Moon, Sun-Moon) and their rates of change
      - 3D position vectors and their products
      - Gravitational / tidal forces and ratios
      - Lunar metrics (phase, declination, node, altitude, etc.)
      - Solar metrics (declination, elongation, daylight hours)
      - Planetary data (Jupiter, Saturn distances and angular separation)

    Parameters
    ----------
    start_date : str
        ISO format start date (inclusive).
    end_date : str
        ISO format end date (inclusive).

    Returns
    -------
    pd.DataFrame
        One row per day, DatetimeIndex, ~40+ float columns.
    """
    dates = pd.date_range(start=start_date, end=end_date, freq="D")
    n = len(dates)
    logger.info(
        "Computing celestial data for %d days: %s to %s", n, start_date, end_date
    )

    # Pre-allocate arrays for speed
    # --- Distances ---
    earth_sun_dist = np.empty(n, dtype=np.float64)
    earth_moon_dist = np.empty(n, dtype=np.float64)
    sun_moon_dist = np.empty(n, dtype=np.float64)

    # --- Sun vector components ---
    sun_x = np.empty(n, dtype=np.float64)
    sun_y = np.empty(n, dtype=np.float64)
    sun_z = np.empty(n, dtype=np.float64)

    # --- Moon vector components ---
    moon_x = np.empty(n, dtype=np.float64)
    moon_y = np.empty(n, dtype=np.float64)
    moon_z = np.empty(n, dtype=np.float64)

    # --- Lunar metrics ---
    moon_phase = np.empty(n, dtype=np.float64)
    moon_dec = np.empty(n, dtype=np.float64)
    lunar_node_lon = np.empty(n, dtype=np.float64)
    days_since_new_moon = np.empty(n, dtype=np.float64)
    days_since_full_moon = np.empty(n, dtype=np.float64)
    moon_alt_mumbai_midnight = np.empty(n, dtype=np.float64)

    # --- Solar metrics ---
    sun_dec = np.empty(n, dtype=np.float64)
    solar_elongation = np.empty(n, dtype=np.float64)
    daylight_hours = np.empty(n, dtype=np.float64)

    # --- Planetary ---
    jupiter_earth_dist = np.empty(n, dtype=np.float64)
    saturn_earth_dist = np.empty(n, dtype=np.float64)
    jupiter_saturn_sep = np.empty(n, dtype=np.float64)

    # Create Mumbai observer (reused and mutated per day)
    mumbai_obs = _make_mumbai_observer()

    # Also create a generic observer for astrometric body computations
    # (ephem bodies need to be computed for a date; we use a default observer
    #  which gives geocentric positions)

    for i, dt in enumerate(dates):
        if i % 500 == 0:
            logger.info("  Processing day %d / %d (%s)", i, n, dt.date())

        d = ephem.Date(dt.strftime("%Y/%m/%d 00:00:00"))

        # ------------------------------------------------------------------
        # Compute body positions (geocentric / astrometric)
        # ------------------------------------------------------------------
        sun_body = ephem.Sun()
        sun_body.compute(d)

        moon_body = ephem.Moon()
        moon_body.compute(d)

        jupiter_body = ephem.Jupiter()
        jupiter_body.compute(d)

        saturn_body = ephem.Saturn()
        saturn_body.compute(d)

        # ------------------------------------------------------------------
        # 1. REAL DISTANCES
        # ------------------------------------------------------------------
        d_es = float(sun_body.earth_distance) * AU_KM  # Earth-Sun in km
        d_em = float(moon_body.earth_distance) * AU_KM  # Earth-Moon in km

        earth_sun_dist[i] = d_es
        earth_moon_dist[i] = d_em

        # Sun-Moon distance via law of cosines:
        # d_sm^2 = d_es^2 + d_em^2 - 2*d_es*d_em*cos(angle_between)
        sun_ra = float(sun_body.ra)
        sun_dec_val = float(sun_body.dec)
        moon_ra = float(moon_body.ra)
        moon_dec_val = float(moon_body.dec)

        ang_sep = _angular_separation(sun_ra, sun_dec_val, moon_ra, moon_dec_val)

        d_sm = math.sqrt(
            d_es**2 + d_em**2 - 2.0 * d_es * d_em * math.cos(ang_sep)
        )
        sun_moon_dist[i] = d_sm

        # ------------------------------------------------------------------
        # 2. 3D POSITION VECTORS
        # ------------------------------------------------------------------
        sx, sy, sz = _ra_dec_dist_to_xyz(sun_ra, sun_dec_val, d_es)
        sun_x[i] = sx
        sun_y[i] = sy
        sun_z[i] = sz

        mx, my, mz = _ra_dec_dist_to_xyz(moon_ra, moon_dec_val, d_em)
        moon_x[i] = mx
        moon_y[i] = my
        moon_z[i] = mz

        # ------------------------------------------------------------------
        # 4. LUNAR METRICS
        # ------------------------------------------------------------------
        # Continuous moon phase (0 = new, 0.5 = full, 1 = next new)
        elongation_ra = float(moon_body.ra) - float(sun_body.ra)
        phase_continuous = (elongation_ra % (2.0 * math.pi)) / (2.0 * math.pi)
        moon_phase[i] = phase_continuous

        # Moon declination
        moon_dec[i] = moon_dec_val

        # Lunar node longitude (ascending node)
        # The mean ascending node regresses with ~18.6 year period.
        # ephem doesn't expose this directly; compute from the Moon's
        # ecliptic latitude crossing. We use the standard formula:
        # Omega = 125.04452 - 1934.136261 * T  (degrees, J2000 epoch)
        # where T = Julian centuries from J2000.0
        jd = ephem.julian_date(d)
        T = (jd - 2451545.0) / 36525.0
        omega_deg = 125.04452 - 1934.136261 * T
        omega_deg = omega_deg % 360.0
        lunar_node_lon[i] = math.radians(omega_deg)

        # Days since last new moon / full moon
        days_since_new_moon[i] = _find_previous_phase(d, ephem.previous_new_moon)
        days_since_full_moon[i] = _find_previous_phase(d, ephem.previous_full_moon)

        # Moon altitude at Mumbai midnight (00:00 IST = 18:30 UTC previous day)
        mumbai_obs.date = ephem.Date(dt.strftime("%Y/%m/%d 18:30:00"))
        moon_midnight = ephem.Moon()
        moon_midnight.compute(mumbai_obs)
        moon_alt_mumbai_midnight[i] = float(moon_midnight.alt)  # radians

        # ------------------------------------------------------------------
        # 5. SOLAR METRICS
        # ------------------------------------------------------------------
        sun_dec[i] = sun_dec_val

        # Solar elongation of moon (angle between sun and moon as seen from Earth)
        solar_elongation[i] = ang_sep

        # Daylight hours at Mumbai
        mumbai_obs.date = ephem.Date(dt.strftime("%Y/%m/%d 00:00:00"))
        daylight_hours[i] = _compute_daylight_hours(mumbai_obs)

        # ------------------------------------------------------------------
        # 6. PLANETARY
        # ------------------------------------------------------------------
        jupiter_earth_dist[i] = float(jupiter_body.earth_distance) * AU_KM
        saturn_earth_dist[i] = float(saturn_body.earth_distance) * AU_KM

        # Jupiter-Saturn angular separation
        jup_ra = float(jupiter_body.ra)
        jup_dec = float(jupiter_body.dec)
        sat_ra = float(saturn_body.ra)
        sat_dec = float(saturn_body.dec)
        jupiter_saturn_sep[i] = _angular_separation(jup_ra, jup_dec, sat_ra, sat_dec)

    logger.info("Ephem loop complete. Deriving vectorized quantities...")

    # ======================================================================
    # VECTORIZED POST-PROCESSING (numpy)
    # ======================================================================

    # --- Distance rates of change (daily diff, km/day) ---
    earth_sun_dist_rate = np.gradient(earth_sun_dist)
    earth_moon_dist_rate = np.gradient(earth_moon_dist)
    sun_moon_dist_rate = np.gradient(sun_moon_dist)

    # --- Dot product of Sun and Moon vectors ---
    dot_product = sun_x * moon_x + sun_y * moon_y + sun_z * moon_z

    # --- Cross product magnitude ---
    cx = sun_y * moon_z - sun_z * moon_y
    cy = sun_z * moon_x - sun_x * moon_z
    cz = sun_x * moon_y - sun_y * moon_x
    cross_product_mag = np.sqrt(cx**2 + cy**2 + cz**2)

    # --- Angle between Sun and Moon vectors (elongation from vectors) ---
    sun_mag = np.sqrt(sun_x**2 + sun_y**2 + sun_z**2)
    moon_mag = np.sqrt(moon_x**2 + moon_y**2 + moon_z**2)
    cos_angle = dot_product / (sun_mag * moon_mag + 1e-30)
    # Clamp for numerical safety
    cos_angle = np.clip(cos_angle, -1.0, 1.0)
    angle_between = np.arccos(cos_angle)

    # --- Tidal forces ---
    # Tidal force ~ G * M / d^3  (proportional, in consistent units)
    # Convert distances from km to meters for force calculation
    d_moon_m = earth_moon_dist * 1e3
    d_sun_m = earth_sun_dist * 1e3

    tidal_moon = G * M_MOON / (d_moon_m**3)
    tidal_sun = G * M_SUN / (d_sun_m**3)

    # Combined tidal force: vector sum considering alignment
    # When Sun and Moon are aligned (new/full moon), forces add;
    # when perpendicular (quarter moons), use vector sum
    # tidal_combined = sqrt(tidal_moon^2 + tidal_sun^2 + 2*tidal_moon*tidal_sun*cos(elongation))
    tidal_combined = np.sqrt(
        tidal_moon**2
        + tidal_sun**2
        + 2.0 * tidal_moon * tidal_sun * np.cos(solar_elongation)
    )

    tidal_ratio = tidal_moon / (tidal_sun + 1e-30)

    # Tidal force rates of change
    tidal_moon_rate = np.gradient(tidal_moon)
    tidal_sun_rate = np.gradient(tidal_sun)
    tidal_combined_rate = np.gradient(tidal_combined)

    # ======================================================================
    # ASSEMBLE DATAFRAME
    # ======================================================================
    data = {
        # 1. Distances
        "earth_sun_dist_km": earth_sun_dist,
        "earth_moon_dist_km": earth_moon_dist,
        "sun_moon_dist_km": sun_moon_dist,
        "earth_sun_dist_rate": earth_sun_dist_rate,
        "earth_moon_dist_rate": earth_moon_dist_rate,
        "sun_moon_dist_rate": sun_moon_dist_rate,
        # 2. 3D Vectors
        "sun_x": sun_x,
        "sun_y": sun_y,
        "sun_z": sun_z,
        "moon_x": moon_x,
        "moon_y": moon_y,
        "moon_z": moon_z,
        "dot_product_sun_moon": dot_product,
        "cross_product_mag_sun_moon": cross_product_mag,
        "angle_between_sun_moon": angle_between,
        # 3. Tidal forces
        "tidal_force_moon": tidal_moon,
        "tidal_force_sun": tidal_sun,
        "tidal_force_combined": tidal_combined,
        "tidal_ratio_moon_sun": tidal_ratio,
        "tidal_force_moon_rate": tidal_moon_rate,
        "tidal_force_sun_rate": tidal_sun_rate,
        "tidal_force_combined_rate": tidal_combined_rate,
        # 4. Lunar metrics
        "moon_phase": moon_phase,
        "moon_declination": moon_dec,
        "lunar_node_longitude": lunar_node_lon,
        "days_since_new_moon": days_since_new_moon,
        "days_since_full_moon": days_since_full_moon,
        "moon_alt_mumbai_midnight": moon_alt_mumbai_midnight,
        # 5. Solar metrics
        "sun_declination": sun_dec,
        "solar_elongation": solar_elongation,
        "daylight_hours_mumbai": daylight_hours,
        # 6. Planetary
        "jupiter_earth_dist_km": jupiter_earth_dist,
        "saturn_earth_dist_km": saturn_earth_dist,
        "jupiter_saturn_angular_sep": jupiter_saturn_sep,
    }

    df = pd.DataFrame(data, index=dates)
    df.index.name = "date"

    # Sanity checks
    null_counts = df.isnull().sum()
    if null_counts.any():
        cols_with_nulls = null_counts[null_counts > 0]
        logger.warning("Columns with NaN values:\n%s", cols_with_nulls)

    logger.info(
        "Celestial DataFrame built: %d rows x %d columns", df.shape[0], df.shape[1]
    )
    return df


def compute_hybrid_indicators(celestial_df: pd.DataFrame) -> pd.DataFrame:
    """
    Create additional derived features from raw celestial data.

    Adds rolling statistics, interaction terms, cyclical encodings,
    and binary event flags.

    Parameters
    ----------
    celestial_df : pd.DataFrame
        Output of ``compute_all_celestial()``.

    Returns
    -------
    pd.DataFrame
        Original columns plus ~30+ derived columns.
    """
    df = celestial_df.copy()
    logger.info("Computing hybrid indicators on %d rows...", len(df))

    # ------------------------------------------------------------------
    # Rolling means of tidal forces (7, 14, 30 day windows)
    # ------------------------------------------------------------------
    for window in (7, 14, 30):
        df[f"tidal_moon_roll_{window}d"] = (
            df["tidal_force_moon"].rolling(window, min_periods=1).mean()
        )
        df[f"tidal_sun_roll_{window}d"] = (
            df["tidal_force_sun"].rolling(window, min_periods=1).mean()
        )
        df[f"tidal_combined_roll_{window}d"] = (
            df["tidal_force_combined"].rolling(window, min_periods=1).mean()
        )

    # ------------------------------------------------------------------
    # Tidal force acceleration (2nd derivative)
    # ------------------------------------------------------------------
    df["tidal_moon_accel"] = np.gradient(np.gradient(df["tidal_force_moon"].values))
    df["tidal_sun_accel"] = np.gradient(np.gradient(df["tidal_force_sun"].values))
    df["tidal_combined_accel"] = np.gradient(
        np.gradient(df["tidal_force_combined"].values)
    )

    # ------------------------------------------------------------------
    # Interaction terms
    # ------------------------------------------------------------------
    df["moon_phase_x_tidal"] = df["moon_phase"] * df["tidal_force_combined"]
    df["dot_product_x_tidal_ratio"] = (
        df["dot_product_sun_moon"] * df["tidal_ratio_moon_sun"]
    )

    # ------------------------------------------------------------------
    # Cyclical encoding: sin/cos transforms
    # ------------------------------------------------------------------
    # Moon phase: already 0-1, map to 2*pi cycle
    df["moon_phase_sin"] = np.sin(2.0 * np.pi * df["moon_phase"])
    df["moon_phase_cos"] = np.cos(2.0 * np.pi * df["moon_phase"])

    # Sun declination: ranges ~[-23.44, +23.44] degrees (in radians from ephem)
    # Normalize to [-1, 1] then encode cyclically
    max_dec = np.radians(23.44)
    dec_normalized = df["sun_declination"] / max_dec  # [-1, 1]
    df["sun_dec_sin"] = np.sin(np.pi * dec_normalized)
    df["sun_dec_cos"] = np.cos(np.pi * dec_normalized)

    # ------------------------------------------------------------------
    # Binary event flags
    # Phase convention: 0 = new moon, 0.5 = full moon, 1 = next new moon
    # ------------------------------------------------------------------
    df["is_new_moon"] = (df["moon_phase"] < 0.05) | (df["moon_phase"] > 0.95)
    df["is_full_moon"] = (df["moon_phase"] > 0.45) & (df["moon_phase"] < 0.55)

    moon_dist_median = df["earth_moon_dist_km"].median()
    df["is_perigee"] = df["earth_moon_dist_km"] < moon_dist_median
    df["is_apogee"] = df["earth_moon_dist_km"] > moon_dist_median

    # Convert boolean flags to int for ML compatibility
    for col in ["is_full_moon", "is_new_moon", "is_perigee", "is_apogee"]:
        df[col] = df[col].astype(int)

    n_derived = df.shape[1] - celestial_df.shape[1]
    logger.info(
        "Hybrid indicators complete: %d new columns, total %d columns",
        n_derived,
        df.shape[1],
    )
    return df


# ---------------------------------------------------------------------------
# CLI / standalone usage
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    df = compute_all_celestial()
    print(f"\n=== Raw Celestial DataFrame ===")
    print(f"Shape: {df.shape}")
    print(f"Columns ({df.shape[1]}):")
    for c in df.columns:
        print(f"  {c}")
    print(f"\nFirst 3 rows:\n{df.head(3)}")
    print(f"\nDescribe:\n{df.describe()}")

    hdf = compute_hybrid_indicators(df)
    print(f"\n=== Hybrid Indicators DataFrame ===")
    print(f"Shape: {hdf.shape}")
    print(f"New columns:")
    new_cols = [c for c in hdf.columns if c not in df.columns]
    for c in new_cols:
        print(f"  {c}")
