"""
Inbox sync service — pulls existing chats from Evolution API into Conversations table.
Called when a WA instance connects (connection.update event with state=open).
"""
import logging
from datetime import datetime, timezone
from typing import Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


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
                    cj = c.get("id") or c.get("remoteJid") or c.get("jid", "")
                    cn = c.get("pushName") or c.get("name") or c.get("verifiedName")
                    if cj and cn and not str(cn).replace("+", "").isdigit():
                        contacts_map[cj] = cn
        except Exception as e:
            logger.warning(f"findContacts {instance_name} failed: {e}")

    logger.info(f"Syncing {len(chats)} chats for instance {instance_name}")

    truncated = len(chats) > 100
    if truncated:
        logger.warning(f"sync_instance_chats: {len(chats)} chats found, capping at 100")
    chats = chats[:100]

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
            # A "name" that's just the phone number isn't a real name — leave it null so the
            # UI falls back to the number and a real pushName can fill it in later.
            if name and str(name).replace("+", "").replace(" ", "").isdigit():
                name = None
            last_msg = chat.get("lastMessage", {}) or {}
            last_content = (
                last_msg.get("conversation")
                or last_msg.get("extendedTextMessage", {}).get("text")
                if isinstance(last_msg, dict) else None
            )

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
                    unread_count=int(chat.get("unreadCount") or 0),
                )
                db.add(conv)
                await db.flush()
                synced += 1
            else:
                # Set a real name if we have one and the stored one is missing or just a number.
                current = conv.contact_name
                current_is_number = bool(current) and str(current).replace("+", "").replace(" ", "").isdigit()
                if name and (not current or current_is_number):
                    conv.contact_name = name
                if last_content:
                    conv.last_message = last_content
                conv.unread_count = int(chat.get("unreadCount") or 0)

        await db.commit()
        logger.info(f"Synced {synced} new conversations for {instance_name}")
    return synced


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
                contact_name=(push_name if (push_name and not from_me) else None),
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

        # Update last message
        conv.last_message = content[:200] if content else conv.last_message
        if not from_me:
            conv.unread_count = (conv.unread_count or 0) + 1
            # Backfill the contact's WhatsApp profile name once, if we don't have one yet.
            if push_name and not conv.contact_name:
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
