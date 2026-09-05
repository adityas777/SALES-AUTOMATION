"""Shared inbound-reply handling used by both whatsapp_webhook.py and
email_poller.py, so the two channels can never drift on classification ->
status mapping.

Rule from the brief: ANY inbound reply stops automated follow-ups (the
scheduler only re-contacts businesses still in Contacted/Follow-up N - see
followup/scheduler.py) - the AI Classification just decides how far it
escalates beyond that:
  - Not Interested / Opt-out / Wrong Number -> that specific terminal status.
  - Interested / Pricing / Call Requested / Human Review -> human handoff.
  - More Information / Follow Later -> "Responded" (still stops follow-ups,
    no dedicated status/handoff needed - a human can pick it up from Airtable
    at their own pace).
"""
from __future__ import annotations

import logging

from src.storage.airtable_client import get_client
from src.storage.schema import BusinessStatus, AIClassificationLabel as Label, Direction
from src.replies.ai_classifier import classify_reply
from src.handoff.human_queue import escalate_to_human

logger = logging.getLogger(__name__)

_STATUS_BY_LABEL = {
    Label.NOT_INTERESTED: BusinessStatus.NOT_INTERESTED,
    Label.OPT_OUT: BusinessStatus.OPT_OUT,
    Label.WRONG_NUMBER: BusinessStatus.WRONG_NUMBER,
}


def handle_inbound_reply(business_id: str, channel: str, message_text: str) -> dict:
    client = get_client()
    classification = classify_reply(message_text)
    label = classification["label"]

    client.log_interaction(
        business_id, channel, Direction.INBOUND, message_text, ai_classification=label,
    )

    if label in Label.HANDOFF_LABELS:
        escalate_to_human(business_id, label, message_text)
    else:
        new_status = _STATUS_BY_LABEL.get(label, BusinessStatus.RESPONDED)
        client.update_status(business_id, new_status)

    logger.info("Inbound reply from business %s classified as %s", business_id, label)
    return classification
