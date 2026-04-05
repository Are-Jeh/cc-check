# Opportunity Engine

An automated system that scans multiple data sources for underpriced assets, market gaps, and arbitrage opportunities in India, then sends alerts via Telegram.

## Scanners

| Scanner | What it does | Schedule |
|---------|-------------|----------|
| **SGB Scanner** | Finds Sovereign Gold Bonds trading below gold NAV on NSE | Every 4 hours (market hours) |
| **Tender Scanner** | Scans GeM and eProcure for IT/AI government tenders (Rs 1L–50L) | Twice daily |
| **Property Scanner** | Flags underpriced properties in Noida/Greater Noida vs area averages | Daily |
| **Job Matcher** | Matches job openings with your contacts for referral income | Daily |
| **Deal Scanner** | Tracks e-commerce price drops on Amazon.in and Flipkart | Every 2 hours |

## Quick Start

```bash
# 1. Clone and enter the directory
cd opportunity-engine

# 2. Create a virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r opportunity_engine/requirements.txt

# 4. Set up environment variables
cp .env.example .env
# Edit .env and add your API keys (see below)

# 5. Run the engine
python -m opportunity_engine.run
```

## Command-Line Options

```bash
python -m opportunity_engine.run                # Start bot + scheduler
python -m opportunity_engine.run --scan-now     # Run all scanners immediately on startup
python -m opportunity_engine.run --no-bot       # Scheduler only (no Telegram)
python -m opportunity_engine.run --bot-only     # Telegram bot only (no scheduler)
```

## Running Individual Scanners

Each scanner can be run standalone for testing:

```bash
python -m opportunity_engine.sgb_scanner
python -m opportunity_engine.tender_scanner
python -m opportunity_engine.property_scanner
python -m opportunity_engine.job_matcher
python -m opportunity_engine.deal_scanner
```

## API Keys Required

| Key | Where to get it | Required? |
|-----|----------------|-----------|
| `TELEGRAM_BOT_TOKEN` | [@BotFather](https://t.me/BotFather) on Telegram | Yes |
| `TELEGRAM_CHANNEL_ID` | Your Telegram channel (e.g. `@my_alerts`) | Yes |
| `GOLD_API_KEY` | [goldapi.io](https://www.goldapi.io/) (free tier: 10 req/day) | For SGB scanner |
| `RAZORPAY_KEY_ID` / `SECRET` | [Razorpay Dashboard](https://dashboard.razorpay.com/) | For paid subscriptions |
| `AMAZON_AFFILIATE_TAG` | [Amazon Associates](https://affiliate-program.amazon.in/) | For deal links |
| `FLIPKART_AFFILIATE_ID` | [Flipkart Affiliate](https://affiliate.flipkart.com/) | For deal links |

## Telegram Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message |
| `/today` | Run all scanners now |
| `/sgb` | SGB discount scan |
| `/tenders` | Government tender scan |
| `/property` | Property opportunity scan |
| `/jobs` | Job-candidate matching |
| `/deals` | E-commerce deal scan |
| `/subscribe` | Subscription tier info |

## Configuring Scanners

All thresholds are tunable via environment variables or by editing `config.py`:

- **SGB**: `SGB_MIN_DISCOUNT_PCT` — minimum discount below NAV (default: 3%)
- **Tenders**: `TENDER_MIN_VALUE` / `TENDER_MAX_VALUE` — budget range (default: Rs 1L–50L)
- **Property**: `PROPERTY_MIN_DISCOUNT_PCT` — minimum below area average (default: 10%)
- **Jobs**: `JOB_MIN_MATCH_SCORE` — minimum match score 0-100 (default: 60)
- **Deals**: `DEAL_MIN_PRICE_DROP_PCT` — minimum price drop to alert (default: 20%)

## Data Files

- `data/contacts.json` — Your network contacts for the job matcher
- `data/tracked_products.json` — Products to track for price drops
- `data/price_history.json` — Auto-generated price tracking data

## Architecture

```
opportunity_engine/
├── __init__.py
├── config.py            # Central configuration, loaded from .env
├── sgb_scanner.py       # Sovereign Gold Bond scanner
├── tender_scanner.py    # Government tender scanner
├── property_scanner.py  # Property price scanner
├── job_matcher.py       # Job-candidate matcher
├── deal_scanner.py      # E-commerce deal tracker
├── telegram_bot.py      # Telegram bot with all commands
├── scheduler.py         # APScheduler job configuration
├── run.py               # Main entry point
├── requirements.txt
└── data/
    ├── contacts.json
    ├── tracked_products.json
    └── price_history.json
```

## Notes on Scraping

Several scanners scrape websites that actively block bots. The code includes:

1. **Full scraping logic** with CSS selectors for each data source.
2. **Fallback demo data** so you can test the pipeline without live access.
3. **Comments explaining alternatives** (official APIs, headless browsers, proxies).

For production use, consider:
- Using **Playwright** or **Selenium** for sites that need JavaScript rendering.
- Rotating **proxies** and **user agents** for sites that rate-limit.
- Subscribing to **official data feeds** where available (NSE, 99acres, Amazon PA-API).

## License

Private project. Not for redistribution.
