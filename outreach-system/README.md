# Local Business Outreach System

Automated pipeline: Google Maps collection → Airtable CRM → enrichment →
dedup → category-based template/media selection → personalized WhatsApp +
email outreach → follow-ups → AI-classified reply handling → human handoff.
Built per `../business-outreach-system-spec.md`. Every category, city,
template, media asset, and follow-up cadence lives in `config/*.yaml` — no
code change needed to adjust any of them.

## What's built so far

All 12 phases from the spec are scaffolded and import cleanly:

| Phase | Module | Status |
|---|---|---|
| 0 | `config/*.yaml`, `.env.example` | Done — sample cities/categories filled in |
| 1 | `src/collectors/places_api.py` | Done — needs `GOOGLE_MAPS_API_KEY` to run for real |
| 2 | `src/storage/schema.py`, `airtable_client.py`, `scripts/setup_airtable_schema.py` | Done — needs Airtable account |
| 3 | `src/enrichment/website_email_extractor.py` | Done |
| 4 | `src/dedup/fuzzy_dedup.py` | Done |
| 5 | `src/routing/category_router.py`, `template_selector.py` | Done |
| 6 | `src/personalization/groq_personalizer.py` | Done — needs `GROQ_API_KEY` |
| 7 | `src/senders/whatsapp_sender.py`, `email_sender.py` | Done — email works with just an App Password; WhatsApp needs Meta template approval first |
| 8 | `src/followup/scheduler.py` | Done |
| 9 | `src/replies/whatsapp_webhook.py`, `email_poller.py` | Done — webhook needs a public HTTPS URL (deploy first) |
| 10 | `src/replies/ai_classifier.py` | Done — needs `GROQ_API_KEY` |
| 11 | `src/handoff/human_queue.py` | Done — Slack webhook optional |
| 12 | `src/app.py`, `src/pipeline.py` | Done |

All Python modules were compiled and import-tested; the pure-logic pieces
(dedup hashing/fuzzy match, category routing, template selection, WhatsApp
variable ordering, and the opt-out keyword short-circuit in the reply
classifier) were smoke-tested directly. What has **not** been tested yet is
anything that needs a live external account: real Airtable base, real Places
API calls, real Groq calls, real WhatsApp/email sending. Follow the setup
steps below in order — each one unblocks the next phase.

## Setup, in the order you'll need each thing

### 1. Python environment
```bash
cd outreach-system
python -m venv .venv
.venv\Scripts\activate        # PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

### 2. Groq (you said you already have this)
Put your key in `.env` as `GROQ_API_KEY`. Free tier is generous for this
volume (personalization + reply classification). Nothing else to configure.

### 3. Airtable (free plan — up to 1,000 records/base)
1. Sign up at airtable.com (free).
2. Create a Personal Access Token: airtable.com/create/tokens → scopes
   `schema.bases:write`, `data.records:read`, `data.records:write` → access
   to your workspace.
3. Find your workspace ID (starts with `wsp...`) — visible in the URL when
   you open/create a base in that workspace.
4. Put the token in `.env` as `AIRTABLE_API_KEY`, and the workspace ID as
   `AIRTABLE_WORKSPACE_ID` (only needed for the one-time setup script below).
5. Run:
   ```bash
   python scripts/setup_airtable_schema.py
   ```
   This creates the `Outreach System` base with all 4 tables (Businesses,
   Interactions, Templates, HumanHandoffQueue) and every field from the spec.
   It prints an `AIRTABLE_BASE_ID` — paste that into `.env`.
6. Smoke-test the client:
   ```bash
   python scripts/seed_sample_businesses.py
   ```
   Open the base in Airtable and confirm 5 rows landed correctly.

### 4. Google Places API (New) — for real business collection
1. console.cloud.google.com → create/select a project.
2. Enable "Places API (New)".
3. Create an API key, restrict it to Places API (New).
4. New Google Cloud accounts get **$200/month recurring free credit** —
   a Text Search + Details pair per business costs fractions of a cent, so a
   few thousand businesses/month stays free.
5. Put the key in `.env` as `GOOGLE_MAPS_API_KEY`.
6. Adjust `config/locations.yaml` (cities) and `config/categories.yaml`
   (search terms) if you want different ones than the samples.
7. Test collection for one city:
   ```bash
   python -m src.collectors.places_api
   ```
   Output lands in `staging/<city>_<date>.jsonl` for review before it ever
   touches Airtable.

### 5. Email sending (no approval needed — do this before WhatsApp)
1. Use a Gmail account (a fresh one is fine), turn on 2-Step Verification.
2. Google Account → Security → App passwords → generate one.
3. Put the Gmail address as `SMTP_USER`, the app password as `SMTP_PASS`.
4. Also enable IMAP (Gmail → Settings → Forwarding and POP/IMAP) — the same
   credentials are reused by `src/replies/email_poller.py` to detect replies.
5. Free tier limit: ~500 sends/day per account.

Drop a real image per category under `content_library/images/<category>/`
matching the filename in `config/media_library.yaml` (currently `intro.jpg`)
— until a real file exists there, emails send without the inline image.

### 6. Meta WhatsApp Cloud API (parallel track — approval takes days)
1. business.facebook.com → create a Business Account, add WhatsApp.
2. Business Manager → WhatsApp → API Setup gives a free test number and a
   temporary access token immediately (get a permanent token + System User
   for production).
3. Put `WHATSAPP_TOKEN` and `WHATSAPP_PHONE_NUMBER_ID` in `.env`.
4. Submit one template per category you want on WhatsApp (Business Manager →
   Account tools → Message templates), name it exactly what
   `config/templates.yaml` expects (e.g. `dance_academy_intro_v1`), with
   `{{1}}` `{{2}}` `{{3}}` placeholders for business name / category / city
   in that order.
5. Only once a category's template is **approved**, flip
   `use_whatsapp: true` for it in `config/templates.yaml`.
6. Deploy the app (step 8 below) and register the webhook: Business Manager
   → WhatsApp → Configuration → Callback URL
   `https://<your-host>/webhooks/whatsapp`, verify token = whatever you put
   in `.env` as `WHATSAPP_VERIFY_TOKEN`, subscribe to the `messages` field.

