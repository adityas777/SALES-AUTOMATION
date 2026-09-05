"""Thin wrapper around pyairtable. This is the ONLY module that should import
pyairtable directly - everything else in the app calls through here so the
Airtable-specific quirks (rate limits, field names, retries) live in one place.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from pyairtable import Api

from src.settings import settings
from src.storage.schema import (
    TBL_BUSINESSES, TBL_INTERACTIONS, TBL_HANDOFF_QUEUE,
    BusinessFields as BF, InteractionFields as IF, HandoffFields as HF,
    BusinessStatus,
)

logger = logging.getLogger(__name__)


class AirtableClient:
    def __init__(self, api_key: Optional[str] = None, base_id: Optional[str] = None):
        self._api = Api(api_key or settings.airtable_api_key)
        self._base_id = base_id or settings.airtable_base_id
        self._businesses = self._api.table(self._base_id, TBL_BUSINESSES)
        self._interactions = self._api.table(self._base_id, TBL_INTERACTIONS)
        self._handoff = self._api.table(self._base_id, TBL_HANDOFF_QUEUE)

    # ---------------- Businesses ----------------

    def find_business_by_dedup_hash(self, dedup_hash: str) -> Optional[dict]:
        formula = f"{{{BF.DEDUP_HASH}}} = '{dedup_hash}'"
        return self._businesses.first(formula=formula)

    def get_business(self, record_id: str) -> dict:
        return self._businesses.get(record_id)

    def upsert_business(self, fields: dict) -> dict:
        """Insert a new business, or update the existing record with the same
        Dedup Hash (merge - keep richer record, per spec Phase 4)."""
        dedup_hash = fields.get(BF.DEDUP_HASH)
        existing = self.find_business_by_dedup_hash(dedup_hash) if dedup_hash else None

        if existing:
            merged = {**existing["fields"]}
            for key, value in fields.items():
                if value not in (None, "", []) and not merged.get(key):
                    merged[key] = value
            # typecast=True: City is a single-select seeded only from
            # locations.yaml's pre-registered cities - the free-text city
            # input (see pipeline.py) can send any city name, and this lets
            # Airtable auto-add it as a new option instead of rejecting it.
            self._businesses.update(existing["id"], merged, typecast=True)
            return {"id": existing["id"], "fields": merged, "created": False}

        fields.setdefault(BF.STATUS, BusinessStatus.NEW)
        record = self._businesses.create(fields, typecast=True)
        return {**record, "created": True}

    def batch_upsert_businesses(self, records: list[dict]) -> list[dict]:
        """Bulk path using pyairtable's native upsert-by-key when Dedup Hash
        is already computed for every record (faster than one-by-one)."""
        return self._businesses.batch_upsert(records, key_fields=[BF.DEDUP_HASH])

    def update_status(self, business_id: str, status: str, extra_fields: Optional[dict] = None) -> dict:
        fields = {BF.STATUS: status}
        if extra_fields:
            fields.update(extra_fields)
        return self._businesses.update(business_id, fields)

    def list_businesses(self, formula: Optional[str] = None) -> list[dict]:
        return self._businesses.all(formula=formula) if formula else self._businesses.all()

    def find_business_by_phone(self, phone: str) -> Optional[dict]:
        formula = f"{{{BF.PHONE}}} = '{phone}'"
        return self._businesses.first(formula=formula)

    def email_already_contacted(self, email: str, exclude_business_id: str) -> bool:
        """True if some OTHER business record already has this exact email
        and has already been sent outreach. Google Maps often lists separate
        franchise locations (e.g. multiple gym branches) that share one
        corporate contact email - without this check each listing would
        independently trigger its own send, spamming that one real inbox
        with several near-duplicate cold emails in a single run."""
        if not email:
            return False
        formula = f"{{{BF.EMAIL}}} = '{email}'"
        matches = self._businesses.all(formula=formula)
        return any(
            m["id"] != exclude_business_id and m["fields"].get(BF.STATUS) != BusinessStatus.NEW
            for m in matches
        )

    def find_business_by_email(self, email: str) -> Optional[dict]:
        formula = f"{{{BF.EMAIL}}} = '{email}'"
        return self._businesses.first(formula=formula)

    def businesses_due_for_followup(self) -> list[dict]:
        """Anything not in a stop status - the caller (followup/scheduler.py)
        applies the cadence_days math per-record since Airtable formulas can't
        easily express "N days since Last Contacted where N depends on
        Follow-up Count"."""
        stop_clause = ", ".join(f"{{{BF.STATUS}}} = '{s}'" for s in BusinessStatus.STOP_STATUSES)
        formula = f"NOT(OR({stop_clause}))"
        return self._businesses.all(formula=formula)

    # ---------------- Interactions ----------------

    def log_interaction(
        self,
        business_id: str,
        channel: str,
        direction: str,
        message_body: str,
        template_used: str = "",
        media_attached: Optional[list[dict]] = None,
        ai_classification: Optional[str] = None,
    ) -> dict:
        fields = {
            IF.BUSINESS: [business_id],
            IF.CHANNEL: channel,
            IF.DIRECTION: direction,
            IF.MESSAGE_BODY: message_body,
            IF.TEMPLATE_USED: template_used,
            IF.TIMESTAMP: datetime.now(timezone.utc).isoformat(),
        }
        if media_attached:
            fields[IF.MEDIA_ATTACHED] = media_attached
        if ai_classification:
            fields[IF.AI_CLASSIFICATION] = ai_classification
        return self._interactions.create(fields)

    def list_interactions_for_business(self, business_id: str) -> list[dict]:
        formula = f"FIND('{business_id}', ARRAYJOIN({{{IF.BUSINESS}}}))"
        return self._interactions.all(formula=formula)

    # ---------------- Human handoff ----------------

    def add_to_handoff_queue(self, business_id: str, reason: str, priority: str = "Normal") -> dict:
        fields = {
            HF.BUSINESS: [business_id],
            HF.REASON: reason,
            HF.PRIORITY: priority,
            HF.RESOLVED: False,
        }
        return self._handoff.create(fields)

    def list_unresolved_handoff(self) -> list[dict]:
        formula = f"NOT({{{HF.RESOLVED}}})"
        return self._handoff.all(formula=formula)

    def resolve_handoff_for_business(self, business_id: str) -> int:
        """Marks every unresolved HumanHandoffQueue row for this business as
        resolved (normally just one). Returns how many rows were updated."""
        updated = 0
        for row in self.list_unresolved_handoff():
            linked_ids = row["fields"].get(HF.BUSINESS, [])
            if business_id in linked_ids:
                self._handoff.update(row["id"], {HF.RESOLVED: True})
                updated += 1
        return updated

    def latest_interaction_for_business(self, business_id: str) -> Optional[dict]:
        interactions = self.list_interactions_for_business(business_id)
        if not interactions:
            return None
        return max(interactions, key=lambda r: r["fields"].get(IF.TIMESTAMP, ""))


_client: Optional[AirtableClient] = None


def get_client() -> AirtableClient:
    global _client
    if _client is None:
        _client = AirtableClient()
    return _client
