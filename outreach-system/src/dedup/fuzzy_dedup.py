"""Deduplication (spec Phase 4).

Two layers:
1. A cheap deterministic hash (`Dedup Hash` field) used as an Airtable-side
   upsert key - catches exact/near-exact repeats fast (e.g. re-running the
   same collection job).
2. A fuzzy check (`is_probable_duplicate`) for cases where phone is missing
   and the name/address differ slightly (e.g. "Rhythm Dance Academy" vs
   "Rhythm Dance Academy Pvt Ltd") - used before creating a brand new record
   when no exact Dedup Hash match was found.
"""
from __future__ import annotations

import hashlib
import re

from rapidfuzz import fuzz

NAME_MATCH_THRESHOLD = 92


def normalize_phone(phone: str) -> str:
    """Strip everything but digits, drop a leading country-code '91' /
    leading '0' so the same Indian number in different formats collapses to
    one key."""
    digits = re.sub(r"\D", "", phone or "")
    if digits.startswith("91") and len(digits) > 10:
        digits = digits[-10:]
    return digits.lstrip("0")


def normalize_address(address: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (address or "").lower())


def normalize_name(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip().lower())


def compute_dedup_hash(name: str, address: str, phone: str) -> str:
    phone_norm = normalize_phone(phone)
    if phone_norm:
        key = f"phone:{phone_norm}"
    else:
        key = f"namead:{normalize_name(name)}|{normalize_address(address)[:20]}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]


def is_probable_duplicate(name_a: str, city_a: str, name_b: str, city_b: str) -> bool:
    """Fuzzy fallback for records that don't share a phone number: same city
    AND name similarity above threshold -> treat as the same business."""
    if normalize_name(city_a) != normalize_name(city_b):
        return False
    score = fuzz.token_sort_ratio(normalize_name(name_a), normalize_name(name_b))
    return score > NAME_MATCH_THRESHOLD
