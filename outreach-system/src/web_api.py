"""Thin read/action API layer for the ops dashboard frontend. Wraps the
existing backend (Airtable + pipeline) - does not change send/follow-up/reply
behavior. The only side-effecting endpoint is POST /api/run-collection, which
just calls the existing run_pipeline() in a background thread.
"""
from __future__ import annotations

import logging
import threading
import time
import unicodedata
import uuid
from datetime import date, datetime, timezone
import base64
import json
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel

from src.config_loader import get_categories, get_locations
from src.pipeline import run_pipeline
from src.settings import settings
from src.storage.airtable_client import get_client
from src.storage.schema import BusinessFields as BF, BusinessStatus, InteractionFields as IF, HandoffFields as HF
from src.voice.gnani_client import is_gnani_configured, synthesize_speech, transcribe_audio
from src.voice.intent_parser import PARSER_MODEL, _groq, parse_voice_command

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

# In-memory run tracking - fine for a single-process ops tool. Deliberately
# server-side and detached from any HTTP connection: api_run_collection just
# starts a daemon thread and returns immediately, so a run keeps executing
# regardless of whether any browser tab is polling it, which screen is open,
# or whether the tab is even still open. Only run_pipeline's own should_stop
# check (wired to stop_requested below) or it naturally finishing can end it.
_runs: dict[str, dict] = {}

# ---------------------------------------------------------------------------
# Stats TTL cache
# Airtable can take 4–7 s per call. smart-summary used to call api_stats twice
# (once in ThreadPoolExecutor, once to build base_parts). Cache the result for
# 60 s so the whole endpoint completes in one Airtable round-trip.
# ---------------------------------------------------------------------------
_stats_cache: dict = {}
_stats_cache_ts: float = 0.0
_STATS_TTL_S: float = 60.0


def _get_cached_stats() -> dict:
    """Returns Airtable stats, refreshing at most once every _STATS_TTL_S seconds."""
    global _stats_cache, _stats_cache_ts
    if time.monotonic() - _stats_cache_ts < _STATS_TTL_S and _stats_cache:
        return _stats_cache
    try:
        fresh = api_stats()
        _stats_cache = fresh
        _stats_cache_ts = time.monotonic()
        return fresh
    except Exception:
        return _stats_cache  # return stale on error rather than empty


class RunCollectionRequest(BaseModel):
    city: str
    categories: list[str] = []


def _new_run_state(city: str, categories: list[str]) -> dict:
    return {
        "status": "running",  # running | stopped | completed | failed
        "city": city,
        "categories": categories,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "businesses_found": 0,
        "new_businesses": 0,
        "contacted": 0,
        "errors": [],
        "status_message": f"Starting collection for {city}...",
        "stop_requested": False,
        "feed": [],  # oldest-first internally; reversed when served
    }


def _execute_run(run_id: str, city: str, categories_filter: Optional[list[str]]) -> None:
    state = _runs[run_id]

    def should_stop() -> bool:
        return _runs[run_id]["stop_requested"]

    def on_progress(snapshot: dict) -> None:
        state["businesses_found"] = snapshot["collected"]
        state["new_businesses"] = snapshot["new_businesses"]
        state["contacted"] = snapshot["contacted"]
        state["status_message"] = (
            f"Searching {snapshot['last_category']} in {city}... "
            f"found {snapshot['collected']} so far"
        )
        state["feed"].append({**snapshot["business"], "added_at": datetime.now(timezone.utc).isoformat()})

    try:
        summary = run_pipeline(
            city, send_outreach=True, categories_filter=categories_filter,
            progress_callback=on_progress, should_stop=should_stop,
        )
        state["businesses_found"] = summary["collected"]
        state["new_businesses"] = summary["new_businesses"]
        state["contacted"] = summary["contacted"]
        if state["stop_requested"]:
            state["status"] = "stopped"
            state["status_message"] = (
                f"Stopped - {summary['collected']} found, {summary['new_businesses']} new, "
                f"{summary['contacted']} contacted."
            )
        else:
            state["status"] = "completed"
            state["status_message"] = (
                f"Completed - {summary['collected']} found, {summary['new_businesses']} new, "
                f"{summary['contacted']} contacted."
            )
    except Exception as exc:
        logger.exception("Manual run %s failed", run_id)
        state["status"] = "failed"
        state["errors"].append(str(exc))
        state["status_message"] = f"Failed: {exc}"


