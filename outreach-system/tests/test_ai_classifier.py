"""Only tests the deterministic opt-out short-circuit, which must work with
zero network calls (it's the safety net if Groq is down or misconfigured).
Full label classification needs a live GROQ_API_KEY and isn't covered here.
"""
from src.replies.ai_classifier import classify_reply
from src.storage.schema import AIClassificationLabel as Label


def test_stop_keyword_always_opts_out():
    result = classify_reply("STOP")
    assert result == {"label": Label.OPT_OUT, "confidence": 1.0}


def test_unsubscribe_phrase_opts_out():
    result = classify_reply("please unsubscribe me from this list")
    assert result["label"] == Label.OPT_OUT
    assert result["confidence"] == 1.0


def test_missing_api_key_forces_human_review(monkeypatch):
    # Settings is a frozen dataclass, so replace the whole module-level
    # reference rather than mutating an attribute on it.
    class FakeSettings:
        groq_api_key = ""

    monkeypatch.setattr("src.replies.ai_classifier.settings", FakeSettings())
    result = classify_reply("Sure, tell me more!")
    assert result["label"] == Label.HUMAN_REVIEW
