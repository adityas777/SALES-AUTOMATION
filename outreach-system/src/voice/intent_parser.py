"""Natural language intent and entity parser for voice commands.
Extracts target city, category keys, and generates a friendly voice response.
Supports state-aware classification (IDLE, CONFIRMING, RUNNING).
Backed by Groq with rule-based fast path & fallback.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Optional

from groq import Groq

from src.config_loader import get_categories, get_locations
from src.settings import settings

logger = logging.getLogger(__name__)

PARSER_MODEL = "openai/gpt-oss-120b"
_client: Optional[Groq] = None


def _groq() -> Groq:
    global _client
    if _client is None:
        _client = Groq(api_key=settings.groq_api_key)
    return _client


def _get_category_metadata() -> dict[str, list[str]]:
    """Returns mapping of category_key -> list of search terms/aliases."""
    cats = get_categories()
    result = {}
    for k, v in cats.items():
        terms = list(v.get("search_terms", []))
        terms.append(k.replace("_", " "))
        result[k] = terms
    return result


def _get_known_cities() -> list[str]:
    try:
        locs = get_locations()
        return [c["name"] for c in locs.get("active_cities", [])]
    except Exception:
        return ["Bhilai, Chhattisgarh", "Raipur, Chhattisgarh", "Durg, Chhattisgarh"]


# ── State-Aware Regex Patterns (English + Hindi/Hinglish) ─────────────────

_CONFIRM_PATTERNS = re.compile(
    r"\b(yes|yeah|yep|yup|ok|okay|sure|confirm|go\s*ahead|start(\s*it)?|launch(\s*it)?|"
    r"sounds?\s*(good|great|perfect|nice|fine)|looks?\s*(good|great|perfect)|"
    r"go\s*for\s*it|let'?s\s*go|do\s*it|proceed|theek\s*hai|thik\s*hai|haan(\s*kar\s*do)?|"
    r"han(\s*kar\s*do)?|ha|chalo(\s*shuru\s*karo)?|shuru\s*karo|sahi\s*hai|bilkul|karo|chalne\s*do|"
    r"absolutely|perfect|great)\b",
    re.IGNORECASE,
)

_CANCEL_PATTERNS = re.compile(
    r"\b(no|nope|cancel|stop|never\s*mind|rehne\s*do|rehney\s*do|nahi|naa|ruk|band\s*karo|"
    r"abort|quit|exit|close)\b",
    re.IGNORECASE,
)

_STATUS_PATTERNS = re.compile(
    r"\b(updates?|status|progress|how'?s\s*it(\s*going)?|what'?s\s*(the\s*)?(current\s*)?update|"
    r"what'?s\s*(the\s*)?(current\s*)?status|tell\s*me\s*(about\s*)?(the\s*)?updates?|"
    r"give\s*me\s*(an?\s*)?update|show\s*(me\s*)?updates?|any\s*updates?|"
    r"how\s*many\s*(leads|messages|contacts|calls|sent)?|"
    r"kitna\s*hua|kitne\s*leads|kya\s*update|kya\s*status|summary|reports?|results?|numbers|stats?|dashboard)\b",
    re.IGNORECASE,
)

_EDIT_PATTERNS = re.compile(
    r"\b(make\s*it|change\s*to|add|remove|hata\s*do|instead\s*of|only|bhi\s*add|include)\b",
    re.IGNORECASE,
)

_SEARCH_INDICATORS = re.compile(
    r"\b(find|search|look|get|collect|studio|gym|school|salon|restaurant|cafe|"
    r"photography|music|dance|yoga|sport|theatre|coworking|activity|event|"
    r"dhundho|khojo)\b",
    re.IGNORECASE,
)


def classify_intent(text: str, current_state: str = "IDLE") -> str:
    """Classifies user intent given transcript and state.

    Returns: 'confirm', 'cancel', 'status_update', 'edit', 'search', or 'unknown'.
    """
    cleaned = (text or "").strip().lower()
    if not cleaned:
        return "unknown"

    # Status query check always comes first regardless of state
    if _STATUS_PATTERNS.search(cleaned):
        return "status_update"

    state_upper = (current_state or "IDLE").upper()

    # When in CONFIRMING state (setup modal open with active slots)
    if state_upper in ("CONFIRMING", "SETUP"):
        if _CONFIRM_PATTERNS.search(cleaned):
            return "confirm"
        if _CANCEL_PATTERNS.search(cleaned):
            return "cancel"
        if _EDIT_PATTERNS.search(cleaned):
            return "edit"

    # General rules
    if _CANCEL_PATTERNS.search(cleaned) and len(cleaned.split()) <= 6:
        return "cancel"

    if _CONFIRM_PATTERNS.search(cleaned) and len(cleaned.split()) <= 8:
        return "confirm"

    if _SEARCH_INDICATORS.search(cleaned) or len(cleaned.split()) > 3:
        return "search"

    return "unknown"


def parse_voice_command(
    text: str,
    language_code: str = "en-IN",
    current_state: str = "IDLE",
    current_city: str = "",
    current_categories: list[str] | None = None,
) -> dict:
    """Parses a spoken or typed command into intent, city, and canonical categories.

    Context-aware & conservative slot handling:
      - In CONFIRMING state, confirm/cancel words maintain existing slots.
      - Edit commands update only mentioned slots and preserve the rest.
      - Status queries return status_update without clearing slots.
    """
    cleaned_text = (text or "").strip()
    curr_city = (current_city or "").strip()
    curr_cats = list(current_categories or [])
    state_upper = (current_state or "IDLE").upper()

    if not cleaned_text:
        return {
            "intent": "unknown",
            "city": curr_city,
            "categories": curr_cats,
            "spoken_response": "I didn't catch that. Could you please specify a city or category?",
            "confidence": 0.0,
            "raw_text": "",
        }

    category_meta = _get_category_metadata()
    valid_categories = list(category_meta.keys())
    known_cities = _get_known_cities()

    # Rule-based fast path intent check
    quick_intent = classify_intent(cleaned_text, current_state=state_upper)

    # Fast path: status queries
    if quick_intent == "status_update":
        return {
            "intent": "status_update",
            "city": curr_city,
            "categories": curr_cats,
            "spoken_response": "",  # Filled by smart summary endpoint
            "confidence": 0.95,
            "raw_text": cleaned_text,
        }

    # Fast path: confirmation or cancellation in CONFIRMING state
    if state_upper in ("CONFIRMING", "SETUP"):
        if quick_intent == "confirm":
            return {
                "intent": "confirm",
                "city": curr_city,
                "categories": curr_cats,
                "spoken_response": "Got it! Starting the collection now.",
                "confidence": 0.98,
                "raw_text": cleaned_text,
            }
        if quick_intent == "cancel":
            return {
                "intent": "cancel",
                "city": curr_city,
                "categories": curr_cats,
                "spoken_response": "Alright, cancelled.",
                "confidence": 0.98,
                "raw_text": cleaned_text,
            }

    # If Groq API key is set, run state-aware LLM parsing
    if settings.groq_api_key:
        try:
            parsed = _parse_with_groq(
                text=cleaned_text,
                valid_categories=valid_categories,
                category_meta=category_meta,
                known_cities=known_cities,
                language_code=language_code,
                current_state=state_upper,
                current_city=curr_city,
                current_categories=curr_cats,
            )
            if parsed and parsed.get("intent"):
                intent = parsed.get("intent", "search")
                extracted_city = (parsed.get("city") or "").strip()
                extracted_cats = [c for c in parsed.get("categories", []) if c in valid_categories]

                # Slot merging rules:
                if intent in ("confirm", "cancel", "status_update"):
                    final_city = curr_city or extracted_city
                    final_cats = curr_cats or extracted_cats
                elif intent == "edit":
                    final_city = extracted_city if extracted_city else curr_city
                    if extracted_cats:
                        merged = set(curr_cats) | set(extracted_cats)
                        final_cats = [c for c in valid_categories if c in merged]
                    else:
                        final_cats = curr_cats
                else:  # search
                    final_city = extracted_city if extracted_city else curr_city
                    final_cats = extracted_cats if extracted_cats else curr_cats

                return {
                    "intent": intent,
                    "city": final_city,
                    "categories": final_cats,
                    "spoken_response": parsed.get("spoken_response", "").strip(),
                    "confidence": float(parsed.get("confidence", 0.9)),
                    "raw_text": cleaned_text,
                }
        except Exception as exc:
            logger.warning("Groq voice intent parsing failed: %s, falling back to rule parser", exc)

    # Fallback to deterministic regex/keyword parser
    rule_res = _parse_with_rules(cleaned_text, valid_categories, category_meta, known_cities)

    extracted_city = rule_res["city"]
    extracted_cats = rule_res["categories"]

    if quick_intent in ("confirm", "cancel", "status_update"):
        final_city = curr_city or extracted_city
        final_cats = curr_cats or extracted_cats
    elif quick_intent == "edit":
        final_city = extracted_city if extracted_city else curr_city
        if extracted_cats:
            merged = set(curr_cats) | set(extracted_cats)
            final_cats = [c for c in valid_categories if c in merged]
        else:
            final_cats = curr_cats
    else:
        final_city = extracted_city if extracted_city else curr_city
        final_cats = extracted_cats if extracted_cats else curr_cats

    intent_out = quick_intent if quick_intent != "unknown" else "search"

    return {
        "intent": intent_out,
        "city": final_city,
        "categories": final_cats,
        "spoken_response": rule_res["spoken_response"],
        "confidence": rule_res["confidence"],
        "raw_text": cleaned_text,
    }


def _parse_with_groq(
    text: str,
    valid_categories: list[str],
    category_meta: dict[str, list[str]],
    known_cities: list[str],
    language_code: str,
    current_state: str,
    current_city: str,
    current_categories: list[str],
) -> dict:
    client = _groq()

    category_descriptions = "\n".join(
        f"- '{k}': {', '.join(terms)}" for k, terms in category_meta.items()
    )

    system_prompt = f"""You are a state-aware voice assistant for sales outreach automation.