@router.get("/categories")
def api_categories() -> list[str]:
    return list(get_categories().keys())


@router.get("/locations")
def api_locations() -> list[str]:
    """Pre-registered cities only - shown as suggestions/history in the UI.
    The free-text city input is NOT restricted to this list; any city can be
    searched, this just powers autocomplete-style convenience."""
    return [c["name"] for c in get_locations()["active_cities"]]


@router.post("/run-collection")
def api_run_collection(req: RunCollectionRequest) -> dict:
    city = req.city.strip()
    if not city:
        raise HTTPException(status_code=400, detail="city is required")

    run_id = str(uuid.uuid4())
    _runs[run_id] = _new_run_state(city, req.categories)
    thread = threading.Thread(
        target=_execute_run, args=(run_id, city, req.categories or None), daemon=True,
    )
    thread.start()
    return {"run_id": run_id}


@router.post("/run-collection/{run_id}/stop")
def api_stop_run(run_id: str) -> dict:
    state = _runs.get(run_id)
    if not state:
        raise HTTPException(status_code=404, detail="Unknown run_id")
    if state["status"] != "running":
        return {"stopped": False, "status": state["status"]}
    state["stop_requested"] = True
    return {"stopped": True}


@router.get("/run-status/{run_id}")
def api_run_status(run_id: str) -> dict:
    state = _runs.get(run_id)
    if not state:
        raise HTTPException(status_code=404, detail="Unknown run_id")
    return {k: v for k, v in state.items() if k != "feed"}


@router.get("/run-status/{run_id}/feed")
def api_run_feed(run_id: str) -> list[dict]:
    state = _runs.get(run_id)
    if not state:
        raise HTTPException(status_code=404, detail="Unknown run_id")
    return list(reversed(state["feed"]))


@router.get("/active-runs")
def api_active_runs() -> list[dict]:
    """Lets the UI recover run state on load, regardless of which screen the
    user lands on first (or whether they started the run from a different
    browser tab/session entirely - the run lives on the server, not in any
    one tab)."""
    return [
        {
            "run_id": run_id, "city": s["city"], "categories": s["categories"],
            "started_at": s["started_at"], "businesses_found": s["businesses_found"],
        }
        for run_id, s in _runs.items()
        if s["status"] == "running"
    ]


_RESPONDED_STATUSES = {
    BusinessStatus.RESPONDED, BusinessStatus.INTERESTED, BusinessStatus.NOT_INTERESTED,
    BusinessStatus.OPT_OUT, BusinessStatus.WRONG_NUMBER, BusinessStatus.NEEDS_HUMAN,
}
_FOLLOW_UP_STATUSES = {BusinessStatus.FOLLOW_UP_1, BusinessStatus.FOLLOW_UP_2, BusinessStatus.FOLLOW_UP_3}


@router.get("/stats")
def api_stats() -> dict:
    client = get_client()
    businesses = client.list_businesses()
    today = date.today().isoformat()

    statuses = [b["fields"].get(BF.STATUS, BusinessStatus.NEW) for b in businesses]
    contacted_today = sum(1 for b in businesses if b["fields"].get(BF.LAST_CONTACTED) == today)
    total_ever_contacted = sum(1 for s in statuses if s != BusinessStatus.NEW)
    total_responded = sum(1 for s in statuses if s in _RESPONDED_STATUSES)
    reply_rate = round(total_responded / total_ever_contacted, 3) if total_ever_contacted else 0.0

    funnel = {
        "queued": sum(1 for s in statuses if s == BusinessStatus.NEW),
        "contacted": sum(1 for s in statuses if s == BusinessStatus.CONTACTED),
        "follow_up": sum(1 for s in statuses if s in _FOLLOW_UP_STATUSES),
        "responded": total_responded,
    }

    return {
        "contacted_today": contacted_today,
        "reply_rate": reply_rate,
        "interested_count": sum(1 for s in statuses if s == BusinessStatus.INTERESTED),
        "needs_human_count": sum(1 for s in statuses if s == BusinessStatus.NEEDS_HUMAN),
        "funnel": funnel,
    }


