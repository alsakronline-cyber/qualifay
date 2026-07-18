"""Email receiving — polls the IMAP mailbox for replies and threads them into the CRM
inbox next to WhatsApp.

Single shared mailbox (all tenants currently send from one account), so we match each
inbound message to a lead by the sender's address and thread it into that lead's tenant.
Unmatched mail (newsletters, cold noise) is left untouched in the mailbox.

Uses stdlib imaplib/email — the blocking IMAP work runs in a thread so it never stalls
the async event loop.
"""
import asyncio
import html as _htmllib
import imaplib
import email
import logging
import re
import uuid
from email.header import decode_header
from email.utils import parseaddr

from app.core.config import settings

logger = logging.getLogger(__name__)


def _html_to_text(html: str) -> str:
    """Turn HTML email into readable plain text — block elements become line breaks so
    the message keeps its structure instead of collapsing into one run-on paragraph."""
    if not html:
        return ""
    html = re.sub(r"(?is)<(script|style|head)[^>]*>.*?</\1>", " ", html)
    html = re.sub(r"(?i)<\s*br\s*/?>", "\n", html)
    html = re.sub(r"(?i)</\s*(p|div|tr|li|h[1-6]|table|blockquote)\s*>", "\n", html)
    html = re.sub(r"(?i)<\s*(p|div|tr|li|h[1-6]|blockquote)[^>]*>", "\n", html)
    html = re.sub(r"(?i)</\s*td\s*>", "  ", html)
    html = re.sub(r"<[^>]+>", "", html)
    html = _htmllib.unescape(html)
    lines = [ln.rstrip() for ln in html.split("\n")]
    text = "\n".join(lines)
    text = re.sub(r"[ \t]{3,}", "  ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_attachments(msg) -> list:
    """Pull file attachments from an email as [{filename, content_type, data, size}]."""
    atts = []
    if not msg.is_multipart():
        return atts
    for part in msg.walk():
        if part.get_content_maintype() == "multipart":
            continue
        disp = str(part.get("Content-Disposition") or "")
        fn = part.get_filename()
        if not fn and "attachment" not in disp.lower():
            continue
        try:
            data = part.get_payload(decode=True)
        except Exception:
            data = None
        if not data:
            continue
        atts.append({
            "filename": _decode(fn) if fn else "attachment",
            "content_type": part.get_content_type() or "application/octet-stream",
            "data": data,
            "size": len(data),
        })
    return atts


def _store_attachments(atts: list) -> list:
    """Upload attachment bytes to object storage; return metadata (no data) for the DB."""
    from app.services.storage_service import upload_attachment
    meta = []
    for a in atts:
        if not a.get("data"):
            continue
        key = f"{uuid.uuid4().hex}_{re.sub(r'[^A-Za-z0-9._-]', '_', a['filename'])[:80]}"
        if upload_attachment(key, a["data"], a["content_type"]):
            meta.append({"filename": a["filename"], "key": key,
                         "content_type": a["content_type"], "size": a["size"]})
    return meta


def _decode(s) -> str:
    if not s:
        return ""
    parts = decode_header(s)
    out = []
    for text, enc in parts:
        if isinstance(text, bytes):
            try:
                out.append(text.decode(enc or "utf-8", errors="replace"))
            except Exception:
                out.append(text.decode("utf-8", errors="replace"))
        else:
            out.append(text)
    return "".join(out)


def _plain_body(msg) -> str:
    """Best-effort plain-text body; strips a quoted reply trailer if present."""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition") or "")
            if ctype == "text/plain" and "attachment" not in disp:
                try:
                    body = part.get_payload(decode=True).decode(
                        part.get_content_charset() or "utf-8", errors="replace")
                    break
                except Exception:
                    continue
        if not body:
            for part in msg.walk():
                if part.get_content_type() == "text/html":
                    try:
                        html = part.get_payload(decode=True).decode(
                            part.get_content_charset() or "utf-8", errors="replace")
                        body = _html_to_text(html)
                        break
                    except Exception:
                        continue
    else:
        try:
            raw = msg.get_payload(decode=True).decode(
                msg.get_content_charset() or "utf-8", errors="replace")
            body = _html_to_text(raw) if msg.get_content_type() == "text/html" else raw
        except Exception:
            body = str(msg.get_payload())
    # Trim the most common quoted-reply markers so the thread shows the new text.
    body = re.split(r"\nOn .+wrote:|\n-{2,} ?Original Message|\n_{5,}", body)[0]
    return body.strip()


def _fetch_unseen(host=None, port=None, user=None, pwd=None):
    """Blocking IMAP fetch for one mailbox. Returns a list of dicts for UNSEEN messages,
    and marks them Seen so they aren't re-ingested. Defaults to the system mailbox."""
    host = host or settings.IMAP_HOST
    port = port or settings.IMAP_PORT
    user = user or settings.SMTP_USER
    pwd = pwd or settings.SMTP_PASSWORD or settings.SMTP_APP_PASSWORD
    if not (host and user and pwd):
        return []

    out = []
    imap = imaplib.IMAP4_SSL(host, port)
    try:
        imap.login(user, pwd)
        imap.select("INBOX")
        typ, data = imap.search(None, "UNSEEN")
        if typ != "OK":
            return []
        ids = data[0].split()
        for mid in ids[-100:]:  # cap per run
            typ, msg_data = imap.fetch(mid, "(RFC822)")
            if typ != "OK" or not msg_data or not msg_data[0]:
                continue
            msg = email.message_from_bytes(msg_data[0][1])
            from_name, from_addr = parseaddr(msg.get("From", ""))
            out.append({
                "from_addr": (from_addr or "").lower().strip(),
                "from_name": _decode(from_name),
                "subject": _decode(msg.get("Subject", "")),
                "message_id": (msg.get("Message-ID") or "").strip(),
                "body": _plain_body(msg),
                "attachments": _extract_attachments(msg),
            })
            imap.store(mid, "+FLAGS", "\\Seen")
    finally:
        try:
            imap.close()
        except Exception:
            pass
        imap.logout()
    return out


async def poll_inbound_email() -> dict:
    """Fetch new replies and thread each into the matching lead's email conversation."""
    if not settings.IMAP_POLL_ENABLED:
        return {"polled": 0, "threaded": 0, "reason": "disabled"}

    # Build the list of mailboxes to poll: the system account + every tenant EmailAccount
    # that has an IMAP host configured (so replies to any sending identity are captured).
    from app.core.database import AsyncSessionLocal
    from app.core.crypto import decrypt

    mailboxes = [(None, None, None, None)]  # (None*) => system defaults
    try:
        from app.models.models import EmailAccount
        from sqlalchemy import select
        async with AsyncSessionLocal() as db:
            accts = (await db.execute(
                select(EmailAccount).where(EmailAccount.imap_host.isnot(None))
            )).scalars().all()
        for a in accts:
            mailboxes.append((a.imap_host, a.imap_port or 993, a.smtp_user, decrypt(a.smtp_password_enc)))
    except Exception as e:
        logger.debug(f"listing email accounts for poll failed: {e}")

    messages = []
    for host, port, user, pwd in mailboxes:
        try:
            messages.extend(await asyncio.to_thread(_fetch_unseen, host, port, user, pwd))
        except Exception as e:
            logger.warning(f"IMAP fetch failed ({host or 'system'}): {e}")

    if not messages:
        return {"polled": 0, "threaded": 0}

    from app.core.database import AsyncSessionLocal
    from app.models.models import (
        Lead, Conversation, ConversationStatus, Message, MessageDirection,
    )
    from sqlalchemy import select, and_

    threaded = 0
    bounced = 0
    async with AsyncSessionLocal() as db:
        for m in messages:
            addr = m["from_addr"]
            if not addr:
                continue

            # Bounce / delivery-failure notice? Suppress the dead address and count it,
            # so the warmup cap pauses sending if bounces spike.
            if _is_bounce(addr, m["subject"]):
                bounced += await _handle_bounce(db, m)
                continue

            # Match to a lead by email (most recent wins if several tenants share it).
            lead = (await db.execute(
                select(Lead).where(Lead.email.ilike(addr)).order_by(Lead.created_at.desc())
            )).scalars().first()
            if not lead:
                continue  # unknown sender — leave it in the mailbox

            conv = (await db.execute(
                select(Conversation).where(and_(
                    Conversation.tenant_id == lead.tenant_id,
                    Conversation.channel == "email",
                    Conversation.wa_jid == addr,
                ))
            )).scalar_one_or_none()
            if not conv:
                conv = Conversation(
                    tenant_id=lead.tenant_id, lead_id=lead.id,
                    instance_name="email", wa_jid=addr, channel="email",
                    contact_name=m["from_name"] or lead.name or lead.company,
                    status=ConversationStatus.open, ai_enabled=False,
                )
                db.add(conv)
                await db.flush()

            # Dedupe by Message-ID.
            if m["message_id"]:
                dup = (await db.execute(
                    select(Message).where(Message.wa_message_id == m["message_id"])
                )).scalar_one_or_none()
                if dup:
                    continue

            body = m["body"] or m["subject"] or "(رسالة فارغة)"
            att_meta = _store_attachments(m.get("attachments") or [])
            db.add(Message(
                conversation_id=conv.id, wa_message_id=m["message_id"] or None,
                direction=MessageDirection.inbound, content=body[:5000],
                message_type="email", attachments=att_meta or None,
            ))
            conv.last_message = (m["subject"] or body)[:200]
            conv.unread_count = (conv.unread_count or 0) + 1
            if not conv.lead_id:
                conv.lead_id = lead.id
            # A reply stops the lead's active cadences (no more follow-ups).
            try:
                from app.workers.sequence_tasks import stop_enrollments_for_lead
                await stop_enrollments_for_lead(db, lead.id)
            except Exception:
                pass
            try:
                from app.services.ab_service import mark_replied
                await mark_replied(db, lead.id)
            except Exception:
                pass
            threaded += 1
        await db.commit()

    logger.info(f"poll_inbound_email: {len(messages)} fetched, {threaded} threaded, {bounced} bounced")
    return {"polled": len(messages), "threaded": threaded, "bounced": bounced}


_BOUNCE_SENDERS = ("mailer-daemon", "postmaster", "mail delivery")
_BOUNCE_SUBJECT = re.compile(
    r"delivery status|undeliver|delivery has failed|returned mail|mail delivery failed|failure notice",
    re.I,
)
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")


def _is_bounce(from_addr: str, subject: str) -> bool:
    fa = (from_addr or "").lower()
    if any(s in fa for s in _BOUNCE_SENDERS):
        return True
    return bool(_BOUNCE_SUBJECT.search(subject or ""))


async def _handle_bounce(db, m: dict) -> int:
    """Find the failed recipient in the bounce body, suppress it on the matching lead,
    and record the bounce against that lead's tenant. Returns 1 if handled, else 0."""
    from app.models.models import Lead
    from app.services.warmup_service import warmup_service
    from sqlalchemy import select

    # Candidate addresses in the bounce body, minus the bounce-sender itself.
    addrs = [a.lower() for a in _EMAIL_RE.findall(m.get("body", ""))]
    addrs = [a for a in addrs if not any(s in a for s in _BOUNCE_SENDERS)]
    if not addrs:
        return 0

    handled = 0
    for a in dict.fromkeys(addrs):  # de-dupe, keep order
        leads = (await db.execute(
            select(Lead).where(Lead.email.ilike(a))
        )).scalars().all()
        for lead in leads:
            lead.raw_data = {**(lead.raw_data or {}), "bounced_email": lead.email}
            lead.email = None  # stop re-emailing a dead address (kept in raw_data)
            await warmup_service.record_email_bounce(str(lead.tenant_id))
            handled = 1
    if handled:
        await db.commit()
    return handled
