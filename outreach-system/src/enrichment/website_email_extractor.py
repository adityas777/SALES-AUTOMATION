"""Website -> email enrichment (spec Phase 3).

If a business has a website but no email yet, fetch the homepage and a
likely /contact page, and regex/`mailto:`-extract an email address.
Per-domain results are cached in-process to avoid re-fetching the same site
across categories/search-term duplicates within one run.
"""
from __future__ import annotations

import logging
import re
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

EMAIL_REGEX = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
GENERIC_LOCAL_PARTS_TO_SKIP = {"example", "test", "sentry", "wixpress"}
CONTACT_PATHS = ["/contact", "/contact-us", "/contactus", "/about", "/about-us"]

# A lot of small businesses put a YouTube/Instagram/Facebook profile link in
# the Google Maps "website" field instead of a real site. Crawling those
# platforms' own /contact, /about pages never finds a business email and just
# wastes several requests per business - skip them outright.
NON_BUSINESS_WEBSITE_DOMAINS = {
    "youtube.com", "youtu.be", "instagram.com", "facebook.com", "fb.com",
    "twitter.com", "x.com", "linkedin.com", "wa.me", "whatsapp.com",
    "page.link", "goo.gl", "bit.ly",
}


def _is_non_business_platform(domain: str) -> bool:
    domain = domain.removeprefix("www.")
    return any(domain == d or domain.endswith(f".{d}") for d in NON_BUSINESS_WEBSITE_DOMAINS)

_domain_cache: dict[str, str] = {}


def _is_probably_real(email: str) -> bool:
    local_part = email.split("@")[0].lower()
    return not any(bad in local_part for bad in GENERIC_LOCAL_PARTS_TO_SKIP)


def _extract_emails_from_html(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")

    mailto_emails = [
        href.replace("mailto:", "").split("?")[0].strip()
        for a in soup.find_all("a", href=True)
        if (href := a["href"]).lower().startswith("mailto:")
    ]

    text_emails = EMAIL_REGEX.findall(soup.get_text(" "))

    candidates = [e for e in (mailto_emails + text_emails) if _is_probably_real(e)]
    # de-dupe, preserve order, mailto: matches first (higher trust)
    seen = set()
    ordered = []
    for e in candidates:
        key = e.lower()
        if key not in seen:
            seen.add(key)
            ordered.append(e)
    return ordered


def _fetch(client: httpx.Client, url: str) -> str | None:
    try:
        resp = client.get(url, timeout=10, follow_redirects=True)
        if resp.status_code == 200:
            return resp.text
    except httpx.HTTPError as exc:
        logger.debug("Fetch failed for %s: %s", url, exc)
    return None


def extract_email_for_website(website: str) -> str | None:
    if not website:
        return None

    domain = urlparse(website).netloc.lower()
    if _is_non_business_platform(domain):
        return None
    if domain in _domain_cache:
        return _domain_cache[domain] or None

    email_found = None
    with httpx.Client(headers={"User-Agent": "Mozilla/5.0 (compatible; OutreachBot/1.0)"}) as client:
        homepage_html = _fetch(client, website)
        if homepage_html:
            emails = _extract_emails_from_html(homepage_html)
            if emails:
                email_found = emails[0]

        if not email_found:
            for path in CONTACT_PATHS:
                contact_url = urljoin(website, path)
                html = _fetch(client, contact_url)
                if not html:
                    continue
                emails = _extract_emails_from_html(html)
                if emails:
                    email_found = emails[0]
                    break

    _domain_cache[domain] = email_found or ""
    return email_found


def enrich_business(business: dict) -> dict:
    """Mutates a copy of the business dict, adding 'email' if it was missing
    and a website is present. Safe no-op otherwise."""
    enriched = dict(business)
    if not enriched.get("email") and enriched.get("website"):
        found = extract_email_for_website(enriched["website"])
        if found:
            enriched["email"] = found
    return enriched
