"""WhatsApp Cloud API sender (spec Phase 7).

Setup needed before this works (do this in parallel while building the email
path first - it takes days for Meta to approve templates):
  1. Meta Business Manager -> create/verify a WhatsApp Business Account +
     phone number (Business Manager > WhatsApp > API Setup gives you a test
     number immediately for development).
  2. Submit each category's template under Business Manager > Account tools >
     Message templates. Name it exactly what config/templates.yaml expects
     (e.g. "dance_academy_intro_v1"), category=MARKETING or UTILITY, with
     {{1}}, {{2}}, {{3}} placeholders matching build_whatsapp_variables()'s
     order (business_name, category_label, city).
  3. If a category's template has a media (image/video) header, upload the
     asset once via upload_media_and_get_id() below and keep the returned
     media ID - Meta requires the media to be part of the approved template
     header, referenced by ID at send time (not attached ad hoc).
  4. Put WHATSAPP_TOKEN and WHATSAPP_PHONE_NUMBER_ID (from API Setup) in .env.
  5. Only flip `use_whatsapp: true` in config/templates.yaml for a category
     once its template is actually APPROVED - sending against a pending/
     rejected template name fails.

Meta gives 1,000 free service conversations/month per WhatsApp Business
Account; template (business-initiated) conversations beyond that are billed
per-conversation but are the cheapest official route (spec §1).
"""
from __future__ import annotations

import logging
from pathlib import Path

import httpx

from src.settings import settings

logger = logging.getLogger(__name__)

GRAPH_API_VERSION = "v20.0"
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"


def _auth_headers() -> dict:
    return {"Authorization": f"Bearer {settings.whatsapp_token}"}


def upload_media_and_get_id(file_path: str, mime_type: str) -> str:
    """One-time (per asset) upload via the Media endpoint. Returns a media ID
    to reference from an approved template's media header at send time."""
    url = f"{GRAPH_BASE}/{settings.whatsapp_phone_number_id}/media"
    path = Path(file_path)
    with open(path, "rb") as f:
        files = {"file": (path.name, f, mime_type)}
        data = {"messaging_product": "whatsapp"}
        resp = httpx.post(url, headers=_auth_headers(), data=data, files=files, timeout=60)
    resp.raise_for_status()
    return resp.json()["id"]


def send_template_message(
    to_phone: str,
    template_name: str,
    language: str,
    variables: list[str],
    media_id: str | None = None,
    media_type: str | None = None,  # "image" | "video" | "document"
) -> dict:
    """Sends an approved WhatsApp template message. `variables` fill the
    template's {{1}}, {{2}}, ... body placeholders in order."""
    components = [
        {
            "type": "body",
            "parameters": [{"type": "text", "text": v} for v in variables],
        }
    ]
    if media_id and media_type:
        components.insert(0, {
            "type": "header",
            "parameters": [{"type": media_type, media_type: {"id": media_id}}],
        })

    payload = {
        "messaging_product": "whatsapp",
        "to": to_phone,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language},
            "components": components,
        },
    }

    url = f"{GRAPH_BASE}/{settings.whatsapp_phone_number_id}/messages"
    resp = httpx.post(url, headers={**_auth_headers(), "Content-Type": "application/json"}, json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()
