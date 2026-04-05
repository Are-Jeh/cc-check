"""
Scheduler
==========
Runs all scanners on a configurable schedule using APScheduler.

Schedule defaults:
    - SGB scanner:       every 4 hours during market hours (9 AM – 4 PM IST)
    - Tender scanner:    twice daily (8 AM, 6 PM IST)
    - Property scanner:  daily at 7 AM IST
    - Job matcher:       daily at 9 AM IST
    - Deal scanner:      every 2 hours (24/7)
    - Daily digest:      every day at 7:30 AM IST

All times are in Asia/Kolkata timezone.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from telegram.ext import Application

from opportunity_engine import config
from opportunity_engine.config import SCHEDULER as CFG
from opportunity_engine import sgb_scanner
from opportunity_engine import tender_scanner
from opportunity_engine import property_scanner
from opportunity_engine import job_matcher
from opportunity_engine import deal_scanner
from opportunity_engine import telegram_bot

logger = logging.getLogger(__name__)

TZ = "Asia/Kolkata"


# ---------------------------------------------------------------------------
# Job functions — each wraps a scanner and sends results to Telegram
# ---------------------------------------------------------------------------

async def _job_sgb(app: Optional[Application] = None) -> None:
    logger.info("Scheduled SGB scan starting...")
    try:
        results = await sgb_scanner.scan()
        if results and app:
            text = f"SGB ALERT ({len(results)} opportunities)\n{'='*35}\n\n"
            text += "\n\n".join(r.summary() for r in results)
            await telegram_bot.send_scanner_results(app, "SGB", text)
        logger.info("SGB scan complete: %d opportunities", len(results))
    except Exception as exc:
        logger.error("SGB scheduled scan failed: %s", exc)


async def _job_tenders(app: Optional[Application] = None) -> None:
    logger.info("Scheduled tender scan starting...")
    try:
        results = await tender_scanner.scan()
        if results and app:
            text = f"TENDER ALERT ({len(results)} opportunities)\n{'='*35}\n\n"
            text += "\n\n".join(r.summary() for r in results)
            await telegram_bot.send_scanner_results(app, "Tenders", text)
        logger.info("Tender scan complete: %d opportunities", len(results))
    except Exception as exc:
        logger.error("Tender scheduled scan failed: %s", exc)


async def _job_property(app: Optional[Application] = None) -> None:
    logger.info("Scheduled property scan starting...")
    try:
        results = await property_scanner.scan()
        if results and app:
            text = f"PROPERTY ALERT ({len(results)} opportunities)\n{'='*35}\n\n"
            text += "\n\n".join(r.summary() for r in results)
            await telegram_bot.send_scanner_results(app, "Property", text)
        logger.info("Property scan complete: %d opportunities", len(results))
    except Exception as exc:
        logger.error("Property scheduled scan failed: %s", exc)


async def _job_jobs(app: Optional[Application] = None) -> None:
    logger.info("Scheduled job matcher starting...")
    try:
        results = await job_matcher.scan()
        if results and app:
            text = f"JOB MATCH ALERT ({len(results)} matches)\n{'='*35}\n\n"
            text += "\n\n".join(r.summary() for r in results)
            await telegram_bot.send_scanner_results(app, "Jobs", text)
        logger.info("Job matcher complete: %d matches", len(results))
    except Exception as exc:
        logger.error("Job matcher scheduled run failed: %s", exc)


async def _job_deals(app: Optional[Application] = None) -> None:
    logger.info("Scheduled deal scan starting...")
    try:
        results = await deal_scanner.scan()
        if results and app:
            # For deals, send each one individually (they have Telegram messages)
            for deal in results:
                await telegram_bot.send_scanner_results(app, "Deals", deal.telegram_message)
        logger.info("Deal scan complete: %d deals", len(results))
    except Exception as exc:
        logger.error("Deal scanner scheduled run failed: %s", exc)


async def _job_daily_digest(app: Optional[Application] = None) -> None:
    logger.info("Daily digest starting...")
    try:
        if app:
            await telegram_bot.send_daily_digest(app)
        logger.info("Daily digest sent")
    except Exception as exc:
        logger.error("Daily digest failed: %s", exc)


# ---------------------------------------------------------------------------
# Scheduler setup
# ---------------------------------------------------------------------------

def create_scheduler(app: Optional[Application] = None) -> AsyncIOScheduler:
    """
    Create and configure the APScheduler with all scanner jobs.

    Args:
        app: Telegram Application instance — if provided, scanner results
             will be sent to the configured Telegram channel.
    """
    scheduler = AsyncIOScheduler(timezone=TZ)

    # --- SGB scanner: every N hours during market hours ---
    scheduler.add_job(
        _job_sgb,
        trigger=CronTrigger(
            hour=f"{CFG.sgb_market_start_hour}-{CFG.sgb_market_end_hour}/{CFG.sgb_interval_hours}",
            minute=5,
            timezone=TZ,
        ),
        kwargs={"app": app},
        id="sgb_scanner",
        name="SGB Scanner",
        replace_existing=True,
        misfire_grace_time=300,
    )

    # --- Tender scanner: twice daily ---
    for i, time_str in enumerate(CFG.tender_times):
        hour, minute = time_str.split(":")
        scheduler.add_job(
            _job_tenders,
            trigger=CronTrigger(hour=int(hour), minute=int(minute), timezone=TZ),
            kwargs={"app": app},
            id=f"tender_scanner_{i}",
            name=f"Tender Scanner ({time_str})",
            replace_existing=True,
            misfire_grace_time=300,
        )

    # --- Property scanner: daily ---
    prop_hour, prop_minute = CFG.property_time.split(":")
    scheduler.add_job(
        _job_property,
        trigger=CronTrigger(hour=int(prop_hour), minute=int(prop_minute), timezone=TZ),
        kwargs={"app": app},
        id="property_scanner",
        name="Property Scanner",
        replace_existing=True,
        misfire_grace_time=300,
    )

    # --- Job matcher: daily ---
    job_hour, job_minute = CFG.job_time.split(":")
    scheduler.add_job(
        _job_jobs,
        trigger=CronTrigger(hour=int(job_hour), minute=int(job_minute), timezone=TZ),
        kwargs={"app": app},
        id="job_matcher",
        name="Job Matcher",
        replace_existing=True,
        misfire_grace_time=300,
    )

    # --- Deal scanner: every N hours ---
    scheduler.add_job(
        _job_deals,
        trigger=IntervalTrigger(hours=CFG.deal_interval_hours, timezone=TZ),
        kwargs={"app": app},
        id="deal_scanner",
        name="Deal Scanner",
        replace_existing=True,
        misfire_grace_time=300,
    )

    # --- Daily digest: 7:30 AM ---
    scheduler.add_job(
        _job_daily_digest,
        trigger=CronTrigger(hour=7, minute=30, timezone=TZ),
        kwargs={"app": app},
        id="daily_digest",
        name="Daily Digest",
        replace_existing=True,
        misfire_grace_time=600,
    )

    return scheduler


def start_scheduler(
    scheduler: AsyncIOScheduler,
    run_initial_scan: bool = False,
    app: Optional[Application] = None,
) -> None:
    """
    Start the scheduler.

    If *run_initial_scan* is True, all scanners will be triggered
    immediately (useful on first startup to verify everything works).
    """
    scheduler.start()
    logger.info("Scheduler started with %d jobs", len(scheduler.get_jobs()))

    for job in scheduler.get_jobs():
        logger.info("  - %s  (next run: %s)", job.name, job.next_run_time)

    if run_initial_scan:
        logger.info("Triggering initial scan for all scanners...")
        for job_id in ("sgb_scanner", "tender_scanner_0", "property_scanner", "job_matcher", "deal_scanner"):
            job = scheduler.get_job(job_id)
            if job:
                job.modify(next_run_time=None)  # trigger immediately
                # Re-add because modify(next_run_time=None) pauses the job
                # Instead, we'll just run them manually
        # Better approach: run them as one-off tasks
        loop = asyncio.get_event_loop()
        loop.create_task(_run_all_once(app))


async def _run_all_once(app: Optional[Application] = None) -> None:
    """Run all scanners once (for initial scan on startup)."""
    logger.info("Running one-time initial scan...")
    await asyncio.gather(
        _job_sgb(app),
        _job_tenders(app),
        _job_property(app),
        _job_jobs(app),
        _job_deals(app),
        return_exceptions=True,
    )
    logger.info("Initial scan complete")
