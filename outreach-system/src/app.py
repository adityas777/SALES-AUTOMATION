"""FastAPI entrypoint (spec Phase 12). Wires the WhatsApp webhook, exposes a
manual/cron collection trigger, and starts the background schedulers (daily
follow-up sweep + periodic email reply poll) on startup.

Run locally:  uvicorn src.app:app --reload --port 8000
Deploy: point Railway/Render's start command at
        uvicorn src.app:app --host 0.0.0.0 --port $PORT
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from src.settings import settings
from src.replies.whatsapp_webhook import router as whatsapp_router
from src.replies.email_poller import poll_inbox_for_replies
from src.followup.scheduler import run_followup_sweep, start_scheduler
from src.pipeline import run_pipeline
from src.web_api import router as web_api_router

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = start_scheduler()
    yield
    scheduler.shutdown()


app = FastAPI(title="Local Business Outreach System", lifespan=lifespan)

# Ops dashboard (frontend/) runs on Vite's dev server during development -
# different origin/port, so it needs CORS to call this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(whatsapp_router)
app.include_router(web_api_router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/run-collection")
def run_collection(city: str, send_outreach: bool = True):
    try:
        return run_pipeline(city, send_outreach=send_outreach)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/run-followup-sweep")
def trigger_followup_sweep():
    sent = run_followup_sweep()
    return {"contacted": sent}


@app.post("/run-email-poll")
def trigger_email_poll():
    processed = poll_inbox_for_replies()
    return {"processed": processed}