Current State: {current_state}
Current Target City: "{current_city or 'None'}"
Current Categories: {current_categories or '[]'}

Allowed Category Keys (MUST be selected strictly from these):
{category_descriptions}

Known Pre-configured Cities:
{", ".join(known_cities)}

Instructions:
1. Determine the user's INTENT based on the current state and transcript:
   - 'confirm': User confirms pending action ("sounds good", "looks good", "go ahead", "yes", "start", "launch it", "theek hai", "haan kar do", "chalo shuru karo").
   - 'cancel': User cancels ("cancel", "stop", "no", "rehne do", "nahi", "band karo").
   - 'edit': User modifies city or categories ("make it Mumbai", "add yoga", "remove salons").
   - 'status_update': User asks for progress/update ("what's the update", "please tell me about the updates", "how many leads so far", "dashboard status").
   - 'search': User provides a new search command ("find dance studios in Pune").

2. CRITICAL SLOT PRESERVATION RULES:
   - For 'confirm', 'cancel', or 'status_update', DO NOT wipe existing city or categories. Return city="{current_city}", categories={current_categories}.
   - For 'edit', update ONLY the mentioned city or categories. Keep untouched slots as they are.
   - For 'search', extract city and categories. If no city/category is mentioned, leave existing slots untouched.

3. Return ONLY a JSON object:
   {{"intent": "<intent>", "city": "<city>", "categories": ["<key1>"], "spoken_response": "<speech>", "confidence": 0.95}}
