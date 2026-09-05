"""Phase 2 smoke test: push 5 hand-crafted business rows through
airtable_client.upsert_business() and read them back. Run this after
setup_airtable_schema.py and before building the real Places API collector -
it proves the Airtable schema + client work end-to-end.

Usage: python scripts/seed_sample_businesses.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.storage.airtable_client import get_client
from src.storage.schema import BusinessFields as BF
from src.dedup.fuzzy_dedup import compute_dedup_hash

SAMPLE_BUSINESSES = [
    {"name": "Rhythm Dance Academy", "category": "dance", "city": "Durg, Chhattisgarh",
     "address": "Civil Lines, Durg", "phone": "+919999900001", "website": "https://rhythmdance.example.com",
     "listing_url": "https://maps.google.com/?cid=1"},
    {"name": "Sunrise Yoga Studio", "category": "yoga", "city": "Raipur, Chhattisgarh",
     "address": "Shankar Nagar, Raipur", "phone": "+919999900002", "website": "",
     "listing_url": "https://maps.google.com/?cid=2"},
    {"name": "PowerHouse Gym", "category": "gym_fitness", "city": "Durg, Chhattisgarh",
     "address": "Supela, Durg", "phone": "+919999900003", "website": "https://powerhousegym.example.com",
     "listing_url": "https://maps.google.com/?cid=3"},
    {"name": "Click Studio Photography", "category": "photography", "city": "Raipur, Chhattisgarh",
     "address": "Pandri, Raipur", "phone": "+919999900004", "website": "",
     "listing_url": "https://maps.google.com/?cid=4"},
    {"name": "Grand Celebration Banquet Hall", "category": "event_venues", "city": "Durg, Chhattisgarh",
     "address": "Station Road, Durg", "phone": "+919999900005", "website": "https://grandcelebration.example.com",
     "listing_url": "https://maps.google.com/?cid=5"},
]


def main() -> None:
    client = get_client()
    for biz in SAMPLE_BUSINESSES:
        dedup_hash = compute_dedup_hash(name=biz["name"], address=biz["address"], phone=biz["phone"])
        fields = {
            BF.NAME: biz["name"],
            BF.CATEGORY: biz["category"],
            BF.CITY: biz["city"],
            BF.ADDRESS: biz["address"],
            BF.PHONE: biz["phone"],
            BF.WEBSITE: biz["website"],
            BF.LISTING_URL: biz["listing_url"],
            BF.DEDUP_HASH: dedup_hash,
        }
        result = client.upsert_business(fields)
        action = "created" if result.get("created") else "updated (dup)"
        print(f"{action}: {biz['name']} -> {result['id']}")

    print("\nAll 5 rows pushed. Open the Airtable base and confirm they look right.")


if __name__ == "__main__":
    main()
