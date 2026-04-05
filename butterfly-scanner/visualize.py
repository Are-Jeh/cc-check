#!/usr/bin/env python3
"""Visual correlation explorer — see patterns with your own eyes."""

import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import yfinance as yf
import ephem
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.gridspec import GridSpec
from datetime import date, datetime, timedelta
from pathlib import Path

OUT_DIR = Path(__file__).parent / "charts"
OUT_DIR.mkdir(exist_ok=True)

START = "2020-01-01"
END = "2025-12-31"

print("Fetching data...")

# ── FETCH MARKET DATA ──
tickers = {
    "Gold": "GC=F",
    "Silver": "SI=F",
    "Nifty 50": "^NSEI",
    "BankNifty": "^NSEBANK",
    "USD/INR": "INR=X",
    "Crude Oil": "CL=F",
    "S&P 500": "^GSPC",
    "India VIX": "^INDIAVIX",
    "US 10Y Yield": "^TNX",
    "DXY (Dollar Index)": "DX-Y.NYB",
}

prices = {}
for name, sym in tickers.items():
    print(f"  {name}...", end=" ")
    try:
        df = yf.download(sym, start=START, end=END, progress=False, auto_adjust=True)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        s = df["Close"].squeeze()
        s.index = pd.to_datetime(s.index)
        prices[name] = s
        print(f"{len(s)} days")
    except Exception as e:
        print(f"FAILED: {e}")

# ── COMPUTE CELESTIAL DATA ──
print("Computing celestial data...")

dates = pd.date_range(START, END, freq="D")

# Moon phase (0=new, 0.5=full, 1=new again)
moon_phase = []
for d in dates:
    m = ephem.Moon(d.strftime("%Y/%m/%d"))
    moon_phase.append(m.phase / 100.0)  # 0-1
moon_series = pd.Series(moon_phase, index=dates, name="Moon Phase")

# Sun-Earth distance (AU)
sun_dist = []
for d in dates:
    s = ephem.Sun(d.strftime("%Y/%m/%d"))
    sun_dist.append(float(s.earth_distance))  # in AU
sun_dist_series = pd.Series(sun_dist, index=dates, name="Sun Distance (AU)")

# Moon-Earth distance
moon_dist = []
for d in dates:
    m = ephem.Moon(d.strftime("%Y/%m/%d"))
    moon_dist.append(float(m.earth_distance) * 149597870.7)  # convert AU to km
moon_dist_series = pd.Series(moon_dist, index=dates, name="Moon Distance (km)")

# Mumbai daylight hours
mumbai = ephem.Observer()
mumbai.lat = "19.0760"
mumbai.lon = "72.8777"
daylight = []
for d in dates:
    mumbai.date = d.strftime("%Y/%m/%d")
    try:
        rise = mumbai.next_rising(ephem.Sun())
        sett = mumbai.next_setting(ephem.Sun())
        daylight.append((sett - rise) * 24)
    except Exception:
        daylight.append(12.0)
daylight_series = pd.Series(daylight, index=dates, name="Daylight Hours")

# ── COMPUTE RETURNS ──
nifty_ret = prices.get("Nifty 50", pd.Series(dtype=float)).pct_change().dropna()
nifty_ret.name = "Nifty Daily Return"

# ── NORMALIZE FUNCTION ──
def normalize(s):
    """Min-max normalize to 0-1 for overlay comparison."""
    mn, mx = s.min(), s.max()
    if mx == mn:
        return s * 0
    return (s - mn) / (mx - mn)


print("Generating charts...")

# ═══════════════════════════════════════════════════════════════════════
# CHART 1: The Big Picture — All prices normalized on one chart
# ═══════════════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(18, 8))
for name in ["Gold", "Silver", "Nifty 50", "USD/INR", "Crude Oil"]:
    if name in prices:
        ax.plot(normalize(prices[name]), label=name, linewidth=1.2)
ax.set_title("All Assets Normalized (0-1) — Do They Move Together?", fontsize=16, fontweight="bold")
ax.legend(loc="upper left", fontsize=11)
ax.set_xlabel("Date")
ax.set_ylabel("Normalized Price")
ax.grid(True, alpha=0.3)
ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
ax.xaxis.set_major_locator(mdates.MonthLocator(interval=6))
plt.xticks(rotation=45)
plt.tight_layout()
fig.savefig(OUT_DIR / "01_all_assets_normalized.png", dpi=150)
plt.close()
print("  01_all_assets_normalized.png")

