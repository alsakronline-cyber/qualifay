"""
Inbox sync service — pulls existing chats from Evolution API into Conversations table.
Called when a WA instance connects (connection.update event with state=open).
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# WhatsApp/Evolution sometimes returns a self-reference ("You" in the account's locale)
# as a contact's pushName. That's not the contact's name — reject it.
_SELF_LABELS = {"você", "voce", "you", "أنت", "انت", "me", "myself", "tu", "yourself"}


def _is_real_name(name) -> bool:
    if not name:
        return False
    s = str(name).strip()
    if not s or s.lower() in _SELF_LABELS:
        return False
    # A bare phone number isn't a name.
    if s.replace("+", "").replace(" ", "").isdigit():
        return False
    return True


async def sync_instance_chats(instance_name: str, tenant_id: str, wa_instance_id: str):
    """
    Fetch all existing chats from Evolution API for this instance
    and upsert them into the conversations table.
    """
    from app.core.database import AsyncSessionLocal
    from app.models.models import Conversation, ConversationStatus, Message, MessageDirection
    from sqlalchemy import select

    base_url = settings.EVOLUTION_API_URL
    api_key = settings.EVOLUTION_API_KEY
    headers = {"apikey": api_key, "Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=30) as client:
        # 1. Fetch chats list
        try:
            r = await client.post(
                f"{base_url}/chat/findChats/{instance_name}",
                headers=headers,
                json={},
            )
            if r.status_code != 200:
                logger.warning(f"fetchChats {instance_name}: {r.status_code} {r.text[:200]}")
                return
            chats = r.json()
            if not isinstance(chats, list):
                chats = chats.get("chats", []) if isinstance(chats, dict) else []
        except Exception as e:
            logger.error(f"sync_instance_chats fetchChats error: {e}")
            return

        # Also fetch the contact book — this is where WhatsApp profile names (pushName)
        # reliably live, whereas findChats often returns only the number.
        contacts_map: dict = {}
        try:
            rc = await client.post(
                f"{base_url}/chat/findContacts/{instance_name}", headers=headers, json={},
            )
            if rc.status_code == 200:
                contacts = rc.json()
                if isinstance(contacts, dict):
                    contacts = contacts.get("contacts", [])
                for c in (contacts or []):
                    # The matching key is remoteJid (the WhatsApp JID); `id` is Evolution's
                    # own internal id and never matches a conversation.
                    cj = c.get("remoteJid") or c.get("jid") or ""
                    cn = c.get("name") or c.get("pushName") or c.get("verifiedName")
                    if cj and "@s.whatsapp.net" in cj and _is_real_name(cn):
                        contacts_map[cj] = cn
        except Exception as e:
            logger.warning(f"findContacts {instance_name} failed: {e}")

    logger.info(f"Syncing {len(chats)} chats for instance {instance_name}")

    # No cap: import every chat the number has. (Previously capped at 100, which silently
    # dropped most of the history on busy numbers.)
    if len(chats) > 500:
        logger.info(f"sync_instance_chats: {len(chats)} chats — large sync, this may take a while")

    async with AsyncSessionLocal() as db:
        # Batch-load all existing conversations for this instance (avoids N+1)
        existing_result = await db.execute(
            select(Conversation).where(
                Conversation.tenant_id == tenant_id,
                Conversation.instance_name == instance_name,
            )
        )
        conv_map = {c.wa_jid: c for c in existing_result.scalars()}

        synced = 0
        for chat in chats:
            jid = chat.get("id") or chat.get("remoteJid") or chat.get("jid", "")
            if not jid or jid.endswith("@g.us") or jid.endswith("@lid") or jid.startswith("cmr") or "newsletter" in jid or not jid.split("@")[0].isdigit():  # skip groups, device IDs, channels, and non-numeric JIDs
                continue

            conv = conv_map.get(jid)

            last_msg_obj = chat.get("lastMessage") or {}
            name = (
                contacts_map.get(jid)
                or chat.get("name")
                or chat.get("pushName")
                or chat.get("verifiedName")
                or (last_msg_obj.get("pushName") if isinstance(last_msg_obj, dict) else None)
                or None
            )
            # Reject numbers and self-labels ("Você"/"You") so the UI falls back to the
            # number and a real pushName can fill it in later.
            if not _is_real_name(name):
                name = None
            last_msg = chat.get("lastMessage", {}) or {}
            last_content = (
                last_msg.get("conversation")
                or last_msg.get("extendedTextMessage", {}).get("text")
                if isinstance(last_msg, dict) else None
            )
            # Real last-activity time from WhatsApp (unix seconds) so the inbox sorts by
            # true recency, not when this sync ran.
            last_at = None
            raw_ts = (last_msg.get("messageTimestamp") if isinstance(last_msg, dict) else None) \
                or chat.get("conversationTimestamp") or chat.get("t")
            if raw_ts:
                try:
                    last_at = datetime.utcfromtimestamp(int(raw_ts))
                except (ValueError, TypeError, OSError):
                    last_at = None

            if not conv:
                conv = Conversation(
                    tenant_id=tenant_id,
                    wa_instance_id=wa_instance_id,
                    instance_name=instance_name,
                    wa_jid=jid,
                    contact_name=name,
                    status=ConversationStatus.open,
                    ai_enabled=False,
                    last_message=last_content,
                    last_message_at=last_at,
                    unread_count=int(chat.get("unreadCount") or 0),
                )
                db.add(conv)
                await db.flush()
                synced += 1
            else:
                # Set a real name if we have one and the stored one is missing or not real.
                if name and not _is_real_name(conv.contact_name):
                    conv.contact_name = name
                if last_content:
                    conv.last_message = last_content
                if last_at and (not conv.last_message_at or last_at > conv.last_message_at):
                    conv.last_message_at = last_at
                conv.unread_count = int(chat.get("unreadCount") or 0)

        # Backfill names for EVERY existing conversation from the contact book — not just
        # the ones that appeared in the (capped) chats list. This is what actually names
        # older conversations whose contact has a WhatsApp profile name.
        named = 0
        for conv in conv_map.values():
            if not _is_real_name(conv.contact_name):
                nm = contacts_map.get(conv.wa_jid)
                if nm:
                    conv.contact_name = nm
                    named += 1

        await db.commit()
        logger.info(f"Synced {synced} new conversations for {instance_name}, named {named} from contacts")
    return synced


def _extract_content(m: dict):
    """Pull display text + type out of a Baileys message payload."""
    if not isinstance(m, dict):
        return None, "text"
    if m.get("conversation"):
        return m["conversation"], "text"
    ext = m.get("extendedTextMessage")
    if isinstance(ext, dict) and ext.get("text"):
        return ext["text"], "text"
    for key, kind in (("imageMessage", "image"), ("videoMessage", "video"),
                      ("audioMessage", "audio"), ("documentMessage", "document"),
                      ("stickerMessage", "sticker"), ("locationMessage", "location")):
        blk = m.get(key)
        if blk:
            cap = blk.get("caption") if isinstance(blk, dict) else None
            return (cap or f"[{kind}]"), kind
    return None, "text"


async def _fetch_chat_messages(client, base_url, headers, instance_name, jid, max_pages=40):
    """Page through every message Evolution has stored for one chat."""
    records, page = [], 1
    while page <= max_pages:
        try:
            r = await client.post(
                f"{base_url}/chat/findMessages/{instance_name}",
                headers=headers, json={"where": {"remoteJid": jid}, "page": page},
            )
            if r.status_code != 200:
                break
            block = (r.json() or {}).get("messages") or {}
            recs = block.get("records") or []
            records.extend(recs)
            if not recs or page >= int(block.get("pages") or 1):
                break
            page += 1
        except Exception as e:
            logger.warning(f"findMessages {instance_name} {jid} page {page}: {e}")
            break
    return records


async def sync_instance_history(instance_name: str, tenant_id: str, wa_instance_id: str):
    """Import the FULL message history for an instance — every chat, every message Evolution
    holds. sync_instance_chats() only creates conversation stubs (contact + last-message
    preview); this is what actually fills the threads. Safe to re-run: messages are deduped
    by wa_message_id. Also re-links conversations left pointing at a previous instance id
    (happens when a number is deleted and re-paired)."""
    from app.core.database import AsyncSessionLocal
    from app.models.models import Conversation, Message, MessageDirection
    from sqlalchemy import select

    # 1) Make sure the conversation rows exist / are up to date.
    await sync_instance_chats(instance_name, tenant_id, wa_instance_id)

    base_url = settings.EVOLUTION_API_URL
    headers = {"apikey": settings.EVOLUTION_API_KEY, "Content-Type": "application/json"}

    async with AsyncSessionLocal() as db:
        convs = (await db.execute(select(Conversation).where(
            Conversation.tenant_id == tenant_id,
            Conversation.instance_name == instance_name,
        ))).scalars().all()

        # Re-link conversations orphaned from an earlier incarnation of this number.
        relinked = 0
        for c in convs:
            if c.wa_instance_id != wa_instance_id:
                c.wa_instance_id = wa_instance_id
                relinked += 1
        if relinked:
            await db.commit()

        # Existing message ids so re-runs don't duplicate.
        conv_ids = [c.id for c in convs]
        known = set()
        if conv_ids:
            known = {
                r for (r,) in (await db.execute(
                    select(Message.wa_message_id).where(Message.conversation_id.in_(conv_ids))
                )).all() if r
            }

        imported, scanned = 0, 0
        async with httpx.AsyncClient(timeout=45) as client:
            for c in convs:
                recs = await _fetch_chat_messages(client, base_url, headers, instance_name, c.wa_jid)
                scanned += 1
                newest = c.last_message_at
                for rec in recs:
                    key = rec.get("key") or {}
                    wid = key.get("id")
                    if not wid or wid in known:
                        continue
                    content, mtype = _extract_content(rec.get("message") or {})
                    if content is None:
                        continue
                    ts = rec.get("messageTimestamp")
                    try:
                        created = datetime.utcfromtimestamp(int(ts)) if ts else datetime.utcnow()
                    except (ValueError, TypeError, OSError):
                        created = datetime.utcnow()
                    db.add(Message(
                        conversation_id=c.id,
                        wa_message_id=wid,
                        direction=MessageDirection.outbound if key.get("fromMe") else MessageDirection.inbound,
                        content=content,
                        message_type=mtype,
                        created_at=created,
                    ))
                    known.add(wid)
                    imported += 1
                    if newest is None or created > newest:
                        newest = created
                        c.last_message = content[:200]
                        c.last_message_at = created
                if imported and imported % 200 < 50:
                    await db.commit()   # periodic flush so progress survives a failure
        await db.commit()

    logger.info(f"history sync {instance_name}: {imported} messages across {scanned} chats "
                f"(relinked {relinked})")
    return {"chats": scanned, "messages_imported": imported, "relinked": relinked}


async def upsert_inbound_message(
    instance_name: str,
    tenant_id: str,
    wa_jid: str,
    content: str,
    wa_message_id: Optional[str],
    from_me: bool,
    timestamp: Optional[int] = None,
    message_type: str = "text",
    push_name: Optional[str] = None,
):
    """
    Called by the webhook handler for every inbound/outbound message.
    Creates or updates the conversation and appends the message.
    """
    from app.core.database import AsyncSessionLocal
    from app.models.models import (
        Conversation, ConversationStatus, Message, MessageDirection, WaInstance
    )
    from sqlalchemy import select
    from sqlalchemy.exc import IntegrityError

    async with AsyncSessionLocal() as db:
        # Resolve instance
        inst_result = await db.execute(
            select(WaInstance).where(
                WaInstance.tenant_id == tenant_id,
                WaInstance.instance_name == instance_name,
            )
        )
        wa_inst = inst_result.scalar_one_or_none()
        wa_instance_id = wa_inst.id if wa_inst else None

        # Upsert conversation
        conv_result = await db.execute(
            select(Conversation).where(
                Conversation.tenant_id == tenant_id,
                Conversation.instance_name == instance_name,
                Conversation.wa_jid == wa_jid,
            )
        )
        conv = conv_result.scalar_one_or_none()
        if not conv:
            conv = Conversation(
                tenant_id=tenant_id,
                wa_instance_id=wa_instance_id,
                instance_name=instance_name,
                wa_jid=wa_jid,
                # The sender's WhatsApp profile name (pushName), only meaningful inbound.
                contact_name=(push_name if (not from_me and _is_real_name(push_name)) else None),
                status=ConversationStatus.open,
                ai_enabled=False,
            )
            db.add(conv)
            try:
                await db.flush()
            except IntegrityError:
                await db.rollback()
                # Another concurrent request already created this conversation — re-fetch
                conv_result2 = await db.execute(
                    select(Conversation).where(
                        Conversation.tenant_id == tenant_id,
                        Conversation.instance_name == instance_name,
                        Conversation.wa_jid == wa_jid,
                    )
                )
                conv = conv_result2.scalar_one()

        # Update last message + its real time (for recency sorting in the inbox).
        conv.last_message = content[:200] if content else conv.last_message
        _msg_at = None
        if timestamp:
            try:
                _msg_at = datetime.utcfromtimestamp(int(timestamp))
            except (ValueError, TypeError, OSError):
                _msg_at = None
        if _msg_at is None:
            _msg_at = datetime.utcnow()
        if not conv.last_message_at or _msg_at >= conv.last_message_at:
            conv.last_message_at = _msg_at
        if not from_me:
            conv.unread_count = (conv.unread_count or 0) + 1
            # Backfill the contact's WhatsApp profile name once, if we don't have a real one.
            if _is_real_name(push_name) and not _is_real_name(conv.contact_name):
                conv.contact_name = push_name

        # Append message if not duplicate
        direction = MessageDirection.outbound if from_me else MessageDirection.inbound
        if wa_message_id:
            dup = await db.execute(
                select(Message).where(Message.wa_message_id == wa_message_id)
            )
            if dup.scalar_one_or_none():
                await db.commit()
                return conv.id

        msg = Message(
            conversation_id=conv.id,
            wa_message_id=wa_message_id,
            direction=direction,
            content=content,
            message_type=message_type,
            created_at=(
                datetime.utcfromtimestamp(timestamp)
                if timestamp else datetime.now(timezone.utc)
            ),
        )
        db.add(msg)
        await db.commit()
        return conv.id