No markdown formatting or extra text."""

    resp = client.chat.completions.create(
        model=PARSER_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Voice Command: {text!r}"},
        ],
        temperature=0.0,
        max_tokens=800,
    )

    content = resp.choices[0].message.content or ""
    match = re.search(r"\{.*\}", content, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON object found in LLM response: {content}")
    return json.loads(match.group(0))


def _parse_with_rules(
    text: str,
    valid_categories: list[str],
    category_meta: dict[str, list[str]],
    known_cities: list[str],
) -> dict:
    """Keyword & regex heuristic fallback parser."""
    lowered = text.lower()
    detected_cats = []

    for cat_key, terms in category_meta.items():
        for term in terms:
            if re.search(r"\b" + re.escape(term.lower()) + r"\b", lowered):
                if cat_key not in detected_cats:
                    detected_cats.append(cat_key)
                break

    # City detection
    detected_city = ""
    for city in known_cities:
        city_core = city.split(",")[0].strip().lower()
        if city_core in lowered or city.lower() in lowered:
            detected_city = city
            break

    if not detected_city:
        in_match = re.search(r"\b(?:in|at|for|around)\s+([A-Za-z\s]+)", text, re.IGNORECASE)
        if in_match:
            detected_city = in_match.group(1).strip()
        else:
            # Safe Hindi postposition match: avoid matching English verbs like "tell me", "give me", "show me"
            me_match = re.search(r"\b(?!please|tell|give|show|send|ask|help|let)\b([A-Za-z]{3,})\s+(?:mein|mai)\b", text, re.IGNORECASE)
            if me_match:
                candidate = me_match.group(1).strip()
                if candidate.lower() not in ("please", "tell", "give", "show", "send", "ask", "help", "let", "about"):
                    detected_city = candidate

    cat_names = [c.replace("_", " ").title() for c in detected_cats]
    cat_str = ", ".join(cat_names) if cat_names else "all configured categories"
    city_str = detected_city if detected_city else "your location"
    spoken_response = f"I found {cat_str} in {city_str}. Shall I start the collection?"

    return {
        "city": detected_city,
        "categories": detected_cats,
        "spoken_response": spoken_response,
        "confidence": 0.7 if (detected_city and detected_cats) else 0.4,
        "raw_text": text,
    }
