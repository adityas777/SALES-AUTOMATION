"""Email sender (spec Phase 7).

Uses plain SMTP with a Gmail App Password by default (Path B in .env.example)
because it needs zero OAuth consent screen setup and is the fastest way to
get Phase 7's "email only, no approval needed" milestone working end-to-end.

Setup needed:
  1. Use a Gmail account (a fresh one is fine) with 2-Step Verification on.
  2. Create an App Password: Google Account > Security > 2-Step Verification
     > App passwords. Use that as SMTP_PASS, the Gmail address as SMTP_USER.
  3. Free tier limit: ~500 sends/day per Gmail account - round-robin across
     multiple SMTP_USER accounts if you outgrow that (not implemented here;
     add a list + rotation in settings.py when needed).

Category images are inlined (cid) so they render in the email body; videos/
reels are linked rather than attached (large files should not be raw email
attachments - spec Phase 7 note).
"""
from __future__ import annotations

import logging
import mimetypes
import smtplib
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from src.settings import settings

logger = logging.getLogger(__name__)


def _connect() -> smtplib.SMTP:
    server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30)
    server.starttls()
    server.login(settings.smtp_user, settings.smtp_pass)
    return server


def send_email(
    to_email: str,
    subject: str,
    html_body: str,
    media: dict | None = None,
) -> None:
    """`media` is the dict returned by template_selector.select(...)["media"]:
    {"type": "image"|"video"|"reel", "path": "...", "exists": bool}."""
    msg = MIMEMultipart("related")
    msg["Subject"] = subject
    msg["From"] = settings.smtp_user
    msg["To"] = to_email

    body_html = html_body
    inline_image = None

    if media and media.get("exists") and media["type"] == "image":
        image_path = Path(media["path"])
        with open(image_path, "rb") as f:
            inline_image = MIMEImage(f.read())
        inline_image.add_header("Content-ID", "<category_media>")
        inline_image.add_header("Content-Disposition", "inline", filename=image_path.name)
        body_html = body_html.replace(
            "<em>(see attached image)</em>",
            '<img src="cid:category_media" alt="" style="max-width:100%;" />',
        )

    msg.attach(MIMEText(body_html, "html"))
    if inline_image is not None:
        msg.attach(inline_image)

    with _connect() as server:
        server.sendmail(settings.smtp_user, [to_email], msg.as_string())

    logger.info("Email sent to %s (subject=%r)", to_email, subject)
