"""Background jobs.

Deliberately in-process (APScheduler) rather than an external cron: this is a
single-user local app, and a job that only runs while the app is running is
fine because every job here is catch-up based. Miss a week and the next run
generates everything that was due in the meantime.
"""

from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import settings
from app.db import SessionLocal
from app.services.portfolio import record_snapshot, refresh_prices
from app.services.recurring import generate_due_transactions

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()


def run_recurring_generation() -> None:
    """Generate any due recurring transactions. Safe to run at any time."""
    try:
        with SessionLocal() as session:
            result = generate_due_transactions(session)
        if result.created:
            logger.info("Recurring: created %s transaction(s)", result.created)
    except Exception:
        # A failing background job must never take the app down with it.
        logger.exception("Recurring generation failed")


def run_price_refresh() -> None:
    """Fetch the latest closes and record a portfolio snapshot."""
    try:
        with SessionLocal() as session:
            result = refresh_prices(session)
            record_snapshot(session)
        if result.failed_tickers:
            logger.warning(
                "Prices: %s updated, no fresh data for %s (last known kept)",
                result.prices_updated,
                ", ".join(result.failed_tickers),
            )
        else:
            logger.info("Prices: %s updated", result.prices_updated)
    except Exception:
        logger.exception("Price refresh failed")


def start_scheduler() -> None:
    if not settings.enable_scheduler:
        logger.info("Scheduler disabled by configuration")
        return

    # Just after midnight, so a charge due today appears on the day it is due.
    scheduler.add_job(
        run_recurring_generation,
        CronTrigger(hour=0, minute=5),
        id="recurring_generation",
        replace_existing=True,
        # If the app was asleep at the trigger time, still run when it wakes.
        misfire_grace_time=None,
        coalesce=True,
    )

    # After the US close (configurable), so the latest daily close exists.
    scheduler.add_job(
        run_price_refresh,
        CronTrigger(
            hour=settings.price_fetch_hour, minute=settings.price_fetch_minute
        ),
        id="price_refresh",
        replace_existing=True,
        misfire_grace_time=None,
        coalesce=True,
    )

    scheduler.start()
    logger.info("Scheduler started")


def shutdown_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
