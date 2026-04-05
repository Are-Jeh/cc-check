"""
Telegram Bot — Opportunity Engine
===================================
Sends daily digests and on-demand scan results via Telegram.

Features:
    /start          — Welcome message and available commands
    /today          — Run all scanners now and send results
    /sgb            — Run SGB scanner only
    /tenders        — Run tender scanner only
    /property       — Run property scanner only
    /jobs           — Run job matcher only
    /deals          — Run deal scanner only
    /subscribe      — Show subscription tiers (Razorpay integration)
    /help           — List commands

Requires: python-telegram-bot >= 20.0 (async version)
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional

from telegram import BotCommand, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from opportunity_engine import config
from opportunity_engine import sgb_scanner
from opportunity_engine import tender_scanner
from opportunity_engine import property_scanner
from opportunity_engine import job_matcher
from opportunity_engine import deal_scanner

logger = logging.getLogger(__name__)

# Maximum Telegram message length
_MAX_MSG = 4096


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _truncate(text: str, limit: int = _MAX_MSG) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 30] + "\n\n... (truncated)"


def _split_messages(text: str, limit: int = _MAX_MSG) -> List[str]:
    """Split long text into multiple Telegram-safe messages."""
    if len(text) <= limit:
        return [text]
    chunks: List[str] = []
    while text:
        if len(text) <= limit:
            chunks.append(text)
            break
        # Find a good split point
        split_at = text.rfind("\n\n", 0, limit)
        if split_at == -1:
            split_at = text.rfind("\n", 0, limit)
        if split_at == -1:
            split_at = limit
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    return chunks


async def _send_long(update: Update, text: str) -> None:
    """Send a potentially long message, splitting if needed."""
    for chunk in _split_messages(text):
        await update.message.reply_text(chunk)


# ---------------------------------------------------------------------------
# Scanner wrappers (run in executor to avoid blocking the bot loop)
# ---------------------------------------------------------------------------

async def _run_sgb() -> str:
    results = await sgb_scanner.scan()
    if not results:
        return "No SGB opportunities found at this time."
    header = f"SGB OPPORTUNITIES ({len(results)} found)\n{'='*40}\n\n"
    body = "\n\n".join(r.summary() for r in results)
    return header + body


async def _run_tenders() -> str:
    results = await tender_scanner.scan()
    if not results:
        return "No tender opportunities found at this time."
    header = f"TENDER OPPORTUNITIES ({len(results)} found)\n{'='*40}\n\n"
    body = "\n\n".join(r.summary() for r in results)
    return header + body


async def _run_property() -> str:
    results = await property_scanner.scan()
    if not results:
        return "No property opportunities found at this time."
    header = f"PROPERTY OPPORTUNITIES ({len(results)} found)\n{'='*40}\n\n"
    body = "\n\n".join(r.summary() for r in results)
    return header + body


async def _run_jobs() -> str:
    results = await job_matcher.scan()
    if not results:
        return "No job match opportunities found at this time."
    header = f"JOB MATCHES ({len(results)} found)\n{'='*40}\n\n"
    body = "\n\n".join(r.summary() for r in results)
    return header + body


async def _run_deals() -> str:
    results = await deal_scanner.scan()
    if not results:
        return "No deal opportunities found at this time."
    header = f"DEAL ALERTS ({len(results)} found)\n{'='*40}\n\n"
    body = "\n\n".join(r.summary() for r in results)
    return header + body


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start — welcome message."""
    text = (
        "Welcome to the Opportunity Engine!\n\n"
        "I scan multiple sources for underpriced assets, market gaps, "
        "and arbitrage opportunities in India.\n\n"
        "Commands:\n"
        "  /today     — Full scan across all sources\n"
        "  /sgb       — Sovereign Gold Bond discounts\n"
        "  /tenders   — Government IT/AI tenders\n"
        "  /property  — Underpriced properties in Noida\n"
        "  /jobs      — Job-candidate matches for referrals\n"
        "  /deals     — E-commerce price drops\n"
        "  /subscribe — Premium subscription info\n"
        "  /help      — Show this message\n\n"
        "I also send a daily morning digest automatically."
    )
    await update.message.reply_text(text)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help."""
    await cmd_start(update, context)


async def cmd_today(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /today — run all scanners."""
    await update.message.reply_text("Running all scanners... this may take a minute.")

    scanner_tasks = {
        "SGB": _run_sgb(),
        "Tenders": _run_tenders(),
        "Property": _run_property(),
        "Jobs": _run_jobs(),
        "Deals": _run_deals(),
    }

    results = await asyncio.gather(*scanner_tasks.values(), return_exceptions=True)

    timestamp = datetime.now().strftime("%d %b %Y, %I:%M %p")
    header = f"DAILY OPPORTUNITY DIGEST\n{timestamp}\n{'='*40}\n\n"

    sections: List[str] = []
    for name, result in zip(scanner_tasks.keys(), results):
        if isinstance(result, Exception):
            sections.append(f"[{name}] Scanner failed: {result}")
            logger.error("Scanner %s failed: %s", name, result)
        else:
            sections.append(result)

    full_report = header + "\n\n---\n\n".join(sections)
    await _send_long(update, full_report)


