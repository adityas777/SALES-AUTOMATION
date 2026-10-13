"""Gnani.ai (Vachana) Voice Client: Speech-to-Text (STT) and Text-to-Speech (TTS)."""
from __future__ import annotations

import logging
from typing import Optional
import httpx

from src.settings import settings

logger = logging.getLogger(__name__)

STT_URL = "https://api.vachana.ai/stt/v3"
TTS_URL = "https://api.vachana.ai/api/v1/tts/inference"
DEFAULT_VOICE = "Nalini"
DEFAULT_MODEL = "timbre-v2.5"


def is_gnani_configured() -> bool:
    return bool(settings.gnani_api_key)


def transcribe_audio(
    audio_bytes: bytes,
    filename: str = "audio.wav",
    content_type: str = "audio/wav",
    language_code: str = "en-IN",
    timeout_sec: float = 15.0,
) -> str:
    """Transcribes audio using Gnani STT API (v3).

    Args:
        audio_bytes: Raw audio bytes (WAV, MP3, WEBM, etc.)
        filename: Filename with extension (e.g. 'recording.wav' or 'recording.webm')
        content_type: MIME type of audio
        language_code: BCP-47 language code ('en-IN', 'hi-IN', etc.)
        timeout_sec: Request timeout in seconds

    Returns:
        Transcribed text string.
    """
    if not settings.gnani_api_key:
        raise ValueError("GNANI_API_KEY / gnani key is not set in .env")

    headers = {
        "X-API-Key-ID": settings.gnani_api_key,
    }

    files = {
        "audio_file": (filename, audio_bytes, content_type),
    }
    data = {
        "language_code": language_code,
    }

    try:
        with httpx.Client(timeout=timeout_sec) as client:
            resp = client.post(STT_URL, headers=headers, files=files, data=data)
            resp.raise_for_status()
            payload = resp.json()
            transcript = payload.get("transcript") or payload.get("output", {}).get("literal", "")
            logger.info("Gnani STT succeeded: '%s' (lang: %s)", transcript, language_code)
            if transcript:
                return transcript.strip()
    except Exception as exc:
        logger.warning("Gnani STT request encountered error: %s, attempting Groq Whisper fallback", exc)

    # Automatic fallback to Groq Whisper if available
    if settings.groq_api_key:
        try:
            from groq import Groq
            groq_client = Groq(api_key=settings.groq_api_key)
            whisper_resp = groq_client.audio.transcriptions.create(
                file=(filename, audio_bytes, content_type),
                model="whisper-large-v3",
                language="hi" if "hi" in language_code.lower() else "en",
            )
            transcript = (whisper_resp.text or "").strip()
            logger.info("Groq Whisper STT succeeded: '%s'", transcript)
            if transcript:
                return transcript
        except Exception as groq_exc:
            logger.exception("Groq Whisper fallback also failed: %s", groq_exc)

    raise RuntimeError("Voice transcription could not be completed. Please ensure you speak clearly or retry.")


def synthesize_speech(
    text: str,
    language_code: str = "en-IN",
    voice: str = DEFAULT_VOICE,
    model: str = DEFAULT_MODEL,
    sample_rate: int = 24000,
    timeout_sec: float = 15.0,
) -> bytes:
    """Synthesizes text to WAV audio using Gnani TTS API.

    Returns:
        Bytes containing RIFF WAV audio data.
    """
    if not settings.gnani_api_key:
        raise ValueError("GNANI_API_KEY / gnani key is not set in .env")

    headers = {
        "X-API-Key-ID": settings.gnani_api_key,
        "Content-Type": "application/json",
    }

    payload = {
        "text": text,
        "language": language_code,
        "voice": voice,
        "model": model,
        "speed": 1.0,
        "audio_config": {
            "encoding": "linear_pcm",
            "container": "wav",
            "num_channels": 1,
            "sample_rate": sample_rate,
            "sample_width": 2,
        },
    }

    try:
        with httpx.Client(timeout=timeout_sec) as client:
            resp = client.post(TTS_URL, headers=headers, json=payload)
            resp.raise_for_status()
            return resp.content
    except Exception as exc:
        logger.exception("Gnani TTS failed for text: '%s'", text)
        raise RuntimeError(f"Gnani TTS failed: {exc}") from exc
