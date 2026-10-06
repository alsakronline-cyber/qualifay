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


def resolve_chat_jid(key: dict):
    """The phone JID a message belongs to.

    WhatsApp now addresses most chats by LID ("<id>@lid") instead of the phone JID. Baileys
    carries the real phone in `remoteJidAlt`, so prefer that; fall back to remoteJid. Returns
    None for anything that isn't a 1:1 chat (groups, channels, status broadcasts).
    """
    raw = str((key or {}).get("remoteJid") or "")
    alt = str((key or {}).get("remoteJidAlt") or "")
    jid = alt if alt.endswith("@s.whatsapp.net") else raw
    if not jid:
        return None
    if jid.endswith("@g.us") or "newsletter" in jid or jid.startswith("status@"):
        return None
    if not jid.split("@")[0].isdigit():
        return None
    return jid


async def _fetch_all_messages(client, base_url, headers, instance_name, max_pages=1000):
    """Page through EVERY message Evolution holds for this instance.

    NOTE: Evolution's /chat/findMessages ignores a `where: {remoteJid: ...}` filter — it
    returns the whole instance stream regardless (verified against this deployment). So we
    fetch once and route each message by its own key instead of querying per chat; querying
    per chat would file the entire stream under whichever chat was asked for.
    """
    page = 1
    while page <= max_pages:
        try:
            r = await client.post(
                f"{base_url}/chat/findMessages/{instance_name}",
                headers=headers, json={"page": page},
            )
            if r.status_code != 200:
                logger.warning(f"findMessages {instance_name} page {page}: HTTP {r.status_code}")
                break
            block = (r.json() or {}).get("messages") or {}
            recs = block.get("records") or []
            if not recs:
                break
            for rec in recs:
                yield rec
            if page >= int(block.get("pages") or 1):
                break
            page += 1
        except Exception as e:
            logger.warning(f"findMessages {instance_name} page {page}: {e}")
            break


