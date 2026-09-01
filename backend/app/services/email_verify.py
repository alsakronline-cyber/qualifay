"""Pre-send email verification.

Sending to dead mailboxes is what destroys a sending domain: providers throttle above ~5%
hard bounces and blacklist not far above, taking the company's ordinary mail down with the
campaign. So addresses are screened BEFORE they are queued, cheapest check first:

  1. syntax            — free, instant
  2. disposable/role    — free, catches info@/sales@ style catch-alls with low reply value
  3. Hunter verifier    — costs quota, so it runs last and only on what survived

Hunter's actual result vocabulary (verified against the live API, NOT the docs' wording):
    valid | invalid | accept_all | webmail | disposable | unknown
Only "invalid" and "disposable" are fatal. "accept_all" means the server accepts anything so
the mailbox can't be proven either way — common for real Egyptian company domains, and
discarding those would throw away good leads.
"""
import logging
import re

import httpx

logger = logging.getLogger(__name__)

HUNTER_VERIFY = "https://api.hunter.io/v2/email-verifier"

# Statuses that mean the address must never be mailed. Everything else (valid, accept_all,
# webmail, unknown) stays sendable.
FATAL_STATUSES = {"invalid", "disposable"}

_SYNTAX = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")

# Mailboxes that technically deliver but are shared aliases — low reply rate, and blasting
# them is what gets a sender reported.
ROLE_PREFIXES = {
    "info", "sales", "support", "admin", "contact", "office", "help", "hello",
    "noreply", "no-reply", "postmaster", "webmaster", "abuse", "marketing",
}

DISPOSABLE_DOMAINS = {
    "mailinator.com", "guerrillamail.com", "10minutemail.com", "tempmail.com",
    "yopmail.com", "trashmail.com", "throwawaymail.com",
}


def screen(email: str) -> dict:
    """Free local checks. Returns {ok, reason, role} — no network, no quota."""
    e = (email or "").strip().lower()
    if not e or not _SYNTAX.match(e):
        return {"ok": False, "reason": "bad_syntax", "role": False}
    local, _, domain = e.partition("@")
    if domain in DISPOSABLE_DOMAINS:
        return {"ok": False, "reason": "disposable", "role": False}
    return {"ok": True, "reason": "", "role": local in ROLE_PREFIXES}


async def verify(email: str, api_key: str, client: httpx.AsyncClient = None) -> dict:
    """Ask Hunter whether a mailbox exists. Returns {status, score, ok, quota_exhausted}.

    Fails OPEN (ok=True) on network/quota problems: a verifier outage must not silently
    discard a real prospect list.
    """
    own = client is None
    client = client or httpx.AsyncClient(timeout=25)
    try:
        r = await client.get(HUNTER_VERIFY, params={"email": email, "api_key": api_key})
        if r.status_code in (401, 403):
            return {"status": "unknown", "ok": True, "quota_exhausted": False,
                    "error": "auth"}
        if r.status_code == 429:
            return {"status": "unknown", "ok": True, "quota_exhausted": True,
                    "error": "rate_limited"}
        if r.status_code != 200:
            return {"status": "unknown", "ok": True, "quota_exhausted": False,
                    "error": f"http_{r.status_code}"}
        d = (r.json() or {}).get("data") or {}
        status = (d.get("status") or "unknown").lower()
        return {
            "status": status,
            "score": d.get("score"),
            # Fatal only when the mailbox is proven bad. accept_all/webmail/unknown stay
            # sendable — a catch-all server simply can't confirm the mailbox either way.
            "ok": status not in FATAL_STATUSES,
            "quota_exhausted": False,
        }
    except Exception as e:
        logger.warning("hunter verify failed for %s: %s", email, e)
        return {"status": "unknown", "ok": True, "quota_exhausted": False, "error": str(e)[:80]}
    finally:
        if own:
            await client.aclose()