# ═══════════════════════════════════════════════════════════════════════
# CHART 2: Gold vs Moon Phase
# ═══════════════════════════════════════════════════════════════════════
fig, ax1 = plt.subplots(figsize=(18, 7))
ax2 = ax1.twinx()

if "Gold" in prices:
    ax1.plot(prices["Gold"], color="#FFD700", linewidth=1.5, label="Gold Price ($)")
    ax1.set_ylabel("Gold Price ($)", color="#FFD700", fontsize=12)

ax2.fill_between(moon_series.index, 0, moon_series.values, alpha=0.15, color="blue", label="Moon Phase")
ax2.plot(moon_series, color="blue", linewidth=0.5, alpha=0.5)
ax2.set_ylabel("Moon Phase (0=New, 1=Full)", color="blue", fontsize=12)
ax2.set_ylim(0, 1.1)

ax1.set_title("Gold Price vs Moon Phase — Any Rhythm?", fontsize=16, fontweight="bold")
ax1.grid(True, alpha=0.3)
ax1.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
ax1.xaxis.set_major_locator(mdates.MonthLocator(interval=6))
plt.xticks(rotation=45)
plt.tight_layout()
fig.savefig(OUT_DIR / "02_gold_vs_moon.png", dpi=150)
plt.close()
print("  02_gold_vs_moon.png")

# ═══════════════════════════════════════════════════════════════════════
# CHART 3: Nifty vs Sun-Earth Distance & Moon Distance
# ═══════════════════════════════════════════════════════════════════════
fig, axes = plt.subplots(2, 1, figsize=(18, 10), sharex=True)

if "Nifty 50" in prices:
    axes[0].plot(prices["Nifty 50"], color="green", linewidth=1.5)
    axes[0].set_ylabel("Nifty 50", color="green", fontsize=12)
    axes[0].set_title("Nifty 50 vs Sun Distance & Moon Distance", fontsize=16, fontweight="bold")
    axes[0].grid(True, alpha=0.3)

    ax_sun = axes[0].twinx()
    ax_sun.plot(sun_dist_series, color="orange", linewidth=1.2, alpha=0.7, label="Sun-Earth Distance")
    ax_sun.set_ylabel("Sun Distance (AU)", color="orange", fontsize=12)

    axes[1].plot(moon_dist_series, color="silver", linewidth=1.2, label="Moon-Earth Distance")
    axes[1].set_ylabel("Moon Distance (km)", fontsize=12)
    axes[1].grid(True, alpha=0.3)

    if "Nifty 50" in prices:
        ax_nifty2 = axes[1].twinx()
        ax_nifty2.plot(prices["Nifty 50"], color="green", linewidth=0.8, alpha=0.4)
        ax_nifty2.set_ylabel("Nifty 50", color="green", fontsize=10, alpha=0.5)

axes[1].xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
axes[1].xaxis.set_major_locator(mdates.MonthLocator(interval=6))
plt.xticks(rotation=45)
plt.tight_layout()
fig.savefig(OUT_DIR / "03_nifty_vs_celestial_distances.png", dpi=150)
plt.close()
print("  03_nifty_vs_celestial_distances.png")

# ═══════════════════════════════════════════════════════════════════════
# CHART 4: Silver vs Gold vs Moon Phase (triple overlay)
# ═══════════════════════════════════════════════════════════════════════
fig, ax1 = plt.subplots(figsize=(18, 7))

if "Gold" in prices and "Silver" in prices:
    ax1.plot(normalize(prices["Gold"]), color="#FFD700", linewidth=1.5, label="Gold (normalized)")
    ax1.plot(normalize(prices["Silver"]), color="#C0C0C0", linewidth=1.5, label="Silver (normalized)")
    ax1.set_ylabel("Normalized Price", fontsize=12)

    ax2 = ax1.twinx()
    ax2.plot(moon_series, color="blue", linewidth=0.8, alpha=0.4, label="Moon Phase")
    ax2.fill_between(moon_series.index, 0, moon_series.values, alpha=0.08, color="blue")
    ax2.set_ylabel("Moon Phase", color="blue", fontsize=12)
    ax2.set_ylim(0, 1.1)

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left")

ax1.set_title("Gold & Silver vs Moon Phase", fontsize=16, fontweight="bold")
ax1.grid(True, alpha=0.3)
ax1.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
ax1.xaxis.set_major_locator(mdates.MonthLocator(interval=6))
plt.xticks(rotation=45)
plt.tight_layout()
fig.savefig(OUT_DIR / "04_gold_silver_moon.png", dpi=150)
plt.close()
print("  04_gold_silver_moon.png")

