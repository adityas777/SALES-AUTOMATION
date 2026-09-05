"""Thin read/action API layer for the ops dashboard frontend. Wraps the
existing backend (Airtable + pipeline) - does not change send/follow-up/reply
behavior. The only side-effecting endpoint is POST /api/run-collection, which
just calls the existing run_pipeline() in a background thread.
"""
from __future__ import annotations

import logging
import threading
import uuid
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.config_loader import get_categories, get_locations
from src.pipeline import run_pipeline
from src.storage.airtable_client import get_client
from src.storage.schema import BusinessFields as BF, BusinessStatus, InteractionFields as IF, HandoffFields as HF

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

# In-memory run tracking - fine for a single-process ops tool. Deliberately
# server-side and detached from any HTTP connection: api_run_collection just
# starts a daemon thread and returns immediately, so a run keeps executing
# regardless of whether any browser tab is polling it, which screen is open,
# or whether the tab is even still open. Only run_pipeline's own should_stop
# check (wired to stop_requested below) or it naturally finishing can end it.
_runs: dict[str, dict] = {}


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
