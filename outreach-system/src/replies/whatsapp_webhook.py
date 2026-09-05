"""WhatsApp inbound webhook (spec Phase 9).

Setup needed: Meta Business Manager > WhatsApp > Configuration > Webhook.
  - Callback URL: https://<your-deployed-host>/webhooks/whatsapp
  - Verify token: must match WHATSAPP_VERIFY_TOKEN in .env
  - Subscribe to the "messages" field.
Meta requires a public HTTPS URL, so this only works once deployed (Railway/
Render free tier both give you one) - for local testing, use a curl payload
shaped like Meta's format (see tests/) or an ngrok tunnel.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Query, Request, Response

from src.settings import settings
from src.storage.airtable_client import get_client
from src.replies.reply_handler import handle_inbound_reply
from src.storage.schema import Channel

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/webhooks/whatsapp")
def verify_webhook(
    hub_mode: str = Query(alias="hub.mode"),
    hub_challenge: str = Query(alias="hub.challenge"),
    hub_verify_token: str = Query(alias="hub.verify_token"),
):
    if hub_mode == "subscribe" and hub_verify_token == settings.whatsapp_verify_token:
        return Response(content=hub_challenge, media_type="text/plain")
    return Response(status_code=403)


@router.post("/webhooks/whatsapp")
async def receive_webhook(request: Request):
    payload = await request.json()
    client = get_client()

    try:
        entries = payload.get("entry", [])
        for entry in entries:
            for change in entry.get("changes", []):
                value = change.get("value", {})
                for message in value.get("messages", []):
                    sender_phone = "+" + message.get("from", "").lstrip("+")
                    text = message.get("text", {}).get("body", "")
                    if not text:
                        continue  # skip non-text messages (media/reactions) for MVP

                    business = client.find_business_by_phone(sender_phone)
                    if not business:
                        logger.warning("No business found for inbound WhatsApp from %s", sender_phone)
                        continue

                    handle_inbound_reply(business["id"], Channel.WHATSAPP, text)
    except Exception:
        logger.exception("Failed to process WhatsApp webhook payload")

    return {"status": "ok"}
