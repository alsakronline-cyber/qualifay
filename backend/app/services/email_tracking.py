"""Per-email tracking for the Email reports page.

Every cold email to a lead gets an EmailSend row. Afterwards the row is stamped by:
  * opened       — a 1×1 pixel in the HTML part (only when the tenant has open tracking on)
  * bounced      — the inbox poller finds a delivery-failure notice for the address
  * replied      — the inbox poller threads a reply from the lead
  * unsubscribed — the lead uses the unsubscribe link or replies asking to stop

Opens are an estimate: many mail apps block images (missed opens) and Apple Mail
pre-loads them (false opens). Bounces, replies and unsubscribes are exact.
"""
import hashlib
import hmac
import html
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import select, update

from app.core.config import settings

logger = logging.getLogger(__name__)

OPEN_PATH = "/api/v1/webhook/open"
# A transparent 1×1 GIF.
PIXEL_GIF = bytes.fromhex("47494638396101000100800000000000ffffff21f90401000000002c00000000010001000002024401003b")


def tracking_enabled(tenant) -> bool:
    """Open tracking is on unless the tenant switched it off on the Email reports page."""
    return bool(((tenant.tenant_profile or {}) if tenant else {}).get("track_email_opens", True))


def _sig(send_id: str) -> str:
    return hmac.new(settings.SECRET_KEY.encode(), f"open:{send_id}".encode(), hashlib.sha256).hexdigest()[:20]


def open_token(send_id: str) -> str:
    return f"{send_id}.{_sig(send_id)}"


def read_open_token(token: str) -> Optional[str]:
    send_id, _, sig = (token or "").removesuffix(".gif").rpartition(".")
    if send_id and hmac.compare_digest(sig, _sig(send_id)):
        return send_id
    return None


def pixel_url(send_id: str) -> str:
    return f"{settings.app_base_url_effective}{OPEN_PATH}/{open_token(send_id)}.gif"


def html_version(text: str, pixel: Optional[str]) -> str:
    """The plain-text body as minimal HTML (same words, same line breaks) plus the pixel."""
    body = html.escape(text or "").replace("\n", "<br>\n")
    img = f'<img src="{html.escape(pixel)}" width="1" height="1" alt="" style="display:block;border:0">' if pixel else ""
    return f'<!doctype html><html><body><div dir="auto" style="font-family:Arial,sans-serif;font-size:14px;line-height:1.6">{body}</div>{img}</body></html>'


async def start_send(db, lead, account, subject: str, source: str, track: bool):
    """Create the EmailSend row before sending (its id goes into the pixel)."""
    from app.models.models import EmailSend
    send = EmailSend(tenant_id=lead.tenant_id, lead_id=lead.id, account_id=getattr(account, "id", None),
                     to_email=lead.email, subject=(subject or "")[:500], source=source, tracked=track,
                     sent_at=datetime.utcnow())
    db.add(send)
    await db.flush()
    return send


async def record_open(db, send_id: str) -> None:
    from app.models.models import EmailSend
    send = (await db.execute(select(EmailSend).where(EmailSend.id == send_id))).scalar_one_or_none()
    if not send:
        return
    send.open_count = (send.open_count or 0) + 1
    if not send.opened_at:
        send.opened_at = datetime.utcnow()
    await db.commit()


async def mark_latest(db, field: str, *, tenant_id=None, lead_id=None, email=None) -> None:
    """Stamp `field` (bounced_at | replied_at | unsubscribed_at) on the most recent send to
    this lead / address that doesn't have it yet. Best-effort; never raises."""
    from app.models.models import EmailSend
    try:
        col = getattr(EmailSend, field)
        q = select(EmailSend.id).where(col.is_(None))
        if tenant_id:
            q = q.where(EmailSend.tenant_id == tenant_id)
        if lead_id:
            q = q.where(EmailSend.lead_id == lead_id)
        elif email:
            q = q.where(EmailSend.to_email.ilike(email))
        else:
            return
        sid = (await db.execute(q.order_by(EmailSend.sent_at.desc()).limit(1))).scalar_one_or_none()
        if sid:
            await db.execute(update(EmailSend).where(EmailSend.id == sid).values({field: datetime.utcnow()}))
    except Exception as e:
        logger.warning(f"email tracking ({field}) skipped: {e}")
