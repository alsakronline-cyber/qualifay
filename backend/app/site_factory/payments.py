"""Paymob checkout links for Site Factory sales.

Uses Paymob's Intention API (create an intention server-side, then send the buyer to the
Unified Checkout with the returned client_secret). The merchant reference is
`sf-<prospect_id>` so the shared /webhook/paymob handler can route the payment back here.

If PAYMOB_SECRET_KEY / PAYMOB_PUBLIC_KEY / PAYMOB_INTEGRATION_ID are not configured, no
card link is produced and the payment message falls back to InstaPay + manual "mark paid".
NOTE: verify the request body against your Paymob account's current API docs before going
live — field requirements differ slightly between Paymob regions/accounts.
"""
from __future__ import annotations

import logging
from typing import Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

INTENTION_URL = "https://accept.paymob.com/v1/intention/"
CHECKOUT_URL = "https://accept.paymob.com/unifiedcheckout/?publicKey={pk}&clientSecret={cs}"
REF_PREFIX = "sf-"


def reference_for(prospect_id: str) -> str:
    return f"{REF_PREFIX}{prospect_id}"


def prospect_id_from_reference(ref: str | None) -> Optional[str]:
    if ref and ref.startswith(REF_PREFIX):
        return ref[len(REF_PREFIX):]
    return None


def configured() -> bool:
    return bool(settings.PAYMOB_SECRET_KEY and settings.PAYMOB_PUBLIC_KEY and settings.PAYMOB_INTEGRATION_ID)


async def create_checkout_link(*, prospect_id: str, business: str, phone: str, amount_egp: int) -> Optional[str]:
    """Return a Unified Checkout URL, or None when Paymob isn't configured / fails."""
    if not configured():
        return None
    payload = {
        "amount": int(amount_egp) * 100,
        "currency": "EGP",
        "payment_methods": [int(x) for x in str(settings.PAYMOB_INTEGRATION_ID).split(",") if x.strip()],
        "items": [{"name": "Website", "amount": int(amount_egp) * 100, "description": f"Website for {business}"[:250], "quantity": 1}],
        "billing_data": {
            "first_name": (business or "Customer")[:50], "last_name": "-", "phone_number": phone or "NA",
            "email": "NA", "country": "EG", "city": "NA", "street": "NA", "building": "NA", "floor": "NA", "apartment": "NA",
        },
        "special_reference": reference_for(prospect_id),
        "notification_url": f"{settings.app_base_url_effective}/api/v1/webhook/paymob",
    }
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(INTENTION_URL, json=payload, headers={"Authorization": f"Token {settings.PAYMOB_SECRET_KEY}"})
        if r.status_code >= 300:
            logger.warning("paymob intention failed %s: %s", r.status_code, r.text[:300])
            return None
        cs = r.json().get("client_secret")
        return CHECKOUT_URL.format(pk=settings.PAYMOB_PUBLIC_KEY, cs=cs) if cs else None
    except Exception as e:  # never block the conversation on the payment provider
        logger.warning("paymob intention error: %s", e)
        return None
