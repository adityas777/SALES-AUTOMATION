#Depoloyed - https://sales-automation-beta.vercel.app/
# Sales Automation — Local Business Outreach System

An automated pipeline that finds local businesses on Google Maps, enriches and dedupes them, sends
category-personalized outreach by email (WhatsApp built, pending Meta template approval), follows
up automatically on non-responders, and uses an LLM to read replies and decide when a human needs
to step in.

Full build spec: [`business-outreach-system-spec.md`](business-outreach-system-spec.md)

The actual implementation lives in [`outreach-system/`](outreach-system/) — see
[`outreach-system/README.md`](outreach-system/README.md) for setup, architecture, and how to run it.

## At a glance

- **Discovery**: Google Places API (New)
- **Database/CRM**: Airtable
- **AI**: Groq (personalization + 9-way reply classification)
- **Channels**: Gmail (SMTP/IMAP), Meta WhatsApp Cloud API
- **Alerts**: Slack
- **Backend**: Python / FastAPI
- **Dashboard**: React / Vite

## How to run in your system
#Backend
cd outreach-system
.venv\Scripts\activate                                                                                                                                   
uvicorn src.app:app --port 8000                                                                                                                          
                                        

#Frontend
cd outreach-system\frontend
npm run dev                                                                                                                                              

#To test slack                     
cd outreach-system
python scripts/demo_simulate_reply.py "Life Fitness 24x7" "Yes, interested! Please call me about pricing."      



python scripts/demo_simulate_reply.py "Gear Up Fitness Centre" "Not interested, please remove us"


Everything — categories, cities, message templates, media, follow-up cadence — lives in
`outreach-system/config/*.yaml`, editable without touching code.
