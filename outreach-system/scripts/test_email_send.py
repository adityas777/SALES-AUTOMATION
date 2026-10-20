"""Quick utility to test sending a real personalized outreach email using configured Gmail SMTP."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.personalization import groq_personalizer
from src.senders import email_sender
from src.settings import settings


def main() -> None:
    parser = argparse.ArgumentParser(description="Send a test outreach email via Gmail SMTP")
    parser.add_argument("--to", default=settings.smtp_user, help="Recipient email (defaults to SMTP_USER)")
    parser.add_argument("--business-name", default="Dance Beats Academy", help="Business name")
    parser.add_argument("--category", default="dance", help="Category (dance, yoga, gym_fitness, etc.)")
    parser.add_argument("--city", default="Delhi", help="City name")
    args = parser.parse_args()

    recipient = args.to or settings.smtp_user
    if not recipient:
        print("Error: No recipient specified and SMTP_USER is not set in .env")
        sys.exit(1)

    print(f"1. Rendering personalized email with Groq for '{args.business_name}' ({args.category} in {args.city})...")
    rendered = groq_personalizer.render_email(args.business_name, args.category, args.city)
    print(f"   Subject: {rendered['subject']}")

    print(f"2. Connecting to Gmail SMTP ({settings.smtp_user}) and sending to {recipient}...")
    email_sender.send_email(recipient, rendered["subject"], rendered["html_body"], rendered.get("media"))
    print(f"SUCCESS: Email sent successfully to {recipient}! Check your inbox.")


if __name__ == "__main__":
    main()
