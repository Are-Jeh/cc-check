"""SQLite storage layer with caching support."""

import sqlite3
import json
import time
import pandas as pd
from config import DB_PATH, CACHE_TTL


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db():
    """Create tables if they don't exist."""
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS raw_data (
            source TEXT NOT NULL,
            indicator TEXT NOT NULL,
            date TEXT NOT NULL,
            value REAL,
            fetched_at REAL NOT NULL,
            PRIMARY KEY (source, indicator, date)
        );

        CREATE TABLE IF NOT EXISTS cache_meta (
            key TEXT PRIMARY KEY,
            fetched_at REAL NOT NULL,
            row_count INTEGER
        );

        CREATE TABLE IF NOT EXISTS analysis_results (
            indicator TEXT NOT NULL,
            market TEXT NOT NULL,
            lag_days INTEGER NOT NULL,
            pearson_r REAL,
            pearson_p REAL,
            spearman_r REAL,
            spearman_p REAL,
            kendall_r REAL,
            kendall_p REAL,
            granger_p REAL,
            mutual_info REAL,
            regime TEXT DEFAULT 'all',
            computed_at REAL NOT NULL,
            PRIMARY KEY (indicator, market, lag_days, regime)
        );

        CREATE INDEX IF NOT EXISTS idx_raw_source ON raw_data(source, indicator);
        CREATE INDEX IF NOT EXISTS idx_raw_date ON raw_data(date);
    """)
    conn.commit()
    conn.close()


def is_cache_valid(key: str) -> bool:
    """Check if cached data is still fresh."""
    conn = get_connection()
    row = conn.execute(
        "SELECT fetched_at FROM cache_meta WHERE key = ?", (key,)
    ).fetchone()
    conn.close()
    if row is None:
        return False
    return (time.time() - row[0]) < CACHE_TTL


def store_series(source: str, indicator: str, series: pd.Series):
    """Store a pandas Series (date-indexed, float values) into raw_data."""
    conn = get_connection()
    now = time.time()
    rows = [
        (source, indicator, str(dt.date()) if hasattr(dt, 'date') else str(dt), float(val), now)
        for dt, val in series.items()
        if pd.notna(val)
    ]
    conn.executemany(
        "INSERT OR REPLACE INTO raw_data (source, indicator, date, value, fetched_at) VALUES (?,?,?,?,?)",
        rows,
    )
    cache_key = f"{source}:{indicator}"
    conn.execute(
        "INSERT OR REPLACE INTO cache_meta (key, fetched_at, row_count) VALUES (?,?,?)",
        (cache_key, now, len(rows)),
    )
    conn.commit()
    conn.close()


def load_series(source: str, indicator: str) -> pd.Series:
    """Load a stored series back as a pandas Series with DatetimeIndex."""
    conn = get_connection()
    df = pd.read_sql_query(
        "SELECT date, value FROM raw_data WHERE source=? AND indicator=? ORDER BY date",
        conn,
        params=(source, indicator),
    )
    conn.close()
    if df.empty:
        return pd.Series(dtype=float)
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date")["value"]


def store_analysis(results: list[dict]):
    """Store analysis results."""
    conn = get_connection()
    now = time.time()
    for r in results:
        conn.execute(
            """INSERT OR REPLACE INTO analysis_results
            (indicator, market, lag_days, pearson_r, pearson_p, spearman_r, spearman_p,
             kendall_r, kendall_p, granger_p, mutual_info, regime, computed_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                r["indicator"], r["market"], r["lag_days"],
                r.get("pearson_r"), r.get("pearson_p"),
                r.get("spearman_r"), r.get("spearman_p"),
                r.get("kendall_r"), r.get("kendall_p"),
                r.get("granger_p"), r.get("mutual_info"),
                r.get("regime", "all"), now,
            ),
        )
    conn.commit()
    conn.close()


def load_all_analysis() -> pd.DataFrame:
    """Load all analysis results as a DataFrame."""
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM analysis_results", conn)
    conn.close()
    return df


def get_all_indicators() -> list[tuple[str, str]]:
    """Return list of (source, indicator) pairs stored."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT DISTINCT source, indicator FROM raw_data"
    ).fetchall()
    conn.close()
    return rows


init_db()
