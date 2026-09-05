"""Loads .env once and exposes typed settings. Import `settings` everywhere else."""
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


@dataclass(frozen=True)
class Settings:
    airtable_api_key: str = _env("AIRTABLE_API_KEY")
    airtable_base_id: str = _env("AIRTABLE_BASE_ID")

    google_maps_api_key: str = _env("GOOGLE_MAPS_API_KEY")

    whatsapp_token: str = _env("WHATSAPP_TOKEN")
    whatsapp_phone_number_id: str = _env("WHATSAPP_PHONE_NUMBER_ID")
    whatsapp_verify_token: str = _env("WHATSAPP_VERIFY_TOKEN")

    groq_api_key: str = _env("GROQ_API_KEY")

    gmail_client_id: str = _env("GMAIL_CLIENT_ID")
    gmail_client_secret: str = _env("GMAIL_CLIENT_SECRET")
    gmail_refresh_token: str = _env("GMAIL_REFRESH_TOKEN")
    gmail_sender_address: str = _env("GMAIL_SENDER_ADDRESS")

    smtp_host: str = _env("SMTP_HOST", "smtp.gmail.com")
    smtp_port: int = int(_env("SMTP_PORT", "587"))
    smtp_user: str = _env("SMTP_USER")
    smtp_pass: str = _env("SMTP_PASS")

    slack_webhook_url: str = _env("SLACK_WEBHOOK_URL")

    app_env: str = _env("APP_ENV", "development")
    log_level: str = _env("LOG_LEVEL", "INFO")


settings = Settings()
