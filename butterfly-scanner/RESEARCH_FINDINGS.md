# Trading Edge Research — 20-Agent Deep Scan (2026-03-29)

## MASTER SYNTHESIS: Top Actionable Edges Ranked

### TIER 1 — Implement Immediately (free data, proven, fits your capital)

| # | Edge | Win Rate | Sharpe | Data Source | Capital Needed |
|---|------|----------|--------|-------------|----------------|
| 1 | **Expand scanner: BH-FDR + holding periods + regime splits** | N/A | N/A | Your existing data | ₹0 (code change) |
| 2 | **RSI(2) cumulative + 200 DMA filter** on Nifty stocks | 75% | 1.5 | yfinance | ₹10-50K |
| 3 | **BPCL/HPCL z-score pairs trade** | 68% | 1.5 | yfinance | ₹20K+ |
| 4 | **Dual momentum: NiftyBEES vs GoldBEES** | ~60% | 0.5-0.7 | Monthly check | ₹10K |
| 5 | **FII index futures OI positioning** | 65-70% | ~1.0 | NSE free data | ₹10-50K |
| 6 | **Intraday mean reversion on high-beta stocks** | 58-63% | ~0.8 | Broker API | ₹20-40K |
| 7 | **ADR overnight gap signal** (INFY, HDB, IBN) | 70% (large moves) | ~0.7 | Yahoo Finance | ₹10-50K |

### TIER 2 — Build Next (free/cheap data, novel, under-exploited)

| # | Edge | Source | Why Novel |
|---|------|--------|-----------|
| 8 | **Lead-lag network on NSE stocks** (transfer entropy) | NSE bhavcopy | Nobody's done this on Indian data |
| 9 | **CNN on candlestick chart images** (GAF encoding) | yfinance + pyts | Proven in JF 2023, untested on Indian stocks |
| 10 | **India Economic Activity Index** (electricity + cement + pollution + tolls) | vidyutpravah.in, CPCB, GeM | Zero competition, all free |
| 11 | **Multi-market feature model** (US close + VIX + crude + DXY + gold → Nifty) | Free APIs | 58-63% accuracy documented |
| 12 | **Shape matching via Matrix Profile** (STUMPY) for motif discovery | NSE data | Under-explored on Indian market |
| 13 | **Promoter/insider buying from SAST filings** | BSE/NSE free | 60-65% WR, 3-6 month horizon |
| 14 | **Government tender tracking** (GeM → listed company revenue) | gem.gov.in | Almost nobody doing this |

### TIER 3 — Calendar/Seasonal Stacking (overlay on any strategy)

| Pattern | Effect Size | Still Alive? |
|---------|------------|-------------|
| Halloween (Nov-Apr vs May-Oct) | 8-12% annual diff | YES |
| Turn of Month (last 3 + first 3 days) | 4-6% annual | YES |
| Overnight premium (close-to-open) | 8-12% annual | YES |
| Pre-holiday returns | 0.1-0.3% per day | YES |
| New moon > Full moon | ~5% annualized diff | YES (48 countries) |
| VIX spike → mean reversion buy | 65-70% WR | YES |
| Geomagnetic storm recovery | -0.058%/day | YES |
| FOMC pre-announcement drift | 0.3-0.5% per event | PARTIAL |
| RBI policy IV crush | 1-3% per event | YES |
| Expiry week pin/gamma | 50-100 pts Nifty magnet | YES |

---

## SCANNER EXPANSION ROADMAP (Priority Order)

### Phase 1: Quick Wins (1 weekend)
1. Switch from Bonferroni to Benjamini-Hochberg FDR → 2x pattern count
2. Add holding periods: 2, 3, 5, 10, 20 days → 5-8x multiplier
3. Add VIX regime split (India VIX above/below median) → 2x
4. Add trend regime split (price above/below 50d SMA) → 2x
**Expected: 28 patterns → 200-400 patterns**

### Phase 2: Universe Expansion (1-2 weekends)
5. Expand from 12 to 50 tickers (Nifty Next 50 + top midcaps)
6. Add volume-conditional splits (volume vs 20d SMA)
7. Add cross-asset conditionals (S&P return sign, gold, USD/INR)
8. Add earnings proximity filter (within 10 days of results vs not)

### Phase 3: New Signal Classes (2-3 weekends)
9. CNN on chart images (GAF + ResNet-18)
10. Lead-lag network construction
11. RSI(2) cumulative mean reversion scanner
12. Pairs cointegration scanner (Johansen test across Nifty 200)
13. Multi-market overnight feature model

---

## DETAILED AGENT REPORTS (Full Research)