async def sync_instance_history(instance_name: str, tenant_id: str, wa_instance_id: str,
                                repair: bool = True):
    """Import the FULL message history for an instance.

    Streams every message Evolution holds and routes each one to its own chat using the
    message's key (resolve_chat_jid), because Evolution's per-chat filter is not honoured.
    Creates conversations on the fly — including LID-addressed chats, which are now the
    majority. Safe to re-run: deduped by wa_message_id.

    repair=True first deletes messages that a previous (buggy) per-chat import filed under
    the wrong conversation.
    """
    from app.core.database import AsyncSessionLocal
    from app.models.models import (
        Conversation, ConversationStatus, Message, MessageDirection,
    )
    from sqlalchemy import select, delete

    base_url = settings.EVOLUTION_API_URL
    headers = {"apikey": settings.EVOLUTION_API_KEY, "Content-Type": "application/json"}

    # Contact names, keyed by BOTH the lid and the phone jid.
    names: dict = {}
    try:
        async with httpx.AsyncClient(timeout=45) as client:
            r = await client.post(f"{base_url}/chat/findChats/{instance_name}",
                                  headers=headers, json={})
            chats = r.json() if r.status_code == 200 else []
            if isinstance(chats, dict):
                chats = chats.get("chats", [])
            for ch in chats or []:
                nm = ch.get("pushName")
                if not _is_real_name(nm):
                    continue
                lm_key = ((ch.get("lastMessage") or {}).get("key")) or {}
                for k in (ch.get("remoteJid"), lm_key.get("remoteJid"), lm_key.get("remoteJidAlt")):
                    if k:
                        names[str(k)] = nm
    except Exception as e:
        logger.warning(f"findChats names {instance_name}: {e}")

    async with AsyncSessionLocal() as db:
        convs = {c.wa_jid: c for c in (await db.execute(select(Conversation).where(
            Conversation.tenant_id == tenant_id,
            Conversation.instance_name == instance_name,
        ))).scalars().all()}

        # Re-link conversations orphaned from an earlier incarnation of this number.
        relinked = 0
        for c in convs.values():
            if c.wa_instance_id != wa_instance_id:
                c.wa_instance_id = wa_instance_id
                relinked += 1

        known = set()
        if convs:
            known = {r for (r,) in (await db.execute(
                select(Message.wa_message_id).where(
                    Message.conversation_id.in_([c.id for c in convs.values()]))
            )).all() if r}

        repaired = 0
        imported = 0
        seen_jids = set()

        async with httpx.AsyncClient(timeout=60) as client:
            # Pass 1 (repair): find messages filed under the wrong conversation and drop them.
            if repair and convs:
                by_id = {c.id: c for c in convs.values()}
                true_jid = {}
                async for rec in _fetch_all_messages(client, base_url, headers, instance_name):
                    wid = (rec.get("key") or {}).get("id")
                    j = resolve_chat_jid(rec.get("key") or {})
                    if wid and j:
                        true_jid[wid] = j
                bad = []
                for m in (await db.execute(select(Message).where(
                        Message.conversation_id.in_(list(by_id.keys()))))).scalars().all():
                    t = true_jid.get(m.wa_message_id)
                    if t and by_id.get(m.conversation_id) and by_id[m.conversation_id].wa_jid != t:
                        bad.append(m.id)
                if bad:
                    for i in range(0, len(bad), 500):
                        await db.execute(delete(Message).where(Message.id.in_(bad[i:i + 500])))
                    await db.commit()
                    repaired = len(bad)
                    known -= {k for k, v in true_jid.items() if k in known}
                    logger.warning(f"history sync {instance_name}: removed {repaired} mis-filed messages")

            # Pass 2: import, routing each message by its own key.
            async for rec in _fetch_all_messages(client, base_url, headers, instance_name):
                key = rec.get("key") or {}
                wid = key.get("id")
                jid = resolve_chat_jid(key)
                if not wid or not jid or wid in known:
                    continue
                content, mtype = _extract_content(rec.get("message") or {})
                if content is None:
                    continue
                ts = rec.get("messageTimestamp")
                try:
                    created = datetime.utcfromtimestamp(int(ts)) if ts else datetime.utcnow()
                except (ValueError, TypeError, OSError):
                    created = datetime.utcnow()

                conv = convs.get(jid)
                if conv is None:
                    nm = names.get(jid) or names.get(str(key.get("remoteJid")))
                    if not _is_real_name(nm):
                        nm = rec.get("pushName") if not key.get("fromMe") else None
                    conv = Conversation(
                        tenant_id=tenant_id, wa_instance_id=wa_instance_id,
                        instance_name=instance_name, wa_jid=jid,
                        contact_name=nm if _is_real_name(nm) else None,
                        status=ConversationStatus.open, ai_enabled=False,
                        last_message=content[:200], last_message_at=created,
                    )
                    db.add(conv)
                    await db.flush()
                    convs[jid] = conv
                seen_jids.add(jid)

                db.add(Message(
                    conversation_id=conv.id, wa_message_id=wid,
                    direction=MessageDirection.outbound if key.get("fromMe") else MessageDirection.inbound,
                    content=content, message_type=mtype, created_at=created,
                ))
                known.add(wid)
                imported += 1
                if conv.last_message_at is None or created > conv.last_message_at:
                    conv.last_message = content[:200]
                    conv.last_message_at = created
                if imported % 500 == 0:
                    await db.commit()
        await db.commit()

    logger.info(f"history sync {instance_name}: imported {imported} messages across "
                f"{len(seen_jids)} chats (repaired {repaired}, relinked {relinked})")
    return {"chats": len(seen_jids), "messages_imported": imported,
            "mis_filed_removed": repaired, "relinked": relinked}


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
            ).order_by(Conversation.last_message_at.desc().nullslast())
        )
        # .first(): duplicates exist (23 chats in prod), and one-or-none raised — which meant
        # an incoming customer reply was never saved to the inbox.
        conv = conv_result.scalars().first()
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
                    ).order_by(Conversation.last_message_at.desc().nullslast())
                )
                conv = conv_result2.scalars().first()

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