# ═══════════════════════════════════════════════════════════════════════
# CHART 5: Nifty vs Daylight Hours (seasonal effect?)
# ═══════════════════════════════════════════════════════════════════════
fig, ax1 = plt.subplots(figsize=(18, 7))

if "Nifty 50" in prices:
    ax1.plot(prices["Nifty 50"], color="green", linewidth=1.5, label="Nifty 50")
    ax1.set_ylabel("Nifty 50", color="green", fontsize=12)

    ax2 = ax1.twinx()
    ax2.fill_between(daylight_series.index, daylight_series.min(), daylight_series.values,
                     alpha=0.3, color="orange", label="Daylight Hours (Mumbai)")
    ax2.plot(daylight_series, color="orange", linewidth=1)
    ax2.set_ylabel("Daylight Hours", color="orange", fontsize=12)

ax1.set_title("Nifty 50 vs Mumbai Daylight Hours — Seasonal Pattern?", fontsize=16, fontweight="bold")
ax1.grid(True, alpha=0.3)
ax1.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
ax1.xaxis.set_major_locator(mdates.MonthLocator(interval=6))
plt.xticks(rotation=45)
plt.tight_layout()
fig.savefig(OUT_DIR / "05_nifty_vs_daylight.png", dpi=150)
plt.close()
print("  05_nifty_vs_daylight.png")

# ═══════════════════════════════════════════════════════════════════════
# CHART 6: Scatter plots — Nifty daily return vs various indicators
# ═══════════════════════════════════════════════════════════════════════
fig, axes = plt.subplots(2, 3, figsize=(20, 12))
fig.suptitle("Nifty Daily Return vs Everything — Scatter Plots", fontsize=18, fontweight="bold")

scatter_pairs = [
    ("Moon Phase", moon_series),
    ("Sun Distance (AU)", sun_dist_series),
    ("Moon Distance (km)", moon_dist_series),
    ("Daylight Hours", daylight_series),
]
# Add Gold & USD returns
if "Gold" in prices:
    gold_ret = prices["Gold"].pct_change().dropna()
    scatter_pairs.append(("Gold Daily Return", gold_ret))
if "USD/INR" in prices:
    usd_ret = prices["USD/INR"].pct_change().dropna()
    scatter_pairs.append(("USD/INR Daily Return", usd_ret))

