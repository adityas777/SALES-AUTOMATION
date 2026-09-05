"""AI reply classifier (spec Phase 10).

Groq call with a fixed system prompt enumerating exactly the 9 allowed
labels, instructed to respond with only a JSON object (parsed defensively,
see classify_reply). Confidence < 0.6 is always forced to "Human Review" -
the system never guesses on an ambiguous reply, it escalates instead.
"""
from __future__ import annotations

import json
import logging
import re

from groq import Groq

from src.settings import settings
from src.storage.schema import AIClassificationLabel as Label

logger = logging.getLogger(__name__)

CLASSIFIER_MODEL = "openai/gpt-oss-120b"
CONFIDENCE_THRESHOLD = 0.6

SYSTEM_PROMPT = f"""You classify a reply to a business-outreach WhatsApp/email message into
EXACTLY ONE of these 9 labels - use this exact spelling:
{", ".join(Label.ALL)}

Guidance:
- "Interested": clearly wants to move forward / learn more with intent to proceed.
- "More Information": asks generic questions, not yet signaling intent.
- "Pricing": asks about cost/rates/packages.
- "Call Requested": explicitly asks for a phone call or to be called.
- "Follow Later": asks to be contacted later / busy now but not a no.
- "Not Interested": politely or bluntly declines.
- "Wrong Number": says this isn't their business / wrong contact.
- "Opt-out": says stop, unsubscribe, remove me, or similar.
- "Human Review": anything ambiguous, off-topic, or you are not confident about.

Respond with ONLY a JSON object: {{"label": "<one of the 9 labels above>", "confidence": <0.0-1.0>}}
No other text."""

FEW_SHOT_EXAMPLES = [
    {"role": "user", "content": "Reply: 'Yes please tell me more, we'd love a demo!'"},
    {"role": "assistant", "content": '{"label": "Interested", "confidence": 0.95}'},
    {"role": "user", "content": "Reply: 'How much does this cost per month?'"},
    {"role": "assistant", "content": '{"label": "Pricing", "confidence": 0.9}'},
    {"role": "user", "content": "Reply: 'STOP'"},
    {"role": "assistant", "content": '{"label": "Opt-out", "confidence": 0.99}'},
    {"role": "user", "content": "Reply: 'Not interested, thanks'"},
    {"role": "assistant", "content": '{"label": "Not Interested", "confidence": 0.9}'},
    {"role": "user", "content": "Reply: 'You have the wrong number'"},
    {"role": "assistant", "content": '{"label": "Wrong Number", "confidence": 0.95}'},
    {"role": "user", "content": "Reply: 'Can someone call me tomorrow morning?'"},
    {"role": "assistant", "content": '{"label": "Call Requested", "confidence": 0.9}'},
    {"role": "user", "content": "Reply: 'ok'"},
    {"role": "assistant", "content": '{"label": "Human Review", "confidence": 0.3}'},
]

_client: Groq | None = None


def _groq() -> Groq:
    global _client
    if _client is None:
        _client = Groq(api_key=settings.groq_api_key)
    return _client


# Explicit opt-out keywords are checked BEFORE calling the model - cheap,
# deterministic, and guarantees "stop" always works even if the API is down.
OPT_OUT_KEYWORDS = {"stop", "unsubscribe", "remove me", "opt out", "opt-out"}


def classify_reply(message_text: str) -> dict:
    """Returns {"label": str, "confidence": float}."""
    normalized = (message_text or "").strip().lower()
    if normalized in OPT_OUT_KEYWORDS or any(k in normalized for k in OPT_OUT_KEYWORDS):
        return {"label": Label.OPT_OUT, "confidence": 1.0}

    if not settings.groq_api_key:
        logger.warning("GROQ_API_KEY not set - defaulting reply to Human Review")
        return {"label": Label.HUMAN_REVIEW, "confidence": 0.0}

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        *FEW_SHOT_EXAMPLES,
        {"role": "user", "content": f"Reply: {message_text!r}"},
    ]

    try:
        # No response_format constraint: gpt-oss models are reasoning models
        # that emit chain-of-thought on a separate channel before the final
        # answer - Groq's strict json_object validator rejects that combo
        # (empty/invalid content). The system prompt's own "respond with ONLY
        # a JSON object" instruction is enough once max_tokens gives the
        # reasoning trace room to finish before the final answer is emitted.
        completion = _groq().chat.completions.create(
            model=CLASSIFIER_MODEL,
            messages=messages,
            temperature=0.0,
            max_tokens=500,
        )
        raw = completion.choices[0].message.content or ""
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        parsed = json.loads(match.group(0) if match else raw)
        label = parsed.get("label")
        confidence = float(parsed.get("confidence", 0.0))
    except Exception:
        logger.exception("Groq classification failed, forcing Human Review")
        return {"label": Label.HUMAN_REVIEW, "confidence": 0.0}

    if label not in Label.ALL:
        logger.warning("Groq returned unknown label %r, forcing Human Review", label)
        return {"label": Label.HUMAN_REVIEW, "confidence": confidence}

    if confidence < CONFIDENCE_THRESHOLD:
        return {"label": Label.HUMAN_REVIEW, "confidence": confidence}

    return {"label": label, "confidence": confidence}
