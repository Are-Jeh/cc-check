#!/usr/bin/env python3
"""
Opportunity Engine — Main Entry Point
=======================================
Starts the Telegram bot and the APScheduler side-by-side in a single
asyncio event loop.

Usage:
    python -m opportunity_engine.run              # normal startup
    python -m opportunity_engine.run --scan-now   # run all scanners immediately on startup
    python -m opportunity_engine.run --no-bot     # scheduler only (no Telegram bot)
    python -m opportunity_engine.run --bot-only   # Telegram bot only (no scheduler)
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
from pathlib import Path

# Ensure the project root is on sys.path so "opportunity_engine" is importable
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from opportunity_engine import config
from opportunity_engine.telegram_bot import build_application, start_bot, stop_bot
from opportunity_engine.scheduler import create_scheduler, start_scheduler

logger = logging.getLogger("opportunity_engine")


def _setup_logging() -> None:
    """Configure logging for the entire application."""
    log_format = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
    handlers: list = [logging.StreamHandler(sys.stdout)]

    log_file = config.LOG_FILE
    if log_file:
        try:
            Path(log_file).parent.mkdir(parents=True, exist_ok=True)
            handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
        except Exception as exc:
            print(f"Warning: could not open log file {log_file}: {exc}")

    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL.upper(), logging.INFO),
        format=log_format,
        handlers=handlers,
    )
    # Quieten noisy third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.INFO)
    logging.getLogger("telegram").setLevel(logging.WARNING)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Opportunity Engine")
    parser.add_argument(
        "--scan-now",
        action="store_true",
        help="Run all scanners immediately on startup",
    )
    parser.add_argument(
        "--no-bot",
        action="store_true",
        help="Run scheduler only (no Telegram bot)",
    )
    parser.add_argument(
        "--bot-only",
        action="store_true",
        help="Run Telegram bot only (no scheduler)",
    )
    return parser.parse_args()


async def _main(args: argparse.Namespace) -> None:
    """Async main — starts bot and/or scheduler."""
    app = None
    scheduler = None
    shutdown_event = asyncio.Event()

    # Handle SIGINT/SIGTERM gracefully
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, shutdown_event.set)

    try:
        # --- Telegram bot ---
        if not args.no_bot:
            if not config.TELEGRAM_BOT_TOKEN:
                logger.error(
                    "TELEGRAM_BOT_TOKEN not set. "
                    "Either set it in .env or use --no-bot to skip the bot."
                )
                if not args.bot_only:
                    logger.info("Continuing with scheduler only...")
                    args.no_bot = True
                else:
                    return

            if not args.no_bot:
                app = build_application()
                await start_bot(app)
                logger.info("Telegram bot is running")

        # --- Scheduler ---
        if not args.bot_only:
            scheduler = create_scheduler(app=app)
            start_scheduler(scheduler, run_initial_scan=args.scan_now, app=app)
            logger.info("Scheduler is running")

        # --- Wait for shutdown signal ---
        logger.info("Opportunity Engine is up. Press Ctrl+C to stop.")
        await shutdown_event.wait()

    except Exception as exc:
        logger.error("Fatal error: %s", exc, exc_info=True)
    finally:
        logger.info("Shutting down...")
        if scheduler:
            scheduler.shutdown(wait=False)
            logger.info("Scheduler stopped")
        if app:
            await stop_bot(app)
            logger.info("Telegram bot stopped")
        logger.info("Goodbye.")


def main() -> None:
    _setup_logging()
    args = _parse_args()

    logger.info("=" * 60)
    logger.info("  OPPORTUNITY ENGINE starting")
    logger.info("=" * 60)
    logger.info("  Bot:       %s", "ON" if not args.no_bot else "OFF")
    logger.info("  Scheduler: %s", "ON" if not args.bot_only else "OFF")
    logger.info("  Scan now:  %s", "YES" if args.scan_now else "NO")
    logger.info("=" * 60)

    try:
        asyncio.run(_main(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
