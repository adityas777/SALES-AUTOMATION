"""Orchestrates one outreach send (first touch or a follow-up) for one
business: template+media selection -> personalization -> send -> log -> status
update. Used by both the initial pipeline (Phase 5-7) and the follow-up
scheduler (Phase 8), so the two never drift apart.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from src.storage.airtable_client import get_client
from src.storage.schema import BusinessFields as BF, BusinessStatus, Channel, Direction
from src.routing import template_selector
from src.personalization import groq_personalizer
from src.senders import email_sender, whatsapp_sender

logger = logging.getLogger(__name__)


def _next_status(current_status: str) -> str:
    sequence = BusinessStatus.FOLLOW_UP_SEQUENCE
    if current_status not in sequence:
        return BusinessStatus.CONTACTED
    idx = sequence.index(current_status)
    return sequence[min(idx + 1, len(sequence) - 1)]


def send_outreach_to_business(business: dict) -> dict:
    """`business` is an Airtable record dict ({"id": ..., "fields": {...}}).
    Sends email always (if an email address exists); sends WhatsApp too if
    the category's template is approved+enabled AND a phone number exists.
    Returns a summary dict for logging/testing."""
    client = get_client()
    fields = business["fields"]
    business_id = business["id"]

    name = fields.get(BF.NAME, "")
    category = fields.get(BF.CATEGORY, "")
    city = fields.get(BF.CITY, "")
    email = fields.get(BF.EMAIL)
    phone = fields.get(BF.PHONE)
    current_status = fields.get(BF.STATUS, BusinessStatus.NEW)

    sent_channels = []

    if email:
        try:
            rendered = groq_personalizer.render_email(name, category, city)
            email_media = rendered["media"]
            email_sender.send_email(email, rendered["subject"], rendered["html_body"], email_media)
            client.log_interaction(
                business_id, Channel.EMAIL, Direction.OUTBOUND,
                message_body=rendered["html_body"], template_used=f"{category}/email",
            )
            sent_channels.append("email")
        except Exception:
            logger.exception("Email send failed for business %s", business_id)

    if phone and template_selector.whatsapp_enabled(category):
        try:
            selection = template_selector.select(category, "whatsapp")
            variables = groq_personalizer.build_whatsapp_variables(name, category, city)
            media_id = None
            media_type = None
            if selection["media"] and selection["media"]["exists"]:
                media_type = selection["media"]["type"]
                media_id = whatsapp_sender.upload_media_and_get_id(
                    selection["media"]["path"], mime_type="image/jpeg" if media_type == "image" else "video/mp4"
                )
            whatsapp_sender.send_template_message(
                phone, selection["template_name"], selection["language"], variables, media_id, media_type,
            )
            client.log_interaction(
                business_id, Channel.WHATSAPP, Direction.OUTBOUND,
                message_body=str(variables), template_used=selection["template_name"],
            )
            sent_channels.append("whatsapp")
        except Exception:
            logger.exception("WhatsApp send failed for business %s", business_id)

    if sent_channels:
        new_status = _next_status(current_status)
        client.update_status(business_id, new_status, extra_fields={
            BF.LAST_CONTACTED: datetime.now(timezone.utc).date().isoformat(),
            BF.FOLLOW_UP_COUNT: fields.get(BF.FOLLOW_UP_COUNT, 0) + (1 if current_status != BusinessStatus.NEW else 0),
            BF.ASSIGNED_TEMPLATE: category,
        })

    return {"business_id": business_id, "sent_channels": sent_channels}