@router.get("/handoff-queue")
def api_handoff_queue() -> list[dict]:
    client = get_client()
    rows = client.list_unresolved_handoff()

    queue = []
    for row in rows:
        linked = row["fields"].get(HF.BUSINESS, [])
        if not linked:
            continue
        business_id = linked[0]
        business = client.get_business(business_id)
        bf = business["fields"]

        latest = client.latest_interaction_for_business(business_id)
        last_message = latest["fields"].get(IF.MESSAGE_BODY, "") if latest else ""
        timestamp = latest["fields"].get(IF.TIMESTAMP, "") if latest else ""

        queue.append({
            "business_id": business_id,
            "name": bf.get(BF.NAME, ""),
            "category": bf.get(BF.CATEGORY, ""),
            "city": bf.get(BF.CITY, ""),
            "reason": row["fields"].get(HF.REASON, ""),
            "last_message": last_message,
            "timestamp": timestamp,
        })

    queue.sort(key=lambda r: r["timestamp"], reverse=True)
    return queue


@router.post("/handoff-queue/{business_id}/resolve")
def api_resolve_handoff(business_id: str) -> dict:
    client = get_client()
    updated = client.resolve_handoff_for_business(business_id)
    if updated == 0:
        raise HTTPException(status_code=404, detail="No unresolved handoff entry found for this business")
    return {"resolved": True}


# --- Voice Agent Endpoints (Gnani STT/TTS + Groq Intent Parsing) ---


class ParseTextRequest(BaseModel):
    text: str
    language_code: str = "en-IN"
    current_state: str = "IDLE"
    current_city: str = ""
    current_categories: list[str] = []


class TtsRequest(BaseModel):
    text: str
    language_code: str = "en-IN"


@router.get("/voice/status")
def api_voice_status() -> dict:
    return {
        "gnani_configured": is_gnani_configured(),
        "languages": [
            {"code": "en-IN", "label": "English (India)"},
            {"code": "hi-IN", "label": "Hindi / Hinglish"},
        ],
    }


@router.post("/voice/process-audio")
async def api_voice_process_audio(
    audio_file: UploadFile = File(...),
    language_code: str = Form("en-IN"),
    current_state: str = Form("IDLE"),
    current_city: str = Form(""),
    current_categories: str = Form("[]"),
) -> dict:
    """End-to-end voice processor:
    1. Transcribes audio via Gnani STT API (or Whisper fallback).
    2. Context & State-aware intent parsing + conservative slot merging via Groq.
    3. Synthesizes confirmation speech via Gnani TTS.
    """
    import asyncio
    import json

    audio_bytes = await audio_file.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio payload")

    filename = audio_file.filename or "recording.wav"
    content_type = audio_file.content_type or "audio/wav"

    cats_list = []
    if current_categories:
        try:
            loaded = json.loads(current_categories)
            if isinstance(loaded, list):
                cats_list = loaded
            else:
                cats_list = [c.strip() for c in str(current_categories).split(",") if c.strip()]
        except Exception:
            cats_list = [c.strip() for c in str(current_categories).split(",") if c.strip()]

    # Diagnostic logging
    logger.info(
        "Voice audio received: filename=%s, content_type=%s, size=%d bytes, state=%s, city=%s, cats=%s",
        filename, content_type, len(audio_bytes), current_state, current_city, cats_list,
    )
    if len(audio_bytes) >= 44 and audio_bytes[:4] == b"RIFF":
        import struct
        sr = struct.unpack_from("<I", audio_bytes, 24)[0]
        ch = struct.unpack_from("<H", audio_bytes, 22)[0]
        bps = struct.unpack_from("<H", audio_bytes, 34)[0]
        data_sz = struct.unpack_from("<I", audio_bytes, 40)[0]
        dur = data_sz / (sr * ch * bps // 8) if (sr * ch * bps) else 0
        logger.info(
            "WAV header: sampleRate=%d, channels=%d, bitsPerSample=%d, dataSizeBytes=%d, duration=%.2fs",
            sr, ch, bps, data_sz, dur,
        )

    loop = asyncio.get_running_loop()

    try:
        transcript = await loop.run_in_executor(
            None, transcribe_audio, audio_bytes, filename, content_type, language_code
        )
    except Exception as exc:
        logger.exception("Voice transcription failed")
        raise HTTPException(status_code=502, detail=f"Voice transcription failed: {exc}")

    parsed = await loop.run_in_executor(
        None,
        lambda: parse_voice_command(
            transcript,
            language_code=language_code,
            current_state=current_state,
            current_city=current_city,
            current_categories=cats_list,
        ),
    )

    # Synthesize speech for the spoken confirmation response
    audio_data_uri = None
    spoken_text = parsed.get("spoken_response", "")
    if spoken_text and is_gnani_configured():
        try:
            tts_wav = await loop.run_in_executor(
                None, synthesize_speech, spoken_text, language_code
            )
            b64 = base64.b64encode(tts_wav).decode("ascii")
            audio_data_uri = f"data:audio/wav;base64,{b64}"
        except Exception:
            logger.warning("Gnani TTS synthesis failed, returning text only", exc_info=True)

    return {
        "success": True,
        "intent": parsed.get("intent", "search"),
        "transcript": transcript,
        "city": parsed.get("city", ""),
        "categories": parsed.get("categories", []),
        "spoken_response": spoken_text,
        "audio_data": audio_data_uri,
        "confidence": parsed.get("confidence", 0.9),
    }


@router.post("/voice/parse-text")
def api_voice_parse_text(req: ParseTextRequest) -> dict:
    """Parses text (e.g. from Web Speech API or typing) and generates TTS audio."""
    parsed = parse_voice_command(
        req.text,
        language_code=req.language_code,
        current_state=req.current_state,
        current_city=req.current_city,
        current_categories=req.current_categories,
    )

    audio_data_uri = None
    spoken_text = parsed.get("spoken_response", "")
    if spoken_text and is_gnani_configured():
        try:
            tts_wav = synthesize_speech(spoken_text, language_code=req.language_code)
            b64 = base64.b64encode(tts_wav).decode("ascii")
            audio_data_uri = f"data:audio/wav;base64,{b64}"
        except Exception:
            logger.warning("Gnani TTS synthesis failed, returning text only", exc_info=True)

    return {
        "success": True,
        "transcript": req.text,
        "city": parsed.get("city", ""),
        "categories": parsed.get("categories", []),
        "spoken_response": spoken_text,
        "audio_data": audio_data_uri,
        "confidence": parsed.get("confidence", 0.9),
    }


@router.post("/voice/tts")
def api_voice_tts(req: TtsRequest):
    """Synthesizes text to speech and returns WAV audio stream."""
    try:
        wav_bytes = synthesize_speech(req.text, language_code=req.language_code)
        return Response(content=wav_bytes, media_type="audio/wav")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"TTS synthesis failed: {exc}")


