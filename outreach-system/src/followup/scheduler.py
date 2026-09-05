"""Follow-up engine (spec Phase 8).

A daily APScheduler job scans every business not in a stop status, and for
each one whose `Last Contacted` is far enough in the past for its current
Follow-up Count (per config/follow_up_policy.yaml's cadence_days), re-runs
the outreach send. Any inbound reply or explicit opt-out (Phase 9/10) flips
Status to a stop_statuses value immediately, so the next sweep naturally
excludes that business - no separate "cancel follow-up" step needed.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, time as dt_time

from apscheduler.schedulers.background import BackgroundScheduler

from src.storage.airtable_client import get_client
from src.storage.schema import BusinessFields as BF, BusinessStatus
from src.config_loader import get_follow_up_policy
from src.outreach import send_outreach_to_business
from src.replies.email_poller import poll_inbox_for_replies

logger = logging.getLogger(__name__)


def _in_quiet_hours(now: datetime) -> bool:
    policy = get_follow_up_policy()
    start = dt_time.fromisoformat(policy["quiet_hours"]["start"])
    end = dt_time.fromisoformat(policy["quiet_hours"]["end"])
    current = now.time()
    if start <= end:
        return start <= current <= end
    return current >= start or current <= end  # wraps past midnight


def _days_since(date_str: str | None, now: datetime) -> int | None:
    if not date_str:
        return None
    last = datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc)
    return (now.date() - last.date()).days


def _is_due(fields: dict, policy: dict, now: datetime) -> bool:
    status = fields.get(BF.STATUS, BusinessStatus.NEW)
    if status not in BusinessStatus.FOLLOW_UP_SEQUENCE:
        return False  # not contacted yet, or already terminal (excluded upstream too)

    follow_up_count = fields.get(BF.FOLLOW_UP_COUNT, 0)
    if follow_up_count >= policy["max_follow_ups"]:
        return False

    days_elapsed = _days_since(fields.get(BF.LAST_CONTACTED), now)
    if days_elapsed is None:
        return False

    cadence = policy["cadence_days"]
    required_gap = cadence[min(follow_up_count, len(cadence) - 1)]
    return days_elapsed >= required_gap


def run_followup_sweep() -> int:
    now = datetime.now(timezone.utc)
    if _in_quiet_hours(now):
        logger.info("Skipping follow-up sweep - inside quiet hours")
        return 0

    policy = get_follow_up_policy()
    client = get_client()
    due_businesses = [
        b for b in client.businesses_due_for_followup()
        if _is_due(b["fields"], policy, now)
    ]

    sent = 0
    for business in due_businesses:
        try:
            result = send_outreach_to_business(business)
            if result["sent_channels"]:
                sent += 1
        except Exception:
            logger.exception("Follow-up send failed for business %s", business["id"])

    logger.info("Follow-up sweep complete: %d/%d businesses contacted", sent, len(due_businesses))
    return sent


def start_scheduler() -> BackgroundScheduler:
    """Single scheduler for both background jobs, so app.py only needs one
    call on startup. Change cadence here - no other file needs to know."""
    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(run_followup_sweep, "cron", hour=10, minute=0, id="daily_followup_sweep")
    scheduler.add_job(poll_inbox_for_replies, "interval", minutes=15, id="email_reply_poll")
    scheduler.start()
    logger.info("Schedulers started: daily follow-up sweep (10:00 UTC), email poll (every 15 min)")
    return scheduler
