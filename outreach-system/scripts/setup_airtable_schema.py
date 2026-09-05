"""One-time setup: creates the 'Outreach System' Airtable base with all four
tables and fields from the spec (Phase 2), using Airtable's Metadata API.

Prerequisites (do this once, in Airtable, before running this script):
  1. Create a Personal Access Token at https://airtable.com/create/tokens
     Scopes needed: schema.bases:write, data.records:write, data.records:read
     Access: "All current and future bases" (or add it to a workspace) — this
     is a one-time bootstrapping token; runtime code uses the same token but
     only needs data.records:read/write once the schema exists.
  2. Find your workspace ID: open airtable.com, open any base or click
     "Create a base", the URL contains `wsp...` — or run
     `curl -H "Authorization: Bearer <token>" https://api.airtable.com/v0/meta/whoami`
     is NOT enough for workspace id; easiest is opening a base's URL bar,
     the workspace id starts with "wsp".

Usage:
    AIRTABLE_API_KEY=pat_xxx AIRTABLE_WORKSPACE_ID=wsp_xxx python scripts/setup_airtable_schema.py

On success it prints the new AIRTABLE_BASE_ID to paste into .env.
"""
from __future__ import annotations

import os
import sys
import json
from pathlib import Path

import httpx
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
load_dotenv()

from src.storage.schema import BusinessStatus, AIClassificationLabel
from src.config_loader import get_categories, get_locations

API_ROOT = "https://api.airtable.com/v0/meta"


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _select(name: str, choices: list[str]) -> dict:
    return {
        "name": name,
        "type": "singleSelect",
        "options": {"choices": [{"name": c} for c in choices]},
    }


def create_base(token: str, workspace_id: str) -> dict:
    category_keys = list(get_categories().keys())
    city_names = [c["name"] for c in get_locations()["active_cities"]]

    businesses_table = {
        "name": "Businesses",
        "fields": [
            {"name": "Name", "type": "singleLineText"},
            _select("Category", category_keys),
            _select("City", city_names),
            {"name": "Address", "type": "multilineText"},
            {"name": "Phone", "type": "phoneNumber"},
            {"name": "Website", "type": "url"},
            {"name": "Listing URL", "type": "url"},
            {"name": "Email (enriched)", "type": "email"},
            {"name": "Dedup Hash", "type": "singleLineText"},
            _select("Status", BusinessStatus.ALL),
            {"name": "Last Contacted", "type": "date", "options": {"dateFormat": {"name": "iso"}}},
            {"name": "Follow-up Count", "type": "number", "options": {"precision": 0}},
            {"name": "Assigned Template", "type": "singleLineText"},
            {"name": "Notes", "type": "multilineText"},
        ],
    }

    payload = {"name": "Outreach System", "workspaceId": workspace_id, "tables": [businesses_table]}
    resp = httpx.post(f"{API_ROOT}/bases", headers=_headers(token), json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()


def create_table(token: str, base_id: str, table: dict) -> dict:
    resp = httpx.post(f"{API_ROOT}/bases/{base_id}/tables", headers=_headers(token), json=table, timeout=30)
    resp.raise_for_status()
    return resp.json()


def main() -> None:
    token = os.environ.get("AIRTABLE_API_KEY")
    workspace_id = os.environ.get("AIRTABLE_WORKSPACE_ID")
    if not token or not workspace_id:
        print("Set AIRTABLE_API_KEY and AIRTABLE_WORKSPACE_ID env vars first.", file=sys.stderr)
        sys.exit(1)

    print("Creating base with Businesses table...")
    base = create_base(token, workspace_id)
    base_id = base["id"]
    businesses_table_id = base["tables"][0]["id"]
    print(f"Base created: {base_id}")

    print("Creating Interactions table...")
    create_table(token, base_id, {
        "name": "Interactions",
        "fields": [
            {"name": "Summary", "type": "singleLineText"},
            {"name": "Business", "type": "multipleRecordLinks", "options": {"linkedTableId": businesses_table_id}},
            _select("Channel", ["WhatsApp", "Email"]),
            _select("Direction", ["Outbound", "Inbound"]),
            {"name": "Message Body", "type": "multilineText"},
            {"name": "Template Used", "type": "singleLineText"},
            {"name": "Media Attached", "type": "multipleAttachments"},
            {"name": "Timestamp", "type": "dateTime", "options": {
                "dateFormat": {"name": "iso"}, "timeFormat": {"name": "24hour"}, "timeZone": "utc",
            }},
            _select("AI Classification", AIClassificationLabel.ALL),
        ],
    })

    print("Creating Templates table (optional Airtable mirror of config/templates.yaml)...")
    create_table(token, base_id, {
        "name": "Templates",
        "fields": [
            {"name": "Category", "type": "singleLineText"},
            _select("Channel", ["WhatsApp", "Email"]),
            {"name": "Template Name / Subject", "type": "singleLineText"},
            {"name": "Body", "type": "multilineText"},
        ],
    })

    print("Creating HumanHandoffQueue table...")
    create_table(token, base_id, {
        "name": "HumanHandoffQueue",
        "fields": [
            {"name": "Summary", "type": "singleLineText"},
            {"name": "Business", "type": "multipleRecordLinks", "options": {"linkedTableId": businesses_table_id}},
            {"name": "Reason", "type": "multilineText"},
            _select("Priority", ["Low", "Normal", "High"]),
            {"name": "Assigned To", "type": "singleLineText"},
            {"name": "Resolved", "type": "checkbox", "options": {"icon": "check", "color": "greenBright"}},
        ],
    })

    print("\nDone. Add this to your .env:")
    print(f"AIRTABLE_BASE_ID={base_id}")


if __name__ == "__main__":
    main()
