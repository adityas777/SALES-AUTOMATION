"""Unit tests for state-aware voice intent parser and slot preservation rules.
"""
import pytest
from src.voice.intent_parser import classify_intent, parse_voice_command


def test_confirm_in_confirming_state_preserves_slots():
    """Test 'sounds good' in CONFIRMING state returns confirm intent and keeps existing city/categories."""
    res = parse_voice_command(
        text="sounds good",
        current_state="CONFIRMING",
        current_city="Bhilai, Chhattisgarh",
        current_categories=["dance", "gym"],
    )
    assert res["intent"] == "confirm"
    assert res["city"] == "Bhilai, Chhattisgarh"
    assert set(res["categories"]) == {"dance", "gym"}


def test_hinglish_confirm_phrases():
    """Test Hinglish confirmation phrases in CONFIRMING state."""
    phrases = ["haan kar do", "theek hai", "chalo shuru karo", "sahi hai", "bilkul"]
    for phrase in phrases:
        res = parse_voice_command(
            text=phrase,
            current_state="CONFIRMING",
            current_city="Raipur, Chhattisgarh",
            current_categories=["photography"],
        )
        assert res["intent"] == "confirm", f"Failed for phrase: {phrase}"
        assert res["city"] == "Raipur, Chhattisgarh"
        assert res["categories"] == ["photography"]


def test_status_update_in_running_state_does_not_touch_slots():
    """Test 'what's the status' or 'how many leads so far?' in RUNNING state returns status_update without clearing slots."""
    queries = [
        "what's the status",
        "how many leads so far?",
        "how many messages sent?",
        "kya update hai",
        "progress report",
    ]
    for q in queries:
        res = parse_voice_command(
            text=q,
            current_state="RUNNING",
            current_city="Pune",
            current_categories=["dance"],
        )
        assert res["intent"] == "status_update", f"Failed for query: {q}"
        assert res["city"] == "Pune"
        assert res["categories"] == ["dance"]


def test_slot_edit_in_confirming_state():
    """Test 'add yoga' in CONFIRMING state merges yoga into categories while keeping city Pune intact."""
    res = parse_voice_command(
        text="add yoga",
        current_state="CONFIRMING",
        current_city="Pune",
        current_categories=["dance"],
    )
    assert res["city"] == "Pune"
    assert "yoga" in res["categories"]
    assert "dance" in res["categories"]


def test_filler_words_do_not_clear_slots():
    """Test filler words in CONFIRMING state leave existing slots untouched."""
    res = parse_voice_command(
        text="um hello",
        current_state="CONFIRMING",
        current_city="Mumbai",
        current_categories=["salons"],
    )
    assert res["city"] == "Mumbai"
    assert res["categories"] == ["salons"]


def test_cancel_in_confirming_state():
    """Test 'rehne do' or 'cancel' in CONFIRMING state returns cancel intent."""
    res = parse_voice_command(
        text="rehne do",
        current_state="CONFIRMING",
        current_city="Bhilai, Chhattisgarh",
        current_categories=["dance"],
    )
    assert res["intent"] == "cancel"
    assert res["city"] == "Bhilai, Chhattisgarh"
