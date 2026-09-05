"""Personalization engine (spec Phase 6), backed by Groq.

WhatsApp: Meta only allows variable substitution inside an approved template
(the {{1}}, {{2}}... slots) - the template's core text can never be
rewritten. So `build_whatsapp_variables()` does plain string substitution,
no LLM call, by design (this is a compliance boundary, not a shortcut).

Email: no such restriction, so Groq can lightly personalize the pre-written
base copy using a short scraped snippet (e.g. the business's own tagline),
but it is instructed to only ADD a short, grounded opening line - never
invent claims, never touch pricing/promises, and output is length-capped and
stripped of markdown before it's logged and sent.
"""
from __future__ import annotations

import logging
import re

from groq import Groq

from src.settings import settings
from src.routing import template_selector

logger = logging.getLogger(__name__)

WHATSAPP_MODEL = "openai/gpt-oss-20b"
EMAIL_MODEL = "openai/gpt-oss-20b"
MAX_OPENER_CHARS = 220

CATEGORY_LABELS = {
    "dance": "dance academy",
    "yoga": "yoga studio",
    "gym_fitness": "gym/fitness center",
    "photography": "photography studio",
    "music_recording": "music school/recording studio",
    "schools_colleges": "school/college/coaching institute",
    "sports": "sports academy",
    "event_venues": "event venue/banquet hall",
    "cafes_restaurants": "cafe/restaurant",
    "coworking": "coworking space",
    "art_studios": "art studio",
    "salons": "salon/spa",
    "theatres": "theatre",
    "activity_centres": "activity centre",
}

_client: Groq | None = None


def _groq() -> Groq:
    global _client
    if _client is None:
        _client = Groq(api_key=settings.groq_api_key)
    return _client


def category_label(category: str) -> str:
    return CATEGORY_LABELS.get(category, category.replace("_", " "))


def _strip_markdown(text: str) -> str:
    text = re.sub(r"[*_`#>]", "", text)
    return text.strip()


def build_whatsapp_variables(business_name: str, category: str, city: str) -> list[str]:
    """Order matters - must match the {{1}}, {{2}}, {{3}} slot order of the
    approved template exactly. No LLM involved (see module docstring)."""
    return [business_name, category_label(category), city]


def _draft_opener_with_groq(business_name: str, category: str, city: str, scraped_snippet: str) -> str | None:
    """Optional short opener line grounded ONLY in the scraped snippet
    (e.g. business's own website tagline). Returns None on any failure or
    if the model output looks unsafe/too long - callers fall back to the
    static hook already baked into the email template."""
    if not settings.groq_api_key or not scraped_snippet:
        return None

    system_prompt = (
        "You write a single short opening sentence for a cold outreach email to a local "
        "business. Ground it ONLY in the provided snippet from the business's own website. "
        "Never invent facts, numbers, awards, or claims not present in the snippet. "
        "Never mention pricing. No markdown. One sentence, under 30 words."
    )
    user_prompt = (
        f"Business name: {business_name}\n"
        f"Category: {category_label(category)}\n"
        f"City: {city}\n"
        f"Snippet from their website: {scraped_snippet[:500]}\n\n"
        "Write the one-sentence opener now."
    )

    try:
        completion = _groq().chat.completions.create(
            model=EMAIL_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.4,
            # gpt-oss-20b is a reasoning model - it spends tokens on an internal
            # chain-of-thought before the final sentence, so this needs much more
            # headroom than the ~30-word output alone would suggest, or the
            # response gets cut off mid-reasoning with no visible answer.
            max_tokens=400,
        )
        text = _strip_markdown(completion.choices[0].message.content or "")
        if not text or len(text) > MAX_OPENER_CHARS:
            return None
        return text
    except Exception:
        logger.exception("Groq opener generation failed, falling back to static hook")
        return None


def _media_block_html(media: dict | None) -> str:
    if not media or not media.get("exists"):
        return ""
    if media["type"] == "image":
        # Assumes email_sender.py attaches/inlines the file separately (cid) or
        # hosts it and swaps this for a real <img src>; kept as a simple caption here.
        return '<p><em>(see attached image)</em></p>'
    return f'<p><a href="{media["path"]}">View {media["type"]}</a></p>'


def render_email(business_name: str, category: str, city: str, scraped_snippet: str = "") -> dict:
    """Returns {"subject": str, "html_body": str, "media": dict|None}."""
    selection = template_selector.select(category, "email")
    subject = selection["subject"].replace("{{business_name}}", business_name)

    template_path = template_selector.PROJECT_ROOT / selection["body_template_path"]
    with open(template_path, "r", encoding="utf-8") as f:
        body = f.read()

    body = (
        body.replace("{{business_name}}", business_name)
        .replace("{{category}}", category_label(category))
        .replace("{{city}}", city)
        .replace("{{media_block}}", _media_block_html(selection["media"]))
    )

    opener = _draft_opener_with_groq(business_name, category, city, scraped_snippet)
    if opener:
        body = body.replace("<p>Hi {{business_name}} team,</p>", "")  # already substituted above, no-op guard
        body = body.replace(
            f"<p>Hi {business_name} team,</p>",
            f"<p>Hi {business_name} team,</p>\n<p>{opener}</p>",
        )

    return {"subject": subject, "html_body": body, "media": selection["media"]}