for idx, (name, series) in enumerate(scatter_pairs[:6]):
    ax = axes[idx // 3][idx % 3]
    # Align
    combined = pd.concat({"x": series, "y": nifty_ret}, axis=1, join="inner").dropna()
    if len(combined) > 10:
        ax.scatter(combined["x"], combined["y"], alpha=0.15, s=8, c="teal")
        # Add trend line
        z = np.polyfit(combined["x"], combined["y"], 1)
        p = np.poly1d(z)
        x_range = np.linspace(combined["x"].min(), combined["x"].max(), 100)
        ax.plot(x_range, p(x_range), "r-", linewidth=2, label=f"slope={z[0]:.6f}")
        # Correlation
        r = combined["x"].corr(combined["y"])
        ax.set_title(f"{name}\nr = {r:.4f}", fontsize=11)
        ax.legend(fontsize=8)
    ax.set_xlabel(name, fontsize=9)
    ax.set_ylabel("Nifty Return", fontsize=9)
    ax.grid(True, alpha=0.3)

plt.tight_layout()
fig.savefig(OUT_DIR / "06_scatter_nifty_vs_all.png", dpi=150)
plt.close()
print("  06_scatter_nifty_vs_all.png")

# ═══════════════════════════════════════════════════════════════════════
# CHART 7: Vector Dot Product — Sun·Moon distance vectors vs Gold
# ═══════════════════════════════════════════════════════════════════════
# Treat sun_dist and moon_dist as 1D "vectors" — their product is a scalar field
dot_product = sun_dist_series * moon_dist_series
dot_product.name = "Sun×Moon Distance Product"

fig, ax1 = plt.subplots(figsize=(18, 7))

if "Gold" in prices:
    ax1.plot(normalize(prices["Gold"]), color="#FFD700", linewidth=1.5, label="Gold (normalized)")
    ax1.set_ylabel("Gold (normalized)", color="#FFD700", fontsize=12)

    ax2 = ax1.twinx()
    ax2.plot(normalize(dot_product), color="purple", linewidth=1.2, alpha=0.7, label="Sun·Moon Distance Product")
    ax2.set_ylabel("Sun × Moon Distance (normalized)", color="purple", fontsize=12)

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left")

ax1.set_title("Gold vs Sun·Moon Distance Product — Your Vector Idea", fontsize=16, fontweight="bold")
ax1.grid(True, alpha=0.3)
ax1.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
ax1.xaxis.set_major_locator(mdates.MonthLocator(interval=6))
plt.xticks(rotation=45)
plt.tight_layout()
fig.savefig(OUT_DIR / "07_gold_vs_sun_moon_product.png", dpi=150)
plt.close()
print("  07_gold_vs_sun_moon_product.png")

# ═══════════════════════════════════════════════════════════════════════
# CHART 8: Nifty returns by Moon Phase bucket
# ═══════════════════════════════════════════════════════════════════════
fig, axes = plt.subplots(1, 2, figsize=(18, 7))

# Align moon with nifty returns
combined = pd.concat({"moon": moon_series, "ret": nifty_ret}, axis=1, join="inner").dropna()

# Bin moon phase into 8 buckets
combined["moon_bucket"] = pd.cut(combined["moon"], bins=8, labels=[
    "New\n0-12%", "Waxing\n12-25%", "Waxing\n25-37%", "Waxing\n37-50%",
    "Waning\n50-62%", "Waning\n62-75%", "Waning\n75-87%", "Full\n87-100%"
])

# Mean return per bucket
bucket_stats = combined.groupby("moon_bucket", observed=True)["ret"].agg(["mean", "std", "count"])
bucket_stats["mean_pct"] = bucket_stats["mean"] * 100

colors = plt.cm.Blues(np.linspace(0.3, 0.9, len(bucket_stats)))
axes[0].bar(range(len(bucket_stats)), bucket_stats["mean_pct"], color=colors, edgecolor="black", linewidth=0.5)
axes[0].set_xticks(range(len(bucket_stats)))
axes[0].set_xticklabels(bucket_stats.index, fontsize=9)
axes[0].set_ylabel("Mean Daily Return (%)")
axes[0].set_title("Nifty Mean Return by Moon Phase", fontsize=14, fontweight="bold")
axes[0].axhline(y=0, color="red", linewidth=0.8, linestyle="--")
axes[0].grid(True, alpha=0.3, axis="y")

# Win rate per bucket
combined["win"] = combined["ret"] > 0
win_rate = combined.groupby("moon_bucket", observed=True)["win"].mean() * 100
colors2 = ["green" if w > 50 else "red" for w in win_rate]
axes[1].bar(range(len(win_rate)), win_rate, color=colors2, edgecolor="black", linewidth=0.5, alpha=0.7)
axes[1].set_xticks(range(len(win_rate)))
axes[1].set_xticklabels(win_rate.index, fontsize=9)
axes[1].set_ylabel("Win Rate (%)")
axes[1].set_title("Nifty Win Rate by Moon Phase", fontsize=14, fontweight="bold")
axes[1].axhline(y=50, color="red", linewidth=0.8, linestyle="--", label="50% baseline")
axes[1].legend()
axes[1].grid(True, alpha=0.3, axis="y")

plt.tight_layout()
fig.savefig(OUT_DIR / "08_nifty_returns_by_moon.png", dpi=150)
plt.close()
print("  08_nifty_returns_by_moon.png")

# ═══════════════════════════════════════════════════════════════════════
# CHART 9: Calendar heatmap — Nifty avg return by day-of-month
# ═══════════════════════════════════════════════════════════════════════
fig, axes = plt.subplots(1, 2, figsize=(18, 7))

nifty_df = nifty_ret.to_frame("ret")
nifty_df["dom"] = nifty_df.index.day
nifty_df["month"] = nifty_df.index.month
nifty_df["dow"] = nifty_df.index.dayofweek  # 0=Mon

# Day of month
dom_stats = nifty_df.groupby("dom")["ret"].agg(["mean", "count"])
dom_stats["mean_pct"] = dom_stats["mean"] * 100
colors = ["green" if x > 0 else "red" for x in dom_stats["mean_pct"]]
axes[0].bar(dom_stats.index, dom_stats["mean_pct"], color=colors, edgecolor="black", linewidth=0.3)
axes[0].set_xlabel("Day of Month")
axes[0].set_ylabel("Mean Return (%)")
axes[0].set_title("Nifty Avg Return by Day of Month (2020-2025)", fontsize=13, fontweight="bold")
axes[0].axhline(y=0, color="black", linewidth=0.5)
axes[0].grid(True, alpha=0.3, axis="y")

# Day of week
dow_labels = ["Mon", "Tue", "Wed", "Thu", "Fri"]
dow_stats = nifty_df.groupby("dow")["ret"].agg(["mean", "count"])
dow_stats["mean_pct"] = dow_stats["mean"] * 100
colors2 = ["green" if x > 0 else "red" for x in dow_stats["mean_pct"]]
axes[1].bar(range(5), dow_stats["mean_pct"].values[:5], color=colors2, edgecolor="black", linewidth=0.5)
axes[1].set_xticks(range(5))
axes[1].set_xticklabels(dow_labels)
axes[1].set_ylabel("Mean Return (%)")
axes[1].set_title("Nifty Avg Return by Day of Week", fontsize=13, fontweight="bold")
axes[1].axhline(y=0, color="black", linewidth=0.5)
axes[1].grid(True, alpha=0.3, axis="y")

plt.tight_layout()
fig.savefig(OUT_DIR / "09_calendar_anomalies.png", dpi=150)
plt.close()
print("  09_calendar_anomalies.png")

# ═══════════════════════════════════════════════════════════════════════
# CHART 10: Month-of-year heatmap
# ═══════════════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(14, 6))

month_labels = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
month_stats = nifty_df.groupby("month")["ret"].agg(["mean", "count"])
month_stats["mean_pct"] = month_stats["mean"] * 100
nifty_df["win"] = nifty_df["ret"] > 0
month_win = nifty_df.groupby("month")["win"].mean() * 100

x = np.arange(12)
width = 0.4
bars1 = ax.bar(x - width/2, month_stats["mean_pct"].values, width, label="Avg Return (%)",
               color=["green" if v > 0 else "red" for v in month_stats["mean_pct"]], alpha=0.7, edgecolor="black", linewidth=0.3)

ax2 = ax.twinx()
ax2.plot(x, month_win.values, "ko-", linewidth=2, markersize=8, label="Win Rate (%)")
ax2.axhline(y=50, color="gray", linestyle="--", alpha=0.5)
ax2.set_ylabel("Win Rate (%)")
ax2.set_ylim(35, 65)

ax.set_xticks(x)
ax.set_xticklabels(month_labels)
ax.set_ylabel("Mean Daily Return (%)")
ax.set_title("Nifty by Month — Which Months Win?", fontsize=16, fontweight="bold")
ax.grid(True, alpha=0.3, axis="y")

lines1, labels1 = ax.get_legend_handles_labels()
lines2, labels2 = ax2.get_legend_handles_labels()
ax.legend(lines1 + lines2, labels1 + labels2, loc="upper right")

plt.tight_layout()
fig.savefig(OUT_DIR / "10_monthly_anomaly.png", dpi=150)
plt.close()
print("  10_monthly_anomaly.png")


# ═══════════════════════════════════════════════════════════════════════
# SUMMARY STATS
# ═══════════════════════════════════════════════════════════════════════
print("\n" + "="*60)
print("CORRELATION SUMMARY (Nifty daily returns vs...)")
print("="*60)

pairs = [
    ("Moon Phase", moon_series),
    ("Sun-Earth Distance", sun_dist_series),
    ("Moon-Earth Distance", moon_dist_series),
    ("Daylight Hours", daylight_series),
    ("Sun×Moon Product", dot_product),
]
if "Gold" in prices:
    pairs.append(("Gold Return", prices["Gold"].pct_change().dropna()))
if "Silver" in prices:
    pairs.append(("Silver Return", prices["Silver"].pct_change().dropna()))
if "USD/INR" in prices:
    pairs.append(("USD/INR Return", prices["USD/INR"].pct_change().dropna()))

for name, series in pairs:
    combined = pd.concat({"x": series, "y": nifty_ret}, axis=1, join="inner").dropna()
    if len(combined) > 10:
        r = combined["x"].corr(combined["y"])
        print(f"  {name:30s}  r = {r:+.4f}  ({'*' if abs(r) > 0.05 else ' '}) n={len(combined)}")

print("\n" + "="*60)
print(f"10 charts saved to: {OUT_DIR}/")
print("="*60)
