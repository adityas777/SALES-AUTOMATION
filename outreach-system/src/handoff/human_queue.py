"""Human handoff (spec Phase 11).

High-intent labels (Interested / Pricing / Call Requested / Human Review) get
a row in Airtable's HumanHandoffQueue plus a Slack ping. A human resolves by
checking the "Resolved" box in Airtable directly - Airtable is the CRM, no
separate UI at MVP stage.

Setup needed: create a Slack Incoming Webhook (Slack app -> Incoming
Webhooks -> Add New Webhook) and put the URL in .env as SLACK_WEBHOOK_URL.
Optional - if left blank, handoff still writes to Airtable, it just skips
the Slack ping.
"""
from __future__ import annotations

import logging

import httpx

from src.settings import settings
from src.storage.airtable_client import get_client
from src.storage.schema import BusinessFields as BF, BusinessStatus, AIClassificationLabel as Label

logger = logging.getLogger(__name__)

PRIORITY_BY_LABEL = {
    Label.INTERESTED: "High",
    Label.CALL_REQUESTED: "High",
    Label.PRICING: "Normal",
    Label.HUMAN_REVIEW: "Normal",
}


def _airtable_record_url(business_id: str) -> str:
    return f"https://airtable.com/{settings.airtable_base_id}/{business_id}"


def _notify_slack(business_name: str, category: str, city: str, last_message: str, record_url: str) -> None:
    if not settings.slack_webhook_url:
        return
    text = (
        f":raising_hand: *Human follow-up needed*\n"
        f"*{business_name}* ({category}, {city})\n"
        f"Last message: {last_message[:280]}\n"
        f"<{record_url}|Open in Airtable>"
    )
    try:
        httpx.post(settings.slack_webhook_url, json={"text": text}, timeout=10)
    except httpx.HTTPError:
        logger.exception("Slack notification failed")


def escalate_to_human(business_id: str, label: str, last_message: str) -> None:
    client = get_client()
    business = client.get_business(business_id)
    fields = business["fields"]

    priority = PRIORITY_BY_LABEL.get(label, "Normal")
    client.add_to_handoff_queue(business_id, reason=f"AI classified reply as '{label}'", priority=priority)
    client.update_status(business_id, BusinessStatus.NEEDS_HUMAN)

    _notify_slack(
        fields.get(BF.NAME, ""), fields.get(BF.CATEGORY, ""), fields.get(BF.CITY, ""),
        last_message, _airtable_record_url(business_id),
    )