async def cmd_sgb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Scanning SGBs...")
    text = await _run_sgb()
    await _send_long(update, text)


async def cmd_tenders(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Scanning government tenders...")
    text = await _run_tenders()
    await _send_long(update, text)


async def cmd_property(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Scanning properties...")
    text = await _run_property()
    await _send_long(update, text)


async def cmd_jobs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Running job matcher...")
    text = await _run_jobs()
    await _send_long(update, text)


async def cmd_deals(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Scanning deals...")
    text = await _run_deals()
    await _send_long(update, text)


async def cmd_subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /subscribe — show subscription tiers with Razorpay payment links.

    Integration steps:
        1. Create a Razorpay subscription plan via their API or dashboard.
        2. Generate a payment link for each tier.
        3. On successful payment, Razorpay sends a webhook to your server.
        4. Your webhook handler adds the user to the "premium" list.

    For now, this shows a stub with placeholder links.
    """
    razorpay_configured = bool(config.RAZORPAY_KEY_ID and config.RAZORPAY_KEY_SECRET)

    if razorpay_configured:
        # TODO: Generate real Razorpay payment links via API
        # razorpay_client = razorpay.Client(auth=(config.RAZORPAY_KEY_ID, config.RAZORPAY_KEY_SECRET))
        # link = razorpay_client.payment_link.create({...})
        payment_note = "(Payment integration is configured — generating links...)"
    else:
        payment_note = "(Payment not yet configured — add Razorpay keys to .env)"

    text = (
        "OPPORTUNITY ENGINE — SUBSCRIPTION TIERS\n"
        "========================================\n\n"
        "FREE TIER (current):\n"
        "  - Daily digest of all opportunities\n"
        "  - /today on-demand scan (3x per day)\n\n"
        "PREMIUM — Rs 299/month:\n"
        "  - Real-time alerts (within 15 min of detection)\n"
        "  - Unlimited on-demand scans\n"
        "  - Priority tender notifications\n"
        "  - Custom price alerts for deals\n\n"
        "PRO — Rs 999/month:\n"
        "  - Everything in Premium\n"
        "  - Property investment analysis reports\n"
        "  - SGB portfolio optimisation suggestions\n"
        "  - Job referral pipeline management\n"
        "  - API access\n\n"
        f"{payment_note}\n\n"
        "Contact @your_username for manual subscription."
    )
    await update.message.reply_text(text)


async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Unknown command. Use /help to see available commands."
    )


# ---------------------------------------------------------------------------
# Daily digest (called by scheduler)
# ---------------------------------------------------------------------------

async def send_daily_digest(app: Application) -> None:
    """
    Run all scanners and send the digest to the configured channel.
    Called by the scheduler, not by a user command.
    """
    channel_id = config.TELEGRAM_CHANNEL_ID
    if not channel_id:
        logger.warning("TELEGRAM_CHANNEL_ID not set — skipping daily digest")
        return

    logger.info("Generating daily digest...")

    scanner_results = await asyncio.gather(
        _run_sgb(),
        _run_tenders(),
        _run_property(),
        _run_jobs(),
        _run_deals(),
        return_exceptions=True,
    )

    names = ["SGB", "Tenders", "Property", "Jobs", "Deals"]
    timestamp = datetime.now().strftime("%d %b %Y, %I:%M %p")
    header = f"DAILY OPPORTUNITY DIGEST\n{timestamp}\n{'='*40}\n\n"

    sections: List[str] = []
    for name, result in zip(names, scanner_results):
        if isinstance(result, Exception):
            sections.append(f"[{name}] Scanner failed: {result}")
        else:
            sections.append(result)

    full_report = header + "\n\n---\n\n".join(sections)

    for chunk in _split_messages(full_report):
        try:
            await app.bot.send_message(chat_id=channel_id, text=chunk)
        except Exception as exc:
            logger.error("Failed to send digest chunk to %s: %s", channel_id, exc)


# ---------------------------------------------------------------------------
# Send individual scanner results to channel
# ---------------------------------------------------------------------------

async def send_scanner_results(app: Application, scanner_name: str, text: str) -> None:
    """Send results from a specific scanner to the Telegram channel."""
    channel_id = config.TELEGRAM_CHANNEL_ID
    if not channel_id:
        return
    for chunk in _split_messages(text):
        try:
            await app.bot.send_message(chat_id=channel_id, text=chunk)
        except Exception as exc:
            logger.error("Failed to send %s results: %s", scanner_name, exc)


# ---------------------------------------------------------------------------
# Bot setup
# ---------------------------------------------------------------------------

def build_application() -> Application:
    """Create and configure the Telegram bot application."""
    if not config.TELEGRAM_BOT_TOKEN:
        raise ValueError(
            "TELEGRAM_BOT_TOKEN is not set. "
            "Get a token from @BotFather on Telegram and add it to your .env file."
        )

    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()

    # Register command handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("today", cmd_today))
    app.add_handler(CommandHandler("sgb", cmd_sgb))
    app.add_handler(CommandHandler("tenders", cmd_tenders))
    app.add_handler(CommandHandler("property", cmd_property))
    app.add_handler(CommandHandler("jobs", cmd_jobs))
    app.add_handler(CommandHandler("deals", cmd_deals))
    app.add_handler(CommandHandler("subscribe", cmd_subscribe))

    # Catch-all for unknown commands
    app.add_handler(MessageHandler(filters.COMMAND, unknown_command))

    return app


async def set_bot_commands(app: Application) -> None:
    """Set the command menu that appears in the Telegram UI."""
    commands = [
        BotCommand("today", "Run all scanners now"),
        BotCommand("sgb", "Sovereign Gold Bond discounts"),
        BotCommand("tenders", "Government IT/AI tenders"),
        BotCommand("property", "Underpriced properties in Noida"),
        BotCommand("jobs", "Job-candidate referral matches"),
        BotCommand("deals", "E-commerce price drops"),
        BotCommand("subscribe", "Premium subscription info"),
        BotCommand("help", "Show available commands"),
    ]
    await app.bot.set_my_commands(commands)


async def start_bot(app: Application) -> None:
    """Initialise the bot, set commands, and start polling."""
    await app.initialize()
    await set_bot_commands(app)
    await app.start()
    logger.info("Telegram bot started — polling for updates")
    await app.updater.start_polling(drop_pending_updates=True)


async def stop_bot(app: Application) -> None:
    """Gracefully shut down the bot."""
    logger.info("Stopping Telegram bot...")
    await app.updater.stop()
    await app.stop()
    await app.shutdown()