@router.get("/voice/smart-summary")
def api_voice_smart_summary() -> dict:
    """Returns a spoken-language summary of the current dashboard state.
    Used by the voice agent to answer 'what's the update?' questions.

    Design goals:
    - NEVER block indefinitely: Airtable is fetched via a 60 s TTL cache so
      the hot path is instant; on a cold cache it is time-boxed to 12 s.
    - Groq curates into natural speech; non-ASCII chars (smart quotes etc.)
      are NFKD-normalised instead of stripped so the spoken text is still
      human-readable even if normalization changes a char.
    - Falls back to the pre-built base_summary if Groq returns empty.
    """
    import concurrent.futures

    # Gather active/completed run snapshots from memory (instant)
    active = [
        {
            "run_id": rid, "city": s["city"], "categories": s["categories"],
            "businesses_found": s["businesses_found"], "new_businesses": s["new_businesses"],
            "contacted": s["contacted"], "status": s["status"],
            "status_message": s.get("status_message", ""),
        }
        for rid, s in _runs.items()
    ]
    running = [r for r in active if r["status"] == "running"]
    completed = [r for r in active if r["status"] == "completed"]

    # --- Airtable stats (TTL-cached; cold-path capped at 12 s) -------------
    # We use _get_cached_stats() which re-uses the last result if it is <60 s
    # old.  This avoids the previous bug where api_stats was called twice
    # inside this endpoint (once via ThreadPoolExecutor AND once to build
    # base_parts), costing up to 14 s of Airtable round-trips per request.
    stats: dict = {}
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            future = ex.submit(_get_cached_stats)
            # 12 s cap — observed worst-case Airtable cold call was 6.65 s,
            # so 12 s gives a comfortable buffer before we give up.
            stats = future.result(timeout=12)
    except concurrent.futures.TimeoutError:
        logger.warning("_get_cached_stats timed out (>12 s) in smart-summary — using empty stats")
    except Exception as exc:
        logger.warning("_get_cached_stats failed in smart-summary: %s", exc)

    # --- Build a data-rich plain-text base summary -------------------------
    # This is passed to Groq AND used as the fallback if Groq fails.
    base_parts = []
    if running:
        r = running[0]
        cats = ", ".join(c.replace("_", " ").title() for c in r["categories"]) or "all categories"
        base_parts.append(
            f"Collection is active for {cats} in {r['city']}. "
            f"{r['businesses_found']} businesses found, {r['new_businesses']} new, {r['contacted']} contacted."
        )
    elif completed:
        r = completed[-1]
        cats = ", ".join(c.replace("_", " ").title() for c in r["categories"]) or "all categories"
        base_parts.append(
            f"Last run for {cats} in {r['city']} completed. "
            f"{r['businesses_found']} found, {r['new_businesses']} new, {r['contacted']} contacted."
        )
    else:
        base_parts.append("No collection runs are currently active.")

    if stats:
        contacted_today = stats.get("contacted_today", 0)
        reply_rate = stats.get("reply_rate", 0)
        interested = stats.get("interested_count", 0)
        needs_human = stats.get("needs_human_count", 0)
        funnel = stats.get("funnel", {})
        if contacted_today:
            base_parts.append(f"{contacted_today} businesses contacted today.")
        if reply_rate:
            base_parts.append(f"Reply rate is {round(reply_rate * 100)}%.")
        if interested:
            base_parts.append(f"{interested} prospects are interested.")
        if needs_human:
            base_parts.append(f"{needs_human} need human follow-up.")
        if funnel:
            base_parts.append(
                f"Pipeline: {funnel.get('queued', 0)} queued, "
                f"{funnel.get('contacted', 0)} contacted, "
                f"{funnel.get('follow_up', 0)} in follow-up, "
                f"{funnel.get('responded', 0)} responded."
            )

    base_summary = " ".join(base_parts)
    logger.info("smart-summary base_summary: %s", base_summary)

    summary_text = ""

    # --- Groq: curate into natural spoken language -------------------------
    if settings.groq_api_key:
        try:
            groq_client = _groq()
            system_prompt = (
                "You are a concise, energetic voice assistant for a sales outreach automation console. "
                "Rephrase the provided dashboard update into a natural, spoken 2-3 sentence summary. "
                "Keep it under 45 words, use natural speech, keep all numbers, "
                "and return ONLY plain text — no markdown, no bullet points, no quotes, no extra commentary."
            )
            resp = groq_client.chat.completions.create(
                model=PARSER_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Dashboard update: {base_summary}"},
                ],
                temperature=0.4,
                max_tokens=120,
            )
            raw = (resp.choices[0].message.content or "").strip()
            logger.info("Groq raw response (repr): %r", raw[:300])

            # Replace common typographic Unicode chars with plain ASCII equivalents
            # BEFORE NFKD normalization, since NFKD alone doesn't map \u2018/\u2019 -> '
            _TYPO_MAP = str.maketrans({
                "\u2018": "'",   # LEFT SINGLE QUOTATION MARK
                "\u2019": "'",   # RIGHT SINGLE QUOTATION MARK (e.g. Groq's "haven't")
                "\u201c": '"',  # LEFT DOUBLE QUOTATION MARK
                "\u201d": '"',  # RIGHT DOUBLE QUOTATION MARK
                "\u2013": "-",  # EN DASH
                "\u2014": "-",  # EM DASH
                "\u2026": "...",  # HORIZONTAL ELLIPSIS
            })
            replaced = raw.translate(_TYPO_MAP)
            normalized = unicodedata.normalize("NFKD", replaced)
            cleaned = normalized.encode("ascii", "ignore").decode("ascii").strip()

            if cleaned:
                summary_text = cleaned
                logger.info("Groq summary (cleaned): %s", summary_text)
            else:
                logger.warning(
                    "Groq summary empty after NFKD+ASCII clean — falling back to base_summary. "
                    "Raw was: %r", raw[:200]
                )
        except Exception as exc:
            logger.warning("Groq summary curation failed: %s — using base_summary", exc)

    # Fallback: use the pre-built data-accurate base_summary
    if not summary_text:
        summary_text = base_summary

    # --- Optional Gnani TTS audio ------------------------------------------
    audio_data_uri = None
    if is_gnani_configured() and summary_text:
        try:
            tts_wav = synthesize_speech(summary_text, language_code="en-IN")
            b64 = base64.b64encode(tts_wav).decode("ascii")
            audio_data_uri = f"data:audio/wav;base64,{b64}"
        except Exception:
            logger.warning("Gnani TTS for smart-summary failed — browser TTS will be used", exc_info=True)

    return {
        "summary": summary_text,
        "audio_data": audio_data_uri,
        "has_active_run": len(running) > 0,
        "stats": stats,
    }

