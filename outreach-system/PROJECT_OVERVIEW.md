# 🎙️ Sales Automation — Local Business Outreach System
### Powered by Gnani.ai Voice Intelligence

> **Dedicated to [Gnani.ai](https://gnani.ai)** — the voice technology backbone of this system.
> Gnani's **Vachana STT/TTS APIs** power the entire voice-command interface,
> enabling operators to run, monitor, and control outreach campaigns entirely by speaking.

---

## 📌 What This Project Does

An end-to-end **automated B2B sales outreach pipeline** that:

1. **Discovers** local businesses (gyms, dance studios, salons, restaurants, etc.) using Google Maps
2. **Enriches** each lead with website & email data
3. **Deduplicates** to never contact the same business twice
4. **Sends personalized outreach** via Gmail (+ WhatsApp when approved)
5. **Follows up automatically** on non-responders at timed intervals
6. **Classifies replies** using AI — interested, not interested, opt-out, needs human, etc.
7. **Hands off** to a human agent via Slack when a business needs personal attention
8. **Lets operators control all of this by voice** — powered by Gnani.ai

---

## 🧱 Full Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   OPERATOR / USER                        │
│         Speaks into mic on the web dashboard             │
└──────────────────────┬──────────────────────────────────┘
                       │ Audio (WAV/WebM)
                       ▼
┌─────────────────────────────────────────────────────────┐
│              GNANI.AI VOICE LAYER                        │
│  STT: Vachana API v3  →  Transcription (en-IN / hi-IN)  │
│  TTS: Vachana TTS     →  Spoken confirmations (Nalini)   │
│  Fallback: Groq Whisper (if Gnani unavailable)           │
└──────────────────────┬──────────────────────────────────┘
                       │ Text transcript
                       ▼
┌─────────────────────────────────────────────────────────┐
│            INTENT PARSER (Groq LLM)                      │
│  Model: openai/gpt-oss-120b via Groq API                 │
│  Intents: search | confirm | cancel | edit | status      │
│  Supports English + Hindi + Hinglish                     │
│  State-aware: IDLE → CONFIRMING → RUNNING                │
└──────────────────────┬──────────────────────────────────┘
                       │ Structured command
                       ▼
┌─────────────────────────────────────────────────────────┐
│              PIPELINE ORCHESTRATOR                       │
│  src/pipeline.py — one city at a time                    │
│                                                          │
│  [1] Google Places API  →  collect businesses            │
│  [2] Enrichment         →  scrape website + email        │
│  [3] Fuzzy Dedup        →  hash-based deduplication      │
│  [4] Category Router    →  assign template/channel       │
│  [5] Groq Personalizer  →  AI-written first message      │
│  [6] Email Sender       →  Gmail SMTP (500/day free)     │
│  [6] WhatsApp Sender    →  Meta Cloud API (pending)      │
│  [7] Airtable CRM       →  store & track every record    │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│              REPLY HANDLING                              │
│  Email Poller (IMAP) + WhatsApp Webhook                  │
│  Groq Classifier → 9-way intent classification           │
│  Auto follow-up scheduler (configurable cadence)         │
│  Human Handoff Queue → Slack alert + Airtable log        │
└─────────────────────────────────────────────────────────┘
```

---

## 🎙️ Gnani.ai — The Voice Brain

This project is **dedicated to Gnani.ai** and their Vachana platform.
Gnani's APIs are used as the **primary voice interface** for the entire ops dashboard.

### What Gnani Powers

| Feature | Gnani API Used | Details |
|---------|----------------|---------|
| **Voice commands** | Vachana STT v3 | Operator speaks city + category in English or Hindi |
| **Spoken confirmations** | Vachana TTS | System replies back in Nalini voice (Indian English) |
| **Smart summaries** | TTS (curated by Groq) | "3 businesses contacted today, reply rate 12%" — spoken aloud |
| **Language support** | STT multi-lang | en-IN (English India) + hi-IN (Hindi / Hinglish) |
| **Whisper fallback** | Groq Whisper v3 | Auto-fallback if Gnani STT is temporarily unavailable |

### Gnani STT Flow
```
Operator mic → WAV audio → POST /api/voice/process-audio
    → Gnani Vachana STT v3 API
    → Transcript ("find dance studios in Bhilai")
    → Groq intent parser
    → {intent: "search", city: "Bhilai", categories: ["dance_studios"]}
    → Spoken TTS reply via Gnani: "Got it! Shall I start?"
```

### Gnani TTS Config
- **Default voice**: Nalini (Indian English)
- **Sample rate**: 24,000 Hz mono WAV
- **Model**: `timbre-v2.5`

---

## 🔌 Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Voice STT** | Gnani.ai Vachana v3 | Speech-to-text (primary) |
| **Voice TTS** | Gnani.ai Vachana TTS | Text-to-speech confirmations |
| **STT Fallback** | Groq Whisper-large-v3 | If Gnani unavailable |
| **AI / NLP** | Groq (openai/gpt-oss-120b) | Intent parsing + personalization + reply classification |
| **Business Discovery** | Google Places API (New) | Find local businesses by category + city |
| **CRM / Database** | Airtable (free plan) | Store, track, and manage all leads |
| **Email** | Gmail SMTP + App Password | Outreach sending (500/day free) |
| **WhatsApp** | Meta WhatsApp Cloud API | WhatsApp outreach (pending template approval) |
| **Human Alerts** | Slack Incoming Webhooks | Ping on human-needed cases |
| **Backend** | FastAPI + Python | REST API, pipeline orchestration |
| **Frontend** | React + Vite | Ops dashboard UI |

---

## 🖥️ The Dashboard (Frontend)

Live at: **http://localhost:5173**

### Screens

#### 1. Overview Dashboard
- Real-time stats: businesses contacted today, reply rate, interested count
- Funnel visualization: Queued → Contacted → Follow-up → Responded
- Handoff queue: list of businesses needing a human
- Active run cards (even if started from a different browser tab)

#### 2. Run Collection Screen
- City input (free text — any city in India)
- Category selector (multi-select from configured list)
- Live feed: businesses found in real-time as the pipeline runs
- Stop button to halt mid-run without losing progress

#### 3. Voice Assistant Modal (Gnani-powered)
- Floating mic button on every screen
- Press-and-hold to record, release to send
- Gnani STT transcribes speech → Groq parses intent
- System speaks back a confirmation via Gnani TTS
- Supports: English commands, Hindi, Hinglish
- State machine: IDLE → CONFIRMING (slot review) → RUNNING

---

## 📂 Project Structure

```
outreach-system/
├── src/
│   ├── app.py                          # FastAPI app entry point
│   ├── pipeline.py                     # End-to-end orchestrator
│   ├── web_api.py                      # All REST API endpoints
│   ├── outreach.py                     # Send first message logic
│   ├── collectors/places_api.py        # Google Maps business scraper
│   ├── storage/airtable_client.py      # Airtable CRUD operations
│   ├── storage/schema.py               # Field names + business statuses
│   ├── enrichment/website_email_extractor.py
│   ├── dedup/fuzzy_dedup.py            # Hash-based deduplication
│   ├── routing/category_router.py      # Map business → category key
│   ├── personalization/groq_personalizer.py
│   ├── senders/email_sender.py         # Gmail SMTP sender
│   ├── senders/whatsapp_sender.py      # Meta Cloud API sender
│   ├── followup/scheduler.py           # Timed follow-up sweeps
│   ├── replies/ai_classifier.py        # Groq 9-way reply classifier
│   ├── replies/email_poller.py         # IMAP inbox monitor
│   ├── replies/whatsapp_webhook.py     # Meta webhook receiver
│   ├── handoff/human_queue.py          # Queue + Slack alert
│   └── voice/
│       ├── gnani_client.py             # Gnani STT + TTS client
│       └── intent_parser.py            # Groq voice intent parser
├── frontend/src/
│   ├── screens/Overview.jsx            # Stats dashboard
│   ├── screens/RunCollection.jsx       # Manual run screen
│   └── components/VoiceAssistantModal.jsx  # Voice UI (Gnani)
├── config/
│   ├── categories.yaml                 # Business categories + search terms
│   ├── locations.yaml                  # Target cities + coords
│   ├── templates.yaml                  # Message template routing
│   ├── media_library.yaml              # Image assets per category
│   └── follow_up_policy.yaml           # Cadence, quiet hours, max follow-ups
├── templates/email/                    # HTML email templates
├── content_library/images/             # Media assets per category
└── scripts/
    ├── setup_airtable_schema.py        # One-time DB setup
    └── seed_sample_businesses.py       # Test data seeder
```

---

## 🔄 Complete Pipeline Flow

```
1. VOICE COMMAND (spoken or typed)
   "Find yoga studios and dance studios in Bhilai"

2. GNANI STT → Transcript
   "Find yoga studios and dance studios in Bhilai"

3. GROQ INTENT PARSE → Structured command
   { intent: "search", city: "Bhilai", categories: ["yoga_studios", "dance_studios"] }

4. GNANI TTS → Confirmation spoken back
   "Got it! Shall I start the collection?"

5. OPERATOR CONFIRMS → "Yes, go ahead" (or "haan kar do")

6. PIPELINE STARTS
   ├── Google Places API → fetch all matching businesses
   ├── Enrichment → website + email for each
   ├── Dedup → skip if already in Airtable
   ├── Airtable upsert → create/update CRM record
   └── Outreach → send personalized email (+ WhatsApp if approved)

7. FOLLOW-UP SCHEDULER (runs every few hours)
   └── Re-contacts non-responders per follow_up_policy.yaml

8. REPLY HANDLER (IMAP poll / WhatsApp webhook)
   └── Groq classifies reply → updates Airtable status
       ├── "interested" → flag for human follow-up
       ├── "opt_out" / "STOP" → permanently blacklist
       └── "needs_human" → Slack alert + HumanHandoffQueue

9. SMART VOICE SUMMARY (on demand)
   "47 businesses found. 12 contacted today. 3 interested. Reply rate 8%."
   → Spoken aloud via Gnani TTS
```

---

## 🌍 Supported Languages (Voice)

| Language Code | Language | Example Command |
|---------------|----------|-----------------|
| `en-IN` | English (India) | "Find dance studios in Raipur" |
| `hi-IN` | Hindi | "Bhilai mein yoga studios dhundho" |
| `hi-IN` | Hinglish | "Start karo, Durg mein gyms find karo" |

---

## 📊 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/run-collection` | Start a pipeline run |
| `POST` | `/api/run-collection/{id}/stop` | Stop an active run |
| `GET` | `/api/run-status/{id}` | Get run progress |
| `GET` | `/api/run-status/{id}/feed` | Get live business feed |
| `GET` | `/api/active-runs` | All currently running pipelines |
| `GET` | `/api/stats` | Dashboard stats |
| `GET` | `/api/handoff-queue` | Businesses needing human attention |
| `POST` | `/api/handoff-queue/{id}/resolve` | Mark handoff resolved |
| `GET` | `/api/voice/status` | Gnani configuration status |
| `POST` | `/api/voice/process-audio` | Full STT → Parse → TTS pipeline |
| `POST` | `/api/voice/parse-text` | Parse typed text as voice command |
| `POST` | `/api/voice/tts` | Synthesize speech (Gnani TTS) |
| `GET` | `/api/voice/smart-summary` | AI-spoken dashboard summary |

---

## ✅ Current API Status

| Service | Status |
|---------|--------|
| Airtable CRM | ✅ Live |
| Google Places API | ✅ Live |
| Groq AI | ✅ Live |
| Gmail SMTP | ✅ Live |
| Slack Webhook | ✅ Live |
| Gnani Voice STT/TTS | ✅ Configured |
| FastAPI Backend | ✅ Running (port 8000) |
| React Dashboard | ✅ Running (port 5173) |
| WhatsApp Cloud API | Pending Meta template approval |

---

## 🚀 Quick Start

```powershell
# Backend
cd outreach-system
.venv\Scripts\activate
uvicorn src.app:app --reload --port 8000

# Frontend (new terminal)
cd frontend
npm run dev

# Dashboard
# http://localhost:5173
```

---
---

# 🎬 VIDEO SCRIPT — Clip-by-Clip Summary
### (Give this section to Claude to curate a demo video)

> **Context for Claude:**
> This is a demo video for the Sales Automation Outreach System — a voice-controlled
> B2B lead generation and outreach platform powered by Gnani.ai's speech APIs.
> The video should feel like a sleek product demo reel. Narration tone: confident, clear, modern.
> Total target length: 3-4 minutes. Background music: subtle lo-fi tech ambient.

---

### CLIP 1 — INTRO / HOOK (0:00 – 0:20)
**Screen:** Black → title card fade in
**Narration:**
> "What if you could run an entire sales outreach campaign — find leads,
> send messages, follow up, and track replies — just by talking to your screen?"

**Visuals:**
- Title card: "Sales Automation — Voice-Controlled Outreach"
- Subtitle: "Powered by Gnani.ai"
- Subtle mic pulse animation in center

---

### CLIP 2 — DASHBOARD OVERVIEW (0:20 – 0:50)
**Screen:** Overview dashboard (http://localhost:5173)
**Narration:**
> "This is the operations dashboard. At a glance — businesses contacted today,
> reply rate, interested prospects, and your full sales pipeline from discovery to response."

**Visuals:**
- Slow pan across stats cards: "Contacted Today", "Reply Rate", "Interested"
- Scroll down to pipeline funnel (Queued → Contacted → Follow-up → Responded)
- Show the Handoff Queue section

---

### CLIP 3 — VOICE ACTIVATION (0:50 – 1:20)
**Screen:** Dashboard with floating mic button
**Narration:**
> "The entire system is voice-controlled — powered by Gnani.ai's Vachana speech platform.
> Press the mic, speak your command in English, Hindi, or Hinglish."

**Visuals:**
- Click the floating orange mic button (bottom right)
- Voice Assistant Modal slides up with waveform animation
- User speaks: "Find dance studios and yoga studios in Bhilai"
- Gnani STT transcript appears word-by-word in real-time

---

### CLIP 4 — INTENT PARSING + CONFIRMATION (1:20 – 1:50)
**Screen:** Voice modal showing parsed result card
**Narration:**
> "Gnani transcribes the command. Groq AI parses the intent — extracting the city,
> business categories, and action. Then Gnani speaks back a natural confirmation."

**Visuals:**
- Parsed result appears: City = "Bhilai", Categories = ["Dance Studios", "Yoga Studios"]
- Speaker icon pulses — audio plays: "Got it! Dance Studios and Yoga Studios in Bhilai. Shall I start?"
- User says "Yes, go ahead" — or shows Hindi: "haan kar do"
- Confirmation animation: green checkmark

---

### CLIP 5 — PIPELINE RUNNING (1:50 – 2:20)
**Screen:** Run Collection screen with live business feed
**Narration:**
> "The pipeline runs automatically. Google Places discovers matching businesses.
> Each one is enriched with contacts, deduplicated, personalized by AI,
> and an email is sent — all without lifting a finger."

**Visuals:**
- Business cards appear one by one in the live feed
- Show: business name, category, city, phone, website
- Counter ticks: "14 found · 9 new · 6 contacted"
- Progress bar fills

---

### CLIP 6 — AIRTABLE CRM (2:20 – 2:40)
**Screen:** Switch to Airtable browser tab
**Narration:**
> "Every business and interaction is stored in Airtable — your CRM.
> Status updates automatically as the campaign runs."

**Visuals:**
- Airtable Businesses table: Name, Category, City, Status columns
- Show status values changing: New → Contacted → Replied → Interested
- Brief glimpse of Interactions table with sent messages

---

### CLIP 7 — AI REPLY CLASSIFICATION (2:40 – 3:00)
**Screen:** Airtable status update + mock Slack notification
**Narration:**
> "When a business replies, Groq AI reads and classifies the message —
> interested, opt-out, or needs a human. Slack gets pinged for hot leads."

**Visuals:**
- Show a mock reply: "Hi, we're interested in this service!"
- Status auto-updates in Airtable: "Interested"
- Slack notification pops: "Business needs human: [Name] — replied with interest"

---

### CLIP 8 — SMART VOICE SUMMARY (3:00 – 3:20)
**Screen:** Dashboard, mic activated
**Narration:**
> "Ask for an update any time — and the system tells you out loud,
> exactly what's happening across all your campaigns."

**Visuals:**
- Press mic, say: "What's the update?"
- Gnani TTS speaks: "47 businesses found. 12 contacted today. 3 are interested. Reply rate is 8%."
- Speaker waveform plays during audio

---

### CLIP 9 — OUTRO (3:20 – 3:45)
**Screen:** Slow zoom-out from dashboard → logo wall
**Narration:**
> "Sales automation, powered by voice. Find leads, send outreach, follow up,
> classify replies — all hands-free. Built on Gnani.ai Vachana."

**Visuals:**
- Dashboard zooms out
- Logo wall fades in: Gnani.ai · Google · Groq · Airtable · Meta
- Final card: "Built with Gnani.ai Vachana"
- Mic pulse animation fades out

---

## Clip Summary Table

| Clip | Title | Duration | Key Visual | Key Message |
|------|-------|----------|------------|-------------|
| 1 | Intro Hook | 0:20 | Title card | What if you could run outreach by talking? |
| 2 | Dashboard | 0:30 | Overview + stats | Ops dashboard at a glance |
| 3 | Voice Activation | 0:30 | Mic modal + Gnani STT | Speak: "Find dance studios in Bhilai" |
| 4 | Intent + TTS | 0:30 | Parsed result + audio | Gnani TTS confirms the command |
| 5 | Pipeline Live | 0:30 | Live feed populating | AI finds + contacts businesses automatically |
| 6 | Airtable CRM | 0:20 | Airtable tables | All data synced automatically |
| 7 | Reply AI | 0:20 | Status update + Slack | Groq classifies every reply |
| 8 | Voice Summary | 0:20 | Mic + spoken summary | "3 interested, 8% reply rate" |
| 9 | Outro | 0:25 | Logo wall | Built with Gnani.ai Vachana |

---

*Document generated: 2026-10-05*
*Project: Sales Automation — Local Business Outreach System*
*Voice Layer: Gnani.ai Vachana (STT v3 + TTS timbre-v2.5, voice: Nalini)*
