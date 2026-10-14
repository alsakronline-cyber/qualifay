"""One-click unsubscribe links (Law 151/2020 opt-out, Gmail/Yahoo one-click rules).

Every cold email to a lead carries a signed link in its footer and in the List-Unsubscribe
header. The token is an HS256 JWT bound to the lead and tenant with a dedicated purpose, so
it can't be swapped for an auth token. It does not expire: an opt-out link must keep working.

WhatsApp messages don't carry the link — the anti-ban rules forbid URLs in the first messages
to a new contact. There, opting out is the inbound STOP / إيقاف keyword handled in the webhook.
"""
import logging
from typing import Optional
from urllib.parse import quote

import jwt

from app.core.config import settings

logger = logging.getLogger(__name__)

PURPOSE = "unsubscribe"
PATH = "/api/v1/webhook/unsubscribe"


def make_token(lead_id: str, tenant_id: str) -> str:
    return jwt.encode({"lead_id": str(lead_id), "tenant_id": str(tenant_id), "purpose": PURPOSE},
                      settings.SECRET_KEY, algorithm="HS256")


def read_token(token: str) -> Optional[dict]:
    """The token's claims, or None if it's forged, malformed or not an unsubscribe token.
    The purpose claim is required, so no other token signed with SECRET_KEY (e.g. a login
    token that happens to carry a lead_id) can unsubscribe anyone."""
    try:
        claims = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    if not claims.get("lead_id"):
        return None
    if claims.get("purpose") != PURPOSE:
        return None
    return claims


def unsubscribe_url(lead) -> str:
    return f"{settings.app_base_url_effective}{PATH}?token={quote(make_token(lead.id, lead.tenant_id))}"


def footer(url: str, language: str = "ar") -> str:
    if language == "en":
        return f"\n\n—\nDon't want to hear from us? Unsubscribe in one click: {url}"
    return f"\n\n—\nلا ترغب في تلقي رسائلنا؟ إلغاء الاشتراك بنقرة واحدة: {url}"


def with_unsubscribe(body: str, lead) -> tuple[str, str]:
    """(body + opt-out footer, the link) for an email to `lead`."""
    url = unsubscribe_url(lead)
    lang = "en" if (lead.language or "ar") == "en" else "ar"
    return (body or "") + footer(url, lang), url


async def unsubscribe_lead(db, lead_id: str, tenant_id: Optional[str], via: str) -> bool:
    """Mark the lead unsubscribed and stop its cadences. Idempotent. Returns True if a lead
    matched. The tenant claim (when present) must match, so a token can't reach across tenants."""
    from sqlalchemy import select
    from app.models.models import Lead, LeadStatus
    q = select(Lead).where(Lead.id == lead_id)
    if tenant_id:
        q = q.where(Lead.tenant_id == tenant_id)
    lead = (await db.execute(q)).scalar_one_or_none()
    if not lead:
        return False
    if lead.status != LeadStatus.unsubscribed:
        from app.services.email_tracking import mark_latest
        await mark_latest(db, "unsubscribed_at", tenant_id=lead.tenant_id, lead_id=lead.id)
        lead.status = LeadStatus.unsubscribed
        lead.raw_data = {**(lead.raw_data or {}), "unsubscribed_via": via}
        logger.info(f"Lead {lead.id} unsubscribed via {via}")
    await db.commit()
    try:
        from app.workers.sequence_tasks import stop_enrollments_for_lead
        await stop_enrollments_for_lead(db, lead.id)
    except Exception as e:
        logger.warning(f"stopping cadences after unsubscribe failed for {lead.id}: {e}")
    return True
