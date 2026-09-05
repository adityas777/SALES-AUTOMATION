"""Google Places API (New) collector (spec Phase 1).

For every (city, category, search_term) combination: Text Search to find
candidate places, then Place Details for the fields we actually need.
Writes raw normalized results to a local JSONL staging file BEFORE touching
Airtable, so a downstream failure is cheaply replayable.

Setup needed (do this before running):
  1. Google Cloud Console -> create/select a project.
  2. Enable "Places API (New)" for that project.
  3. Create an API key, restrict it to Places API (New).
  4. Put it in .env as GOOGLE_MAPS_API_KEY.
  New Google Cloud accounts get $200/month recurring free credit, which
  comfortably covers a few thousand businesses/month of Text Search + Details.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator, Optional

import httpx

from src.settings import settings
from src.config_loader import get_categories, get_locations

logger = logging.getLogger(__name__)

TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
DETAILS_URL_TMPL = "https://places.googleapis.com/v1/places/{place_id}"

TEXT_SEARCH_FIELD_MASK = "places.id,places.displayName,nextPageToken"
DETAILS_FIELD_MASK = "displayName,formattedAddress,internationalPhoneNumber,websiteUri,googleMapsUri,types,rating"

STAGING_DIR = Path(__file__).resolve().parent.parent.parent / "staging"
STAGING_DIR.mkdir(exist_ok=True)

RATE_LIMIT_SLEEP_SECONDS = 0.2  # be polite; Places API (New) has its own QPS caps too


def _headers(field_mask: str) -> dict:
    return {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": settings.google_maps_api_key,
        "X-Goog-FieldMask": field_mask,
    }


def _text_search(client: httpx.Client, query: str, lat: Optional[float], lng: Optional[float],
                  radius_km: Optional[float], page_token: str | None = None) -> dict:
    # Google requires a paginated request to repeat the exact same parameters
    # as the initial call (400 INVALID_ARGUMENT otherwise) - locationBias must
    # stay present (or absent) consistently across every page, with pageToken
    # just added on top. lat/lng/radius_km are None for a free-text city that
    # isn't pre-registered in locations.yaml - Places API can still resolve
    # location from the "... in <city>" phrase in the query text itself,
    # just without the extra precision a bias circle gives.
    body = {"textQuery": query}
    if lat is not None and lng is not None and radius_km is not None:
        body["locationBias"] = {
            "circle": {"center": {"latitude": lat, "longitude": lng}, "radius": radius_km * 1000}
        }
    if page_token:
        body["pageToken"] = page_token
    resp = client.post(TEXT_SEARCH_URL, headers=_headers(TEXT_SEARCH_FIELD_MASK), json=body, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _place_details(client: httpx.Client, place_id: str) -> dict:
    url = DETAILS_URL_TMPL.format(place_id=place_id)
    resp = client.get(url, headers=_headers(DETAILS_FIELD_MASK), timeout=30)
    resp.raise_for_status()
    return resp.json()


def _normalize(details: dict, category: str, city: str, matched_search_term: str) -> dict:
    return {
        "name": details.get("displayName", {}).get("text", ""),
        "category": category,
        "matched_search_term": matched_search_term,
        "city": city,
        "address": details.get("formattedAddress", ""),
        "phone": details.get("internationalPhoneNumber", ""),
        "website": details.get("websiteUri", ""),
        "listing_url": details.get("googleMapsUri", ""),
        "google_types": details.get("types", []),
        "rating": details.get("rating"),
        "source": "google_places_api",
        "collected_at": datetime.now(timezone.utc).isoformat(),
    }


def collect_for_city(
    city_cfg: dict,
    categories_filter: list[str] | None = None,
    should_stop: Optional[Callable[[], bool]] = None,
) -> Iterator[dict]:
    """Yields normalized business dicts for every category/search_term
    combination configured for this city. Also appends everything to a JSONL
    staging file named after the city and today's date.

    `categories_filter`: restrict to these category keys only (used by the
    manual UI-triggered run). None (the default) searches every configured
    category, unchanged from before this parameter existed.

    `should_stop`: checked before every Text Search call and before every
    single place is processed (not just between categories), so a manual
    Stop takes effect within one business, not one whole category."""
    categories = get_categories()
    if categories_filter is not None:
        categories = {k: v for k, v in categories.items() if k in categories_filter}
    city_name = city_cfg["name"]
    lat, lng, radius_km = city_cfg.get("lat"), city_cfg.get("lng"), city_cfg.get("radius_km")
    stem = city_name.lower().replace(",", "").replace(" ", "_")
    staging_path = STAGING_DIR / f"{stem}_{datetime.now(timezone.utc):%Y%m%d}.jsonl"

    def stopped() -> bool:
        return bool(should_stop and should_stop())

    with httpx.Client() as client, open(staging_path, "a", encoding="utf-8") as staging_file:
        for category, cat_cfg in categories.items():
            if stopped():
                return
            for search_term in cat_cfg["search_terms"]:
                if stopped():
                    return
                query = f"{search_term} in {city_name}"
                page_token = None
                seen_place_ids: set[str] = set()

                while True:
                    if stopped():
                        return
                    result = _text_search(client, query, lat, lng, radius_km, page_token)
                    places = result.get("places", [])
                    for place in places:
                        if stopped():
                            return
                        place_id = place.get("id")
                        if not place_id or place_id in seen_place_ids:
                            continue
                        seen_place_ids.add(place_id)

                        time.sleep(RATE_LIMIT_SLEEP_SECONDS)
                        details = _place_details(client, place_id)
                        normalized = _normalize(details, category, city_name, search_term)

                        staging_file.write(json.dumps(normalized, ensure_ascii=False) + "\n")
                        staging_file.flush()
                        yield normalized

                    page_token = result.get("nextPageToken")
                    if not page_token:
                        break
                    # Places API (New) requires a short delay before the next page token is valid
                    time.sleep(2)


def collect_all_active_cities() -> list[dict]:
    all_results: list[dict] = []
    for city_cfg in get_locations()["active_cities"]:
        logger.info("Collecting businesses for %s", city_cfg["name"])
        all_results.extend(collect_for_city(city_cfg))
    return all_results


if __name__ == "__main__":
    logging.basicConfig(level=settings.log_level)
    results = collect_all_active_cities()
    print(f"Collected {len(results)} businesses. Staged under {STAGING_DIR}/")
