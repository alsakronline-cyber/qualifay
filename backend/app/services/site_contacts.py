"""Read a company's own website and return the contact emails it actually publishes.

Contacts must come from the real page, never from an AI guess: a guessed address bounces,
and bounces damage the sender's domain reputation. Only emails on the company's own domain
(or the exact address its site publishes) are returned.
"""
import re
from typing import Optional
from urllib.parse import urljoin, urlparse

import httpx

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
CONTACT_PATHS = ["", "/contact", "/contact-us", "/about", "/about-us"]
_JUNK = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp")
_PLACEHOLDER = ("example.", "domain.", "yourdomain", "email.com", "sentry", "wixpress")
# Generic inboxes a business monitors — preferred for first contact over personal ones.
_ROLE_FIRST = ("info", "hello", "contact", "sales", "business", "studio", "team", "office", "enquiries", "inquiries")


def _domain(url: str) -> str:
    host = urlparse(url if "//" in url else f"https://{url}").netloc.lower()
    return host[4:] if host.startswith("www.") else host


def pick_emails(text: str, site_url: str) -> list[str]:
    """Emails from `text` that belong to the site's own domain, role inboxes first."""
    site = _domain(site_url)
    found = []
    for m in EMAIL_RE.findall(text or ""):
        e = m.strip(".").lower()
        if e.endswith(_JUNK) or any(p in e for p in _PLACEHOLDER):
            continue
        dom = e.split("@", 1)[1]
        if site and (dom == site or dom.endswith("." + site) or site.endswith("." + dom)):
            if e not in found:
                found.append(e)
    return sorted(found, key=lambda e: (e.split("@")[0] not in _ROLE_FIRST, e))


async def fetch_site_text(site_url: str, max_pages: int = 4) -> str:
    """Homepage + a few contact pages, as text with mailto: links kept. Best effort."""
    base = site_url if "//" in site_url else f"https://{site_url}"
    out = []
    headers = {"User-Agent": "Mozilla/5.0 (compatible; QualifayBot/1.0; business contact lookup)"}
    async with httpx.AsyncClient(timeout=15, follow_redirects=True, headers=headers) as c:
        for path in CONTACT_PATHS[:max_pages]:
            try:
                r = await c.get(urljoin(base, path))
                if r.status_code == 200 and "text/html" in r.headers.get("content-type", ""):
                    html = r.text
                    out.append(" ".join(re.findall(r"mailto:([^\"'?>\s]+)", html)))
                    out.append(re.sub(r"<[^>]+>", " ", html))
            except Exception:
                continue
    return " ".join(out)


async def find_contact_email(site_url: Optional[str]) -> Optional[str]:
    if not site_url:
        return None
    emails = pick_emails(await fetch_site_text(site_url), site_url)
    return emails[0] if emails else None
