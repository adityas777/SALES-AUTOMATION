"""Email reply capture via IMAP polling (spec Phase 9).

Chosen over Gmail Push/Pub-Sub because it needs zero extra Google Cloud
setup - it reuses the same Gmail App Password already configured for
sending (SMTP_USER/SMTP_PASS in .env).

Setup needed: Gmail > Settings > Forwarding and POP/IMAP > enable IMAP.
Uses the same account/app password as email_sender.py.

Runs as an APScheduler job (see app.py) every N minutes, pulling UNSEEN
messages, matching sender -> Business by email address, and handing the
plain-text body to reply_handler.handle_inbound_reply(). Processed messages
are marked \\Seen so they aren't re-processed on the next poll.
"""
from __future__ import annotations

import email
import imaplib
import logging
from datetime import datetime, timedelta, timezone
from email.header import decode_header
from email.utils import parseaddr

from src.settings import settings
from src.storage.airtable_client import get_client
from src.replies.reply_handler import handle_inbound_reply
from src.storage.schema import Channel

logger = logging.getLogger(__name__)

IMAP_HOST = "imap.gmail.com"
IMAP_TIMEOUT_SECONDS = 15

# Only look at mail from the last N days. Without this, an inbox that
# accumulates any backlog of unrelated unseen mail (easy to do by accident -
# see incident: pointing this at a busy inbox made one poll hang for minutes
# processing hundreds of unrelated unseen messages) turns every poll into a
# slow full-backlog scan. Anything older than this window is simply never
# looked at - safe, since a real outreach reply always arrives well within
# a few days of the original send.
LOOKBACK_DAYS = 7


def _decode(value: str) -> str:
    parts = decode_header(value or "")
    return "".join(
        part.decode(enc or "utf-8", errors="ignore") if isinstance(part, bytes) else part
        for part, enc in parts
    )


def _extract_plain_text(msg: email.message.Message) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and "attachment" not in str(part.get("Content-Disposition", "")):
                charset = part.get_content_charset() or "utf-8"
                return part.get_payload(decode=True).decode(charset, errors="ignore")
        return ""
    charset = msg.get_content_charset() or "utf-8"
    return msg.get_payload(decode=True).decode(charset, errors="ignore")


def poll_inbox_for_replies() -> int:
    if not settings.smtp_user or not settings.smtp_pass:
        logger.warning("SMTP_USER/SMTP_PASS not configured - skipping email poll")
        return 0

    client = get_client()
    processed = 0

    with imaplib.IMAP4_SSL(IMAP_HOST, timeout=IMAP_TIMEOUT_SECONDS) as imap:
        imap.login(settings.smtp_user, settings.smtp_pass)
        imap.select("INBOX")

        since_date = (datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)).strftime("%d-%b-%Y")
        status, message_ids = imap.search(None, f'(UNSEEN SINCE "{since_date}")')
        if status != "OK":
            return 0

        for msg_id in message_ids[0].split():
            status, msg_data = imap.fetch(msg_id, "(RFC822)")
            if status != "OK":
                continue

            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)

            _, sender_email = parseaddr(_decode(msg.get("From", "")))
            body = _extract_plain_text(msg).strip()
            if not sender_email or not body:
                imap.store(msg_id, "+FLAGS", "\\Seen")
                continue

            business = client.find_business_by_email(sender_email)
            if not business:
                logger.info("No business found for inbound email from %s", sender_email)
                imap.store(msg_id, "+FLAGS", "\\Seen")
                continue

            handle_inbound_reply(business["id"], Channel.EMAIL, body)
            imap.store(msg_id, "+FLAGS", "\\Seen")
            processed += 1

    logger.info("Email poll complete: %d replies processed", processed)
    return processed