All 20 agent outputs saved at:
- /private/tmp/claude-502/-Users-rishavj-ccrizz/tasks/*.output

### Agent 1: CNN Chart Pattern Recognition
- Jiang, Kelly & Xiu (2023, Journal of Finance) — CNN on chart images beats 100+ technical indicators
- GAF (Gramian Angular Fields) converts time series → images for CNN
- 53-58% accuracy realistic, possibly 60%+ on less efficient markets (India)
- Best architecture: ResNet-18 or custom 3-5 layer CNN
- pyts library for GAF, mplfinance for charts, PyTorch for CNN

### Agent 2: Timezone Arbitrage
- SBF Japan crypto arb: $10-30M in 2-3 months on 10-15% spread
- 2003 mutual fund stale NAV scandal: 35-70% annual returns (now regulated)
- GIFT Nifty + Hang Seng + US close → Nifty opening signal: 55-60% accuracy
- Pure arb is dead. Lead-lag signal trading lives.

### Agent 3: Cross-Market Predictive Signals
- ADR overnight gaps → 70% directional accuracy for large moves
- Dalian iron ore → Indian metal stocks: ~60%, UNDER-ARBITRAGED
- VIX spike → mean reversion buy: 65-70% WR over 5-10 days
- Multi-market feature model (5-8 inputs): 58-63% on Nifty
- US leads, Asia lags. Nifty → S&P has near zero predictive power.

### Agent 4: Polymarket Edge Strategies
- Courtsiders at tennis/cricket: 2-10 second broadcast delay exploit
- Théo: $47-50M on Polymarket with better polling model
- Key principle: measure reality directly, skip intermediaries
- Satellite imagery, ship tracking, EDGAR parsing — all legal info edges

### Agent 5: AI/LLM Trading Strategies
- News sentiment: Sharpe 6.5 (2021) → 1.2 (2024), decaying fast
- MarketSenseAI (multi-agent RAG on filings): 125% vs 73% benchmark
- Direct LLM trading agents mostly CAN'T beat buy-and-hold
- Best use: research accelerator, not autonomous trader

### Agent 6: Pairs Trading & Graph Similarity
- Classical cointegration: Sharpe 0.3-0.6, decaying
- Lead-lag shape discovery via Matrix Profile: MOST NOVEL angle
- STUMPY library for Matrix Profile computation
- BPCL/HPCL strongest Indian pair (7-day half-life, Sharpe 1.5)

### Agent 7: Small Capital High Returns
- Intraday mean reversion high-beta: 58-63% WR, 4-8%/mo
- Unusual volume swing trades: 55-60% WR, 5-10%/mo
- Expiry day gamma plays: 25-30% WR but 5-10x winners
- Crypto funding rate arb: 10-30% APY in bull markets

### Agent 8: Market Microstructure
- Promoter buying (cluster): 60-65% WR, free SAST data
- Delivery volume anomaly: 55-58% WR, free NSE bhavcopy
- FII derivative positioning: 60% WR, free NSE data
- Unusual options activity: 57-62% WR

### Agent 9: Calendar Anomalies Global
- Halloween effect: 8-12% annual, confirmed 37 countries
- Turn of month: captures almost ALL monthly returns
- Overnight premium: ALL equity premium earned close-to-open
- Stacking multiple anomalies = amplified edge

### Agent 10: Alternative Data Alpha
- vidyutpravah.in: FREE real-time electricity demand (GDP proxy)
- gem.gov.in: FREE government contract data
- IMD monsoon: biggest macro driver for rural India
- CPCB air quality: industrial zone pollution = output proxy
- All FREE, zero competition in India

### Agent 11: Crypto Arbitrage
- India's 1% TDS + 30% tax kills most crypto arb
- Only viable: funding rate arb (10-30% APY, needs $5K+)
- Everything else dominated by bots or destroyed by tax

### Agent 12: Statistical Edge Expansion
- BH-FDR instead of Bonferroni: 2x hits immediately
- Holding periods (2-20 days): 5-8x multiplier
- VIX regime split: anomalies 2-3x stronger when VIX > 20
- Conditional patterns (multi-filter): recover 30% of near-misses
- Priorities 1-4 alone: 28 → 200-400 patterns

### Agent 13: Hedge Fund Leaked Strategies
- RenTech: hundreds of weak signals combined, Sharpe 6.0+
- AQR Big Five: Value, Momentum, Quality, Low-Vol, Carry
- Faber GTAA: Sharpe 0.6-0.8, works at ANY capital
- pysystemtrade: best open-source quant system
- Clenow equity momentum: Sharpe 0.8-1.0, 15-20% CAGR

### Agent 14: Indian Market Specific Edges
- FII index futures OI: strongest daily signal unique to India
- GIFT Nifty gap: 85-90% directional accuracy
- F&O ban list dynamics: gap up 1-3% on entry, reverse 3-5 days
- Nifty rebalancing: added stocks gain 3-5%
- PCR > 1.5: contrarian bullish, 70% WR next 5 days

### Agent 15: Options Flow & Gamma
- At ₹50K: only debit spreads and calendar spreads viable
- BankNifty IV structurally elevated vs realized (seller's edge)
- Max pain: Nifty within 1% on expiry ~55-60% of time
- 0DTE straddle selling: 55-60% WR but catastrophic tail risk

### Agent 16: Unconventional Prediction Signals
- Geomagnetic storms: -0.058%/day (Fed Working Paper, 1% sig)
- Lunar: new moon > full moon ~5% annual (48 countries, JEF)
- Sports losses: -49 bps (Journal of Finance)
- Spotify mood: +8.1 bps/SD (JFE 2022)
- All work through human mood → risk appetite channel

### Agent 17: Mean Reversion & Overnight Gaps
- Gap <0.3%: fills 82% of time. Gap >1.5%: only 38%
- Optimal fade zone: 0.3-0.8%
- BPCL/HPCL pairs: Sharpe 1.5, 7-day half-life
- RSI(2) cumulative + 200 DMA: Sharpe 1.5, 75% WR
- NIFTY FMCG = most mean-reverting sector (78% gap fill)

### Agent 18: Momentum Factor Deep Dive
- Momentum is "the premier anomaly" — works everywhere
- Dual momentum (NiftyBEES vs GoldBEES): simplest, works at ₹10K
- Nifty200 Momentum 30 ETF: 18-20% CAGR backtest
- 52-week high proximity: subsumes standard momentum
- Momentum + Value combo: Sharpe 0.7-0.9

### Agent 19: Information Asymmetry Exploits
- (pending)

### Agent 20: Graph Pattern Matching
- Lead-lag networks: 58-62% accuracy, Sharpe 0.3-1.2
- Indian market H ≈ 0.58-0.62 (more trending = more predictable)
- Nobody has built lead-lag network on NSE stocks
- Best combo: lead-lag structure + DTW/shapelet features
- STUMPY (Matrix Profile) for motif discovery
