"""Email receiving — polls the IMAP mailbox for replies and threads them into the CRM
inbox next to WhatsApp.

Single shared mailbox (all tenants currently send from one account), so we match each
inbound message to a lead by the sender's address and thread it into that lead's tenant.
Unmatched mail (newsletters, cold noise) is left untouched in the mailbox.

Uses stdlib imaplib/email — the blocking IMAP work runs in a thread so it never stalls
the async event loop.
"""
import asyncio
import imaplib
import email
import logging
import re
from email.header import decode_header
from email.utils import parseaddr

from app.core.config import settings

logger = logging.getLogger(__name__)


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
                        body = re.sub(r"<[^>]+>", " ", html)
                        break
                    except Exception:
                        continue
    else:
        try:
            body = msg.get_payload(decode=True).decode(
                msg.get_content_charset() or "utf-8", errors="replace")
        except Exception:
            body = str(msg.get_payload())
    # Trim the most common quoted-reply markers so the thread shows the new text.
    body = re.split(r"\nOn .+wrote:|\n-{2,} ?Original Message|\n_{5,}", body)[0]
    return body.strip()


def _fetch_unseen():
    """Blocking IMAP fetch. Returns a list of dicts for UNSEEN messages, and marks them
    Seen so they aren't re-ingested."""
    host, port = settings.IMAP_HOST, settings.IMAP_PORT
    user = settings.SMTP_USER
    pwd = settings.SMTP_PASSWORD or settings.SMTP_APP_PASSWORD
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

    try:
        messages = await asyncio.to_thread(_fetch_unseen)
    except Exception as e:
        logger.warning(f"IMAP fetch failed: {e}")
        return {"polled": 0, "threaded": 0, "error": str(e)}

    if not messages:
        return {"polled": 0, "threaded": 0}

    from app.core.database import AsyncSessionLocal
    from app.models.models import (
        Lead, Conversation, ConversationStatus, Message, MessageDirection,
    )
    from sqlalchemy import select, and_

    threaded = 0
    async with AsyncSessionLocal() as db:
        for m in messages:
            addr = m["from_addr"]
            if not addr:
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
            db.add(Message(
                conversation_id=conv.id, wa_message_id=m["message_id"] or None,
                direction=MessageDirection.inbound, content=body[:5000],
                message_type="email",
            ))
            conv.last_message = (m["subject"] or body)[:200]
            conv.unread_count = (conv.unread_count or 0) + 1
            if not conv.lead_id:
                conv.lead_id = lead.id
            threaded += 1
        await db.commit()

    logger.info(f"poll_inbound_email: {len(messages)} fetched, {threaded} threaded")
    return {"polled": len(messages), "threaded": threaded}
