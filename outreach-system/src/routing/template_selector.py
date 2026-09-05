"""Template + media selector (spec Phase 5).

Pure config lookup: category -> {whatsapp/email template, media asset}.
Reads YAML first (version-controlled source of truth); an Airtable
`Templates` table mirror can be layered in later as a fallback for
non-technical editing without touching this function's contract.
"""
from __future__ import annotations

from pathlib import Path

from src.config_loader import get_templates, get_media_library

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class TemplateNotConfigured(Exception):
    pass


def select(category: str, channel: str) -> dict:
    """channel: 'whatsapp' | 'email'"""
    templates = get_templates()
    media_library = get_media_library()

    if category not in templates:
        raise TemplateNotConfigured(f"No template configured for category '{category}'")

    category_cfg = templates[category]
    if channel not in category_cfg:
        raise TemplateNotConfigured(f"No '{channel}' template configured for category '{category}'")

    channel_cfg = dict(category_cfg[channel])
    media_cfg = media_library.get(category)

    result = {**channel_cfg, "category": category, "channel": channel}
    if media_cfg:
        media_path = PROJECT_ROOT / media_cfg["path"]
        result["media"] = {**media_cfg, "exists": media_path.exists()}
    else:
        result["media"] = None

    if channel == "whatsapp":
        result["enabled"] = category_cfg.get("use_whatsapp", False)

    return result


def whatsapp_enabled(category: str) -> bool:
    templates = get_templates()
    return bool(templates.get(category, {}).get("use_whatsapp", False))
