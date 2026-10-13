from fastapi.testclient import TestClient
from src.app import app
from src.voice.intent_parser import parse_voice_command

client = TestClient(app)


def test_voice_status_endpoint():
    resp = client.get("/api/voice/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "gnani_configured" in data
    assert "languages" in data
    assert len(data["languages"]) >= 2


def test_intent_parser_fallback_rule():
    # Test deterministic fallback
    result = parse_voice_command("Find dance academies in Pune")
    assert "dance" in result["categories"]
    assert "pune" in result["city"].lower()


def test_voice_parse_text_endpoint():
    resp = client.post(
        "/api/voice/parse-text",
        json={"text": "Find dance academies and music studios in Pune", "language_code": "en-IN"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "pune" in data["city"].lower()
    assert any(c in ["dance", "music_recording"] for c in data["categories"])
    assert bool(data.get("spoken_response"))