Cold-outreach risk (per the spec's compliance notes): Meta can restrict a
number with high block/report rates. Start with small batches, prioritize
email for first-touch, reserve WhatsApp for businesses showing some opt-in
signal, honor "STOP" instantly (already automatic — see `ai_classifier.py`).

### 7. Slack handoff notification (optional)
Slack → create an app → Incoming Webhooks → Add New Webhook → paste the URL
into `.env` as `SLACK_WEBHOOK_URL`. Skip this and handoff still works, it
just won't ping Slack — the `HumanHandoffQueue` Airtable table is the source
of truth either way.

### 8. Deploy (Railway or Render free tier)
Needed for the WhatsApp webhook to be reachable, and to keep the follow-up
scheduler / email poller running continuously.
- Start command: `uvicorn src.app:app --host 0.0.0.0 --port $PORT`
- Set every `.env` variable as an environment variable in the platform's
  dashboard (don't commit `.env`).

## Running it

```bash
# One city, full pipeline: collect -> enrich -> dedup -> push -> first outreach
curl -X POST "http://localhost:8000/run-collection?city=Durg, Chhattisgarh"

# Manually trigger a follow-up sweep or email poll (they also run on a schedule)
curl -X POST http://localhost:8000/run-followup-sweep
curl -X POST http://localhost:8000/run-email-poll
```

## Changing behavior without touching code

- New city → add a block to `config/locations.yaml`.
- New category → add a block to `config/categories.yaml` +
  `config/templates.yaml` + `config/media_library.yaml`, and drop the
  media asset + email HTML under `content_library/` / `templates/email/`.
- New/changed follow-up cadence, quiet hours, max follow-ups →
  `config/follow_up_policy.yaml`.
- Swap a category's media asset → replace the file at the path already
  listed in `config/media_library.yaml`.

## Known gaps / next steps

- `scraper_fallback.py` (spec §3.2) isn't built — Places API is the
  compliant default and is what's wired up; only add the scraper if you
  deliberately want to accept its Terms-of-Service risk.
- Gmail API (OAuth) path is documented in `.env.example` but not
  implemented — SMTP + App Password is what's wired up (faster to bootstrap,
  same 500/day free limit). Add OAuth later only if you need Gmail's higher
  quota via delegated domain-wide access.
- No automated test suite yet beyond the manual smoke tests described above.
- `Templates` Airtable table is created by the schema script but
  `template_selector.py` only reads YAML — wire in an Airtable fallback read
  later if you want non-technical template editing.
