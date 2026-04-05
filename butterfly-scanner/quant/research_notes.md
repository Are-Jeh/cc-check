# Celestial & Nature-Based Market Indicators: Research Notes

> Compiled: 2026-03-15
> Status: Foundation research for quant project
> Sources: Academic papers, Fed working papers, Reddit/forum discussions, GitHub repos
> Note: Web search/fetch tools were unavailable during compilation. All entries below are drawn from training data (cutoff May 2025). URLs and details should be independently verified before building on them. Papers marked with [VERIFY] need extra confirmation.

---

## Table of Contents

1. [Tier 1: Peer-Reviewed Academic Papers](#tier-1-peer-reviewed-academic-papers)
2. [Tier 2: Working Papers & Fed/Central Bank Research](#tier-2-working-papers)
3. [Tier 3: Nature-Based Indicators (Less Studied)](#tier-3-nature-based-indicators)
4. [Tier 4: Reddit & Forum Discussions](#tier-4-reddit--forum-discussions)
5. [Tier 5: GitHub Repos](#tier-5-github-repos)
6. [Summary Table: Effect Sizes & Reliability](#summary-table)
7. [Data Sources for Implementation](#data-sources)
8. [Key Takeaways for Strategy Design](#key-takeaways)

---

## Tier 1: Peer-Reviewed Academic Papers

### 1.1 Dichev & Janes (2003) — Lunar Cycle and Stock Returns

- **Full title:** "Lunar Cycle Effects in Stock Returns"
- **Published in:** Journal of Private Equity, 2003 (Note: often cited as Journal of Finance, but the final publication venue was Journal of Private Equity, Vol. 6, No. 4, Fall 2003, pp. 8-29) [VERIFY exact venue — some sources cite a different journal]
- **What they tested:** Whether stock returns differ between the 15-day period around new moons vs. the 15-day period around full moons, across 100 years of DJIA and S&P 500 data (1896-2000) and 24 other countries' indices.
- **What they found:** **POSITIVE RESULT.** Returns in the 15 days around new moons were significantly higher than returns around full moons. The difference was roughly 5-8% annualized for the US market.
- **Effect size:** ~3-5 bps per day difference between new moon and full moon periods. Annualized, new moon periods returned ~8.3% vs. full moon periods ~4.8% (approximate figures from US data).
- **Methodology:** Simple comparison of mean daily returns in two halves of the lunar cycle. T-tests for difference in means. Controlled for day-of-week effects, January effect, calendar month effects. Used both DJIA (1896-2000) and S&P 500 (1928-2000).
- **Cross-country:** Found similar effects in 24 of 25 countries examined.
- **Peer-reviewed:** Yes.
- **Caveat:** Transaction costs and the small per-trade alpha may make it hard to trade profitably. The effect is real in-sample but economically marginal after costs.

### 1.2 Yuan, Zheng & Zhu (2006) — Are Investors Moonstruck?

- **Full title:** "Are Investors Moonstruck? Lunar Cycle and Stock Returns"
- **Published in:** Journal of Empirical Finance, Vol. 13, No. 1, 2006, pp. 1-23
- **What they tested:** Lunar cycle effects on stock returns using data from 48 countries, 1973-2001.
- **What they found:** **POSITIVE RESULT.** Stock returns are lower around full moons compared to new moons. The difference is statistically significant and robust across markets.
- **Effect size:** Average daily returns around new moon ~3.2 bps higher than around full moon. Annualized spread: ~5-8% depending on market.
- **Methodology:** Regression of daily returns on lunar phase dummy variables, controlling for day-of-week, month-of-year, and other calendar anomalies. Used CRSP data for US, Datastream for international.
- **Statistical significance:** t-stats generally between 2 and 4.
- **Peer-reviewed:** Yes (Journal of Empirical Finance is a solid venue).
- **Key insight:** They hypothesize the mechanism is mood — full moons are associated with more pessimistic mood (sleep disruption, documented psychological effects), leading to lower risk appetite.

### 1.3 Kamstra, Kramer & Levi (2003) — Winter Blues (SAD and Stock Returns)

- **Full title:** "Winter Blues: A SAD Stock Market Cycle"
- **Published in:** American Economic Review, Vol. 93, No. 1, 2003, pp. 324-343
- **What they tested:** Whether Seasonal Affective Disorder (SAD) — driven by reduced daylight hours — affects stock returns. This is the canonical "nature affects markets through mood" paper.
- **What they found:** **STRONG POSITIVE RESULT.** Returns are significantly higher in fall/winter (when days get shorter and SAD onset occurs, increasing risk aversion, depressing prices, and creating a rebound). Markets at higher latitudes show stronger effects.
- **Effect size:** SAD effect accounts for a significant portion of seasonal variation. The magnitude is large enough to be economically meaningful.
- **Methodology:** Regression of returns on hours of daylight, controlling for known calendar anomalies (January effect, day-of-week). Tested across multiple countries at different latitudes.
- **Peer-reviewed:** Yes (AER is top-tier).
- **Critical for your project:** This is THE foundational paper for "nature-based market indicators." Published in the most prestigious economics journal. Establishes that a measurable physical/biological phenomenon (light exposure -> SAD -> risk aversion) affects asset prices.

### 1.4 Kamstra, Kramer & Levi (2000) — Losing Sleep at the Market

- **Full title:** "Losing Sleep at the Market: The Daylight Saving Anomaly"
- **Published in:** American Economic Review, Vol. 90, No. 4, 2000, pp. 1005-1011
- **What they tested:** Whether the disruption from daylight saving time changes affects stock returns on the Monday following the change.
- **What they found:** **POSITIVE RESULT.** Significant negative returns on the Monday following spring-forward DST change (losing an hour of sleep). Weekend average return is about 2.5x larger negative on DST weekends.
- **Effect size:** Mean weekend return on DST weekends: approximately -25 bps (vs. ~-8 bps on normal weekends).
- **Peer-reviewed:** Yes (AER).

### 1.5 Hirshleifer & Shumway (2003) — Good Day Sunshine

- **Full title:** "Good Day Sunshine: Stock Returns and the Weather"
- **Published in:** Journal of Finance, Vol. 58, No. 3, 2003, pp. 1009-1032
- **What they tested:** Whether sunshine at the city of a country's major stock exchange affects daily stock returns.
- **What they found:** **STRONG POSITIVE RESULT.** Sunshine is strongly correlated with daily stock returns. The effect is statistically significant in nearly all 26 markets studied.
- **Effect size:** A move from total cloud cover to total sunshine is associated with approximately 24.8 bps higher daily return for the NYSE.
- **Methodology:** Regression of daily returns on cloud cover (from weather stations near exchanges), controlling for known anomalies.
- **Peer-reviewed:** Yes (Journal of Finance, top-3 finance journal).
- **Key insight:** The mechanism is mood. Sunshine improves mood, which increases risk appetite. This paper is one of the most-cited behavioral finance papers. Confirms the "mood channel" that your celestial indicators would also operate through.

---

## Tier 2: Working Papers & Fed/Central Bank Research

### 2.1 Krivelyova & Robotti (2003) — Playing the Field: Geomagnetic Storms and the Stock Market

- **Full title:** "Playing the Field: Geomagnetic Storms and the Stock Market"
- **Published as:** Federal Reserve Bank of Atlanta Working Paper 2003-5b
- **What they tested:** Whether geomagnetic storms (measured by the Kp index and Ap index) affect stock returns across international markets.
- **What they found:** **STRONG POSITIVE RESULT.** Geomagnetic storms are followed by lower stock returns. The effect is economically significant and robust.
- **Effect size:** In the week following a severe geomagnetic storm, average returns are significantly lower. They find that a trading strategy of going long during geomagnetically quiet periods and short during storm periods yields ~2.8-3.6% annualized excess return (varies by market).
- **Methodology:**
  - Used daily and weekly Ap and Kp geomagnetic indices from NOAA.
  - Regressed stock returns (US: S&P 500, NYSE; international: multiple indices) on lagged geomagnetic activity.
  - Controlled for day-of-week, month, market volatility.
  - Tested lag structures (same-day, next-day, weekly).
- **Statistical tests:** OLS regression, robustness checks with HAC standard errors, subperiod analysis.
- **Peer-reviewed:** No (working paper), but from the Federal Reserve Bank of Atlanta, which gives it institutional credibility. Has been widely cited (~200+ citations on Google Scholar).
- **Data source for Kp index:** NOAA Space Weather Prediction Center, free and publicly available at ftp://ftp.swpc.noaa.gov/pub/indices/old_indices/ [VERIFY current URL]
- **Proposed mechanism:** Geomagnetic storms -> disrupted circadian rhythms -> depressed mood -> reduced risk appetite -> lower returns.
- **Critical for your project:** This is the BEST paper on geomagnetic effects. The Kp index is freely available in real-time. This is directly tradeable.

### 2.2 Dowling & Lucey (2005) — Weather, Biorhythms, Beliefs and Stock Returns

- **Full title:** "Weather, Biorhythms, Beliefs and Stock Returns — Some Preliminary Irish Evidence"
- **Published in:** International Review of Financial Analysis, Vol. 14, No. 3, 2005, pp. 337-355
- **What they tested:** Combined effects of weather (rain, temperature, wind), biorhythms (lunar cycle), and geomagnetic storms on Irish stock returns.
- **What they found:** **MIXED.** Geomagnetic storms had a significant negative effect. Lunar effects were present but weaker. Weather effects were consistent with Hirshleifer & Shumway.
- **Peer-reviewed:** Yes.

### 2.3 Lepori (2009) — Geomagnetic Storms and Stock Returns

- **Full title:** [VERIFY exact title]
- **What they tested:** Replication and extension of Krivelyova & Robotti using updated data.
- **What they found:** Confirmed the geomagnetic storm effect persists in out-of-sample data.
- **Peer-reviewed:** [VERIFY]

### 2.4 Novy-Marx (2014) — Predicting Anomaly Performance with Politics, the Weather, Global Warming, Sunspots, and the Stars

- **Full title:** As above
- **Published in:** Journal of Financial Economics, Vol. 112, No. 2, 2014, pp. 137-146
- **What they tested:** Whether various "absurd" predictors (including sunspots, weather, and astrological signs) can predict anomaly returns. This is a CAUTIONARY paper.
- **What they found:** **NEGATIVE/CAUTIONARY.** Many of these seemingly absurd predictors do show in-sample significance — but this is a statistical artifact of data mining and multiple testing. The paper is a warning about spurious correlations.
- **Methodology:** Demonstrates that with enough variables, you'll always find "significant" predictors.
- **Peer-reviewed:** Yes (JFE is top-3).
- **Critical for your project:** You MUST address the Novy-Marx critique. Any celestial strategy must pass out-of-sample tests and multiple testing corrections to be credible.

---

## Tier 1 Continued: Sunspot/Solar Cycle Papers

### 2.5 Saunders (1993) — Stock Prices and Wall Street Weather

- **Published in:** American Economic Review, 1993
- **What they tested:** NYSE returns vs. NYC weather (cloud cover).
- **What they found:** Significant relationship between cloud cover and returns.
- **Peer-reviewed:** Yes (AER). This was the precursor to Hirshleifer & Shumway (2003).

### 2.6 Garcia & Norli (2012) — Sunspot Cycle and Stock Market [VERIFY]

- **What they tested:** Relationship between the ~11-year sunspot cycle and long-run stock market performance.
- **What they found:** Some evidence of correlation between solar maxima and periods of financial distress/lower returns, but the sample size is very small (only ~15 complete solar cycles in the modern financial era).
- **Key problem:** With only 15 data points at the cycle level, statistical power is extremely low.

### 2.7 Gorbanev (2021) — Sunspot Cycles and Stock Markets [VERIFY]

- **What they tested:** Updated analysis of the Juglar economic cycle (~7-11 years) and its possible connection to solar cycles.
- **What they found:** Suggestive correlation, but the mechanism is unclear and the evidence is not compelling after proper statistical controls.

### 2.8 Jevons (1878) — The Periodicity of Commercial Crises

- **Historical note:** William Stanley Jevons, one of the founders of neoclassical economics, proposed in 1878 that sunspot cycles drive commercial crises through their effect on weather and agricultural output. This is the ORIGINAL "sunspot -> economy" hypothesis.
- **Modern assessment:** The agricultural channel is largely irrelevant for modern economies, but the mood/biological channel (UV exposure, sleep disruption during geomagnetic storms) may have validity.

---

## Tier 3: Nature-Based Indicators (Less Studied)

### 3.1 Tidal Forces and Markets

- **Research status:** Very sparse. No major peer-reviewed paper specifically on tidal force height and stock returns as of my knowledge.
- **Related hypothesis:** Tidal forces are correlated with lunar phase (spring tides at new/full moon, neap tides at quarters). So any "tidal" effect would be partially captured by lunar cycle studies already.
- **Potential angle:** Tidal forces provide a CONTINUOUS variable (vs. binary new/full moon), which gives more statistical power. The gravitational pull varies smoothly and can be calculated precisely for any moment.
- **Data source:** NOAA Tides & Currents (tidesandcurrents.noaa.gov) — free, high-frequency data. Also computable from ephemeris data.
- **Assessment:** This is an UNTESTED angle. If lunar effects are real, a continuous tidal force measure should capture them better than binary moon phase. This could be your novel contribution.

### 3.2 Schumann Resonance and Markets

- **Research status:** No peer-reviewed financial research exists connecting Schumann resonance to markets (as of my knowledge cutoff).
- **Background:** The Schumann resonance is the fundamental electromagnetic resonance of the Earth-ionosphere cavity, typically ~7.83 Hz. It is affected by global lightning activity and solar/geomagnetic events.
- **Fringe claims:** Some alternative health communities claim Schumann resonance variations affect human mood and cognition. No rigorous evidence for this.
- **Data source:** HeartMath Institute monitors Schumann resonance (gcicenter.org). Some academic monitoring stations exist.
- **Assessment:** This is HIGHLY SPECULATIVE. No financial literature. Could be interesting as a novel variable, but establishing a mechanism is very difficult. The correlation with geomagnetic activity means it may just be a noisy proxy for what Krivelyova & Robotti already measured.

### 3.3 Solar Wind and Markets

- **Research status:** Solar wind is the driver of geomagnetic storms, so it's indirectly studied through the geomagnetic storm literature.
- **Data source:** ACE satellite real-time solar wind data from NOAA SWPC. DSCOVR satellite data.
- **Key variables:** Solar wind speed, density, Bz component of interplanetary magnetic field (southward Bz triggers geomagnetic storms).
- **Potential angle:** Solar wind data is available ~30-60 minutes BEFORE the geomagnetic storm hits Earth (because ACE/DSCOVR sit at the L1 Lagrange point). This gives a LEAD TIME advantage over using the Kp index directly. You could predict the Kp spike before it registers.
- **Assessment:** This is a PROMISING and potentially novel approach. Using upstream solar wind as a leading indicator for the geomagnetic effect could provide genuine alpha.

### 3.4 Kp Index as a Direct Trading Signal

- **What it is:** The Kp index is a 3-hour planetary geomagnetic activity index, ranging from 0 (quiet) to 9 (extreme storm). Published by GFZ Potsdam and NOAA.
- **Data availability:** Real-time: NOAA SWPC (swpc.noaa.gov). Historical: GFZ Potsdam (kp.gfz-potsdam.de). Free.
- **Update frequency:** Every 3 hours (0-3 UT, 3-6 UT, etc.).
- **Storm thresholds:** Kp >= 5 is G1 (minor storm), Kp >= 6 is G2, Kp >= 7 is G3, Kp >= 8 is G4, Kp = 9 is G5.
- **Based on Krivelyova & Robotti:** Go long during quiet periods (Kp < 4), reduce exposure or go short during storms (Kp >= 5).

### 3.5 Seasonal Daylight / Photoperiod

- **Covered by:** Kamstra, Kramer & Levi (2003) — see Section 1.3.
- **Data:** Daylight hours are perfectly deterministic and computable from latitude and date. No external data feed needed.
- **Implementation:** Calculate hours of daylight for the exchange's latitude on each trading day. Use as a continuous predictor.

---

## Tier 4: Reddit & Forum Discussions

> Note: Unable to fetch live Reddit data. Below is a summary of known community discussions based on training data.

### 4.1 r/algotrading

- **General sentiment:** Skeptical but curious. Several threads testing lunar cycle effects. Common finding: "the effect exists in backtests but is too small to trade profitably after costs." Some users have shared Python notebooks testing moon phase strategies.
- **Key thread topics:**
  - "Has anyone tested moon phase trading?" — typical responses cite Dichev & Janes, some share backtest results showing 1-3% annualized edge pre-costs.
  - "Geomagnetic storms and trading" — less discussed, but those who know the Krivelyova paper tend to be more positive about this signal.

### 4.2 r/quantfinance

- **General sentiment:** More academic, tends to cite the Novy-Marx critique. The consensus is: "statistically interesting, economically marginal, probably not worth building a strategy around as a standalone signal."

### 4.3 r/wallstreetbets

- **General sentiment:** Memetic. "Buy on full moon, sell on new moon" posts exist but are treated as jokes.

### 4.4 EliteTrader.com & Trade2Win

- **Notable threads:** Longer-form discussions about "astro trading" exist on these forums. W.D. Gann enthusiasts are active. The Gann angle/astro-trading community is a separate subculture from academic quant research — they use planetary aspects, planetary ingresses, and other astrological techniques. This is NOT the same as the academic literature and is not statistically rigorous.

### 4.5 QuantConnect / Quantopian (archived) Community

- **Several shared strategies** backtesting moon phase effects. Results are generally consistent with the academic literature — small positive effect, not enough to overcome transaction costs as a standalone strategy.

---

## Tier 5: GitHub Repos

> Note: Unable to query GitHub API live. Below are repos known from training data. [VERIFY all URLs]

### 5.1 Known Repos

1. **moonphase-trading** (various users)
   - Multiple small repos exist with names like "lunar-trading", "moon-phase-stocks", etc.
   - Typically: Python scripts that pull moon phase data (via `ephem` or `skyfield` library) and compare returns around new vs. full moons.
   - Quality: Usually hobby projects, not production-grade.

2. **astro-trading** / **financial-astrology**
   - Repos that implement W.D. Gann-style astrological trading rules.
   - NOT the same as the academic literature. These are based on planetary aspects, not peer-reviewed research.
   - Typically low-quality, no statistical rigor.

3. **geomagnetic-stocks** [VERIFY if exists]
   - Fewer repos exist for geomagnetic trading than for lunar cycle trading.
   - This is actually an opportunity — less crowded.

### 5.2 Useful Python Libraries (not trading-specific but needed for implementation)

- **`skyfield`** — Modern, accurate astronomical computation library. Can compute moon phases, planetary positions, tidal forces. By Brandon Rhodes. Well-maintained. pip install skyfield.
- **`ephem`** — Older astronomical library (PyEphem). Can compute moon phases, sun position, etc. pip install ephem.
- **`astropy`** — Full astronomical library. Overkill for this project but very accurate.
- **`noaa-sdk`** or direct API calls — For Kp index and space weather data.
- **`sunpy`** — Solar physics library. Can pull solar wind data, sunspot numbers.

---

## Summary Table

| Signal | Key Paper | Effect Size (annualized) | Statistical Sig. | Peer-Reviewed | Tradeable? | Data Availability |
|--------|-----------|-------------------------|-------------------|---------------|------------|-------------------|
| Lunar cycle (new vs full moon returns) | Dichev & Janes (2003), Yuan et al. (2006) | ~3-8% spread | Yes (t > 2) | Yes | Marginal (small per-trade) | Free (computable) |
| Geomagnetic storms (Kp index) | Krivelyova & Robotti (2003) | ~2.8-3.6% excess | Yes (t > 2) | No (Fed WP) | Yes (episodic) | Free (NOAA real-time) |
| Sunshine / cloud cover | Hirshleifer & Shumway (2003) | ~6-9% spread (full cloud vs. sun) | Yes (t > 2) | Yes (JF) | Hard (local weather) | Paid/mixed |
| SAD / daylight hours | Kamstra et al. (2003) | Significant | Yes | Yes (AER) | Slow (seasonal) | Free (computable) |
| Daylight saving disruption | Kamstra et al. (2000) | ~25 bps on DST Monday | Yes | Yes (AER) | 2 trades/year | Free (known dates) |
| Sunspot cycle (~11yr) | Jevons (1878), various | Unclear | Low power | Mixed | No (too slow) | Free (SIDC) |
| Tidal forces (continuous) | NONE | Untested | N/A | N/A | Unknown | Free (computable) |
| Schumann resonance | NONE | Untested | N/A | N/A | Unknown | Limited |
| Solar wind (leading indicator) | Indirect via Krivelyova | Untested directly | N/A | N/A | Promising (lead time) | Free (ACE/DSCOVR) |

---

## Data Sources for Implementation

### Free & Real-Time

1. **Kp Index (Geomagnetic Activity)**
   - Source: NOAA SWPC — https://www.swpc.noaa.gov/products/planetary-k-index
   - Historical: GFZ Potsdam — https://kp.gfz-potsdam.de/
   - Format: 3-hourly values, 0-9 scale
   - Latency: ~3 hours (definitive), near-real-time (estimated)

2. **Solar Wind Data**
   - Source: NOAA SWPC ACE Real-Time Solar Wind — https://www.swpc.noaa.gov/products/ace-real-time-solar-wind
   - Also DSCOVR data at same site
   - Key variables: Speed, density, Bz component
   - Latency: ~1 hour (real-time from L1 point)
   - Lead time advantage: ~30-60 minutes before geomagnetic impact

3. **Moon Phase / Lunar Data**
   - Compute locally using `skyfield` or `ephem` Python libraries
   - No API needed — fully deterministic from orbital mechanics
   - Can compute exact illumination fraction, phase angle, distance (for tidal force)

4. **Sunspot Number**
   - Source: SIDC (Royal Observatory of Belgium) — https://www.sidc.be/silso/datafiles
   - Daily, monthly, yearly sunspot numbers going back to 1700
   - Format: CSV, free

5. **Daylight Hours**
   - Compute from latitude and date using astronomical formulas
   - No external data needed

6. **Tidal Force**
   - Compute from Sun-Moon-Earth positions using `skyfield`
   - Key: distance to Moon (perigee/apogee), lunar phase (alignment with Sun)
   - Can compute precise gravitational tidal acceleration

### Paid / Harder to Get

7. **Cloud Cover / Weather at Exchanges**
   - Historical: NOAA ISD (Integrated Surface Database) — free but messy
   - Real-time: OpenWeatherMap API (free tier limited)
   - Need weather stations near each exchange

8. **Schumann Resonance**
   - HeartMath GCI — https://www.heartmath.org/gci/ [VERIFY]
   - Academic monitoring stations (limited access)

---

## Key Takeaways for Strategy Design

### What's Real (Academically Supported)

1. **Geomagnetic storms -> lower returns** is the STRONGEST and most tradeable signal. Published by the Fed. Effect is episodic (storms are infrequent — maybe 50-100 significant events per year), so it won't generate constant trades but individual events have meaningful magnitude.

2. **Lunar cycle -> return differential** is well-documented across multiple papers and 48+ countries. The effect is real but SMALL on a per-trade basis. Best used as a tilt/overlay, not a primary signal.

3. **Daylight/SAD -> seasonal return patterns** is published in the AER. Very robust. But it's a slow-moving signal (seasonal), so it's more of a risk allocation overlay.

4. **Sunshine -> returns** is published in the Journal of Finance. Robust. But hard to trade (you'd need real-time cloud cover at the exchange city, and the effect is same-day).

### What's Novel (Your Potential Edge)

1. **Continuous tidal force** instead of binary moon phase — no one has published this. You'd have a more granular signal that captures both the lunar phase effect AND lunar distance (perigee/apogee) effects simultaneously.

2. **Solar wind as a LEADING indicator** for geomagnetic effects — the ACE/DSCOVR data gives you ~30-60 minutes of lead time before a geomagnetic storm hits. If geomagnetic storms depress returns, you could position BEFORE the storm registers on the Kp index.

3. **Combining signals** — No paper has tested a combined model of geomagnetic + lunar + daylight + weather. A multi-factor "nature" model might capture more variance than any single factor.

### Critical Risks

1. **Novy-Marx (2014) critique:** Data mining is a real danger. Any strategy must be tested out-of-sample, with proper multiple-testing corrections (Bonferroni, BH, or bootstrap).

2. **Transaction costs:** Most of these effects are small. If you're paying 5-10 bps round-trip, the lunar effect (~3-5 bps/day differential) might not survive.

3. **Crowding:** The lunar cycle papers are well-known (hundreds of citations). If many people trade this, the effect will diminish.

4. **Mechanism skepticism:** Journals have published these, but many economists remain skeptical. The mood channel (nature -> mood -> risk appetite -> prices) is plausible but hard to prove.

### Recommended Priority for Implementation

1. **FIRST: Geomagnetic (Kp index)** — Strongest signal, free real-time data, clear lead-time opportunity via solar wind
2. **SECOND: Lunar cycle (continuous tidal force version)** — Novel angle, free computable data, well-supported academically
3. **THIRD: Daylight/SAD overlay** — Free computable data, AER-published, good as a background signal
4. **FOURTH: Combined multi-factor model** — After individual signals are validated
5. **LAST: Schumann, sunspot cycle** — Too speculative or too slow to trade

---

## Appendix: Full Citation List

1. Dichev, I. D., & Janes, T. D. (2003). Lunar cycle effects in stock returns. *Journal of Private Equity*, 6(4), 8-29. [VERIFY venue]
2. Yuan, K., Zheng, L., & Zhu, Q. (2006). Are investors moonstruck? Lunar cycle and stock returns. *Journal of Empirical Finance*, 13(1), 1-23.
3. Krivelyova, A., & Robotti, C. (2003). Playing the field: Geomagnetic storms and the stock market. *Federal Reserve Bank of Atlanta Working Paper* 2003-5b.
4. Kamstra, M. J., Kramer, L. A., & Levi, M. D. (2003). Winter blues: A SAD stock market cycle. *American Economic Review*, 93(1), 324-343.
5. Kamstra, M. J., Kramer, L. A., & Levi, M. D. (2000). Losing sleep at the market: The daylight saving anomaly. *American Economic Review*, 90(4), 1005-1011.
6. Hirshleifer, D., & Shumway, T. (2003). Good day sunshine: Stock returns and the weather. *Journal of Finance*, 58(3), 1009-1032.
7. Saunders, E. M. (1993). Stock prices and Wall Street weather. *American Economic Review*, 83(5), 1337-1345.
8. Novy-Marx, R. (2014). Predicting anomaly performance with politics, the weather, global warming, sunspots, and the stars. *Journal of Financial Economics*, 112(2), 137-146.
9. Dowling, M., & Lucey, B. M. (2005). Weather, biorhythms, beliefs and stock returns. *International Review of Financial Analysis*, 14(3), 337-355.
10. Jevons, W. S. (1878). Commercial crises and sun-spots. *Nature*, 19, 33-37.

---

## Appendix: Items to Verify via Web Search

When web access is available, verify:

- [ ] Exact publication venue for Dichev & Janes (2003) — some sources say Journal of Private Equity, others suggest a different journal
- [ ] Current URL for NOAA Kp index historical data
- [ ] Existence of any published paper on continuous tidal force and financial returns (this would change the "novel angle" assessment)
- [ ] GitHub repos: search `lunar trading python`, `geomagnetic stocks`, `astro trading backtest`
- [ ] Reddit threads: search r/algotrading and r/quantfinance for recent discussions (2024-2026)
- [ ] Whether Lepori (2009) geomagnetic replication was published in a peer-reviewed journal
- [ ] Any post-2020 papers that replicate or refute the lunar/geomagnetic effects with recent data
- [ ] HeartMath GCI Schumann resonance data availability and API access
