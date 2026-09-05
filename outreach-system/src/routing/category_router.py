"""Category router (spec Phase 5).

The Places collector already tags each business with the canonical category
it was searched under, so routing is usually a pass-through. This module
exists as the single place that reconciles a business back to a canonical
category key for any source that DOESN'T already carry one cleanly (e.g. a
future scraper fallback, or a business found under an ambiguous search term
matching multiple categories) - so downstream template/media selection never
has to guess.
"""
from __future__ import annotations

from src.config_loader import get_categories

# Extra keyword hints from Google's own place `types[]` -> canonical category,
# used only when matched_search_term doesn't map cleanly.
GOOGLE_TYPE_HINTS = {
    "dance": ["dance_school"],
    "yoga": [],
    "gym_fitness": ["gym"],
    "photography": [],
    "music_recording": [],
    "schools_colleges": ["school", "university", "primary_school", "secondary_school"],
    "sports": ["stadium"],
    "event_venues": ["banquet_hall", "event_venue"],
    "cafes_restaurants": ["cafe", "restaurant"],
    "coworking": [],
    "art_studios": ["art_studio"],
    "salons": ["beauty_salon", "hair_salon", "spa"],
    "theatres": ["movie_theater", "performing_arts_theater"],
    "activity_centres": [],
}


def _search_term_to_category(search_term: str) -> str | None:
    categories = get_categories()
    for category, cfg in categories.items():
        if search_term in cfg["search_terms"]:
            return category
    return None


def resolve_category(business: dict) -> str:
    """Returns a canonical category key for a raw/normalized business dict.
    Falls back through: explicit `category` field -> matched_search_term ->
    google_types keyword hints -> 'uncategorized'."""
    categories = get_categories()

    explicit = business.get("category")
    if explicit in categories:
        return explicit

    search_term = business.get("matched_search_term")
    if search_term:
        resolved = _search_term_to_category(search_term)
        if resolved:
            return resolved

    google_types = set(business.get("google_types", []))
    for category, hint_types in GOOGLE_TYPE_HINTS.items():
        if google_types.intersection(hint_types):
            return category

    return "uncategorized"
