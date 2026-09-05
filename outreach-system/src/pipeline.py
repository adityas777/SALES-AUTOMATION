"""End-to-end orchestrator: collectors -> storage -> enrichment -> dedup ->
routing -> personalization -> senders, one city at a time (spec Phase 12).
Callable manually, from a cron, or via POST /run-collection?city=....
"""
from __future__ import annotations

import logging
from typing import Callable, Optional

from src.config_loader import get_locations
from src.collectors.places_api import collect_for_city
from src.enrichment.website_email_extractor import enrich_business
from src.dedup.fuzzy_dedup import compute_dedup_hash
from src.routing.category_router import resolve_category
from src.storage.airtable_client import get_client
from src.storage.schema import BusinessFields as BF
from src.outreach import send_outreach_to_business

logger = logging.getLogger(__name__)


def _city_config(city_name: str) -> dict:
    """Looks up lat/lng/radius for a pre-registered city (better search
    precision via locationBias). A city NOT in locations.yaml is still valid
    - the manual-run UI allows searching any free-text city - it just runs
    without a location bias, relying on the "... in <city>" phrase in the
    Places API query text itself."""
    for city_cfg in get_locations()["active_cities"]:
        if city_cfg["name"] == city_name:
            return city_cfg
    return {"name": city_name, "lat": None, "lng": None, "radius_km": None}


def run_pipeline(
    city_name: str,
    send_outreach: bool = True,
    categories_filter: Optional[list[str]] = None,
    progress_callback: Optional[Callable[[dict], None]] = None,
    should_stop: Optional[Callable[[], bool]] = None,
) -> dict:
    """`send_outreach=False` runs collection -> enrichment -> dedup -> Airtable
    push only, skipping the auto-send step - useful for a first look at real
    collected data (or a controlled re-send later) before any real message
    goes out to a real business.

    `categories_filter`: restrict collection to these category keys (None =
    all configured categories, the original/default behavior).

    `progress_callback`, if given, is called after every business is
    processed with a running snapshot dict (including that business's own
    detail) - used by the manual-run API to show live progress/feed without
    changing this function's core behavior.

    `should_stop`, if given, is checked by the collector between every
    business (not just between categories/cities) so a manual Stop takes
    effect promptly. Whatever was already pushed to Airtable before a stop
    stays - nothing is rolled back."""
    city_cfg = _city_config(city_name)
    client = get_client()

    collected = 0
    created = 0
    contacted = 0

    for raw_business in collect_for_city(
        city_cfg, categories_filter=categories_filter, should_stop=should_stop
    ):
        collected += 1

        enriched = enrich_business(raw_business)
        category = resolve_category(enriched)
        dedup_hash = compute_dedup_hash(
            name=enriched["name"], address=enriched["address"], phone=enriched["phone"]
        )

        fields = {
            BF.NAME: enriched["name"],
            BF.CATEGORY: category,
            BF.CITY: enriched["city"],
            BF.ADDRESS: enriched["address"],
            BF.PHONE: enriched["phone"],
            BF.WEBSITE: enriched["website"],
            BF.LISTING_URL: enriched["listing_url"],
        }
        if enriched.get("email"):
            fields[BF.EMAIL] = enriched["email"]
        fields[BF.DEDUP_HASH] = dedup_hash

        result = client.upsert_business(fields)
        if result.get("created"):
            created += 1
            email = fields.get(BF.EMAIL)
            if send_outreach and email and client.email_already_contacted(email, result["id"]):
                logger.info(
                    "Skipping outreach for %s - %s already contacted via another listing",
                    enriched["name"], email,
                )
            elif send_outreach:
                business_record = {"id": result["id"], "fields": result["fields"]}
                try:
                    send_result = send_outreach_to_business(business_record)
                    if send_result["sent_channels"]:
                        contacted += 1
                except Exception:
                    logger.exception("Initial outreach failed for %s", enriched["name"])

        if progress_callback:
            try:
                progress_callback({
                    "collected": collected, "new_businesses": created, "contacted": contacted,
                    "last_category": category, "last_business_name": enriched["name"],
                    "business": {
                        "name": enriched["name"],
                        "category": category,
                        "address": enriched["address"],
                        "phone": enriched["phone"],
                        "website": enriched["website"],
                    },
                })
            except Exception:
                logger.exception("progress_callback raised - ignoring, run continues")

    summary = {
        "city": city_name, "collected": collected, "new_businesses": created,
        "contacted": contacted, "outreach_sent": send_outreach,
    }
    logger.info("Pipeline run complete: %s", summary)
    return summary
