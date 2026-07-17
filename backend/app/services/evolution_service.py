"""
Evolution API Client — WhatsApp Integration
Connects to self-hosted Evolution API v2 at http://localhost:8080
"""
import logging
import httpx
from typing import Optional
from app.core.config import settings

logger = logging.getLogger(__name__)

BASE = settings.EVOLUTION_API_URL
HEADERS = {
    "apikey": settings.EVOLUTION_API_KEY,
    "Content-Type": "application/json",
}


class EvolutionService:
    """Async client wrapping Evolution API REST endpoints."""

    async def _get(self, path: str) -> dict:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f"{BASE}{path}", headers=HEADERS)
            r.raise_for_status()
            return r.json()

    async def _post(self, path: str, data: dict) -> dict:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(f"{BASE}{path}", json=data, headers=HEADERS)
            r.raise_for_status()
            return r.json()

    async def _delete(self, path: str) -> dict:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.delete(f"{BASE}{path}", headers=HEADERS)
            r.raise_for_status()
            return r.json()

    # ─── Instances ──────────────────────────────────────────

    async def get_instances(self) -> list:
        """Fetch all WhatsApp instances from Evolution API."""
        try:
            data = await self._get("/instance/fetchInstances")
            return data if isinstance(data, list) else []
        except Exception as e:
            raise RuntimeError(f"Failed to fetch instances from Evolution API: {e}")

    async def create_instance(self, name: str) -> dict:
        """Create a new WhatsApp instance in Evolution API."""
        try:
            return await self._post("/instance/create", {
                "instanceName": name,
                "qrcode": True,
                "integration": "WHATSAPP-BAILEYS",
            })
        except Exception as e:
            raise RuntimeError(f"Failed to create instance '{name}': {e}")

    async def get_qr(self, instance_name: str) -> Optional[str]:
        """Get QR from Redis (populated by webhook) or trigger generation."""
        try:
            from app.core.redis import get_redis
            r = await get_redis()
            cached = await r.get(f"qualifay:qr:{instance_name}")
            if cached:
                return cached.decode() if isinstance(cached, bytes) else cached
        except Exception as e:
            logger.warning(f"Redis QR fetch failed: {e}")
        try:
            data = await self._get(f"/instance/connect/{instance_name}")
            b64 = data.get("base64")
            if not b64 and isinstance(data.get("qrcode"), dict):
                b64 = data["qrcode"].get("base64")
            if b64 and len(str(b64)) > 100:
                return b64
        except Exception as e:
            logger.error(f"QR fetch failed: {e}")
        return None

    async def connect_status(self, instance_name: str) -> dict:
        """Get connection state of an instance."""
        try:
            return await self._get(f"/instance/connectionState/{instance_name}")
        except Exception as e:
            logger.error(f"Status check failed for '{instance_name}': {e}")
            return {"state": "close"}

    async def delete_instance(self, instance_name: str) -> dict:
        """Delete an instance from Evolution API."""
        try:
            return await self._delete(f"/instance/delete/{instance_name}")
        except Exception as e:
            raise RuntimeError(f"Failed to delete instance '{instance_name}': {e}")

    async def logout_instance(self, instance_name: str) -> dict:
        """Logout (disconnect) without deleting the instance."""
        try:
            return await self._delete(f"/instance/logout/{instance_name}")
        except Exception as e:
            raise RuntimeError(f"Failed to logout instance '{instance_name}': {e}")

    async def regenerate_qr(self, instance_name: str) -> Optional[str]:
        """Force a fresh QR for a closed/stale instance. A WhatsApp QR expires after a
        minute if unscanned and the session goes 'close' — then plain connect returns
        only {count}. Logging out resets it so connect re-opens and Evolution emits a new
        qrcode.updated (cached by the webhook). Returns a QR if immediately available,
        else None (the caller should poll /qr for the freshly-cached one)."""
        import asyncio
        try:
            st = await self.connect_status(instance_name)
            state = st.get("state") or (st.get("instance") or {}).get("state")
            if state not in ("open", "connected"):
                try:
                    await self.logout_instance(instance_name)
                except Exception:
                    pass
                await asyncio.sleep(2)
        except Exception:
            pass
        return await self.get_qr(instance_name)

    # ─── Messaging ──────────────────────────────────────────

    async def send_text(self, instance_name: str, jid: str, text: str) -> dict:
        """Send a text message to a WhatsApp JID or phone number."""
        try:
            return await self._post(f"/message/sendText/{instance_name}", {
                "number": jid,
                "text": text,
            })
        except Exception as e:
            raise RuntimeError(f"Failed to send text via '{instance_name}' to '{jid}': {e}")

    async def send_typing(self, instance_name: str, jid: str, duration: int = 3) -> None:
        """Show typing indicator for `duration` seconds. Non-critical — swallows errors."""
        try:
            await self._post(f"/message/sendPresence/{instance_name}", {
                "number": jid,
                "presence": "composing",
                "delay": duration * 1000,
            })
        except Exception as e:
            logger.debug(f"Typing indicator failed (non-critical): {e}")

    async def fetch_chats(self, instance_name: str) -> list:
        """Fetch all chats for an instance."""
        try:
            data = await self._post(f"/chat/findChats/{instance_name}", {})
            return data if isinstance(data, list) else []
        except Exception as e:
            raise RuntimeError(f"Failed to fetch chats for '{instance_name}': {e}")

    async def fetch_messages(self, instance_name: str, jid: str, limit: int = 50) -> list:
        """Fetch recent messages for a specific JID."""
        try:
            data = await self._post(f"/chat/findMessages/{instance_name}", {
                "where": {"key": {"remoteJid": jid}},
                "limit": limit,
            })
            if isinstance(data, dict):
                return data.get("messages", {}).get("records", [])
            return data if isinstance(data, list) else []
        except Exception as e:
            raise RuntimeError(f"Failed to fetch messages for '{jid}' on '{instance_name}': {e}")

    async def set_webhook(self, instance_name: str, url: str) -> dict:
        """Configure the webhook URL for an instance."""
        try:
            from app.core.config import settings
            return await self._post(f"/webhook/set/{instance_name}", {
                "webhook": {
                    "enabled": True,
                    "url": url,
                    "headers": {"apikey": settings.EVOLUTION_API_KEY},
                    "webhookByEvents": False,
                    "webhookBase64": False,
                    "events": [
                        "MESSAGES_UPSERT",
                        "MESSAGES_UPDATE",
                        "CONNECTION_UPDATE",
                        "QRCODE_UPDATED",
                        "SEND_MESSAGE",
                    ],
                }
            })
        except Exception as e:
            raise RuntimeError(f"Failed to set webhook for '{instance_name}': {e}")

    async def send_image(self, instance_name: str, jid: str, url: str, caption: str = "") -> dict:
        """Send an image message."""
        try:
            return await self._post(f"/message/sendMedia/{instance_name}", {
                "number": jid,
                "mediatype": "image",
                "media": url,
                "caption": caption,
            })
        except Exception as e:
            raise RuntimeError(f"Failed to send image via '{instance_name}': {e}")

    async def send_media(
        self,
        instance_name: str,
        jid: str,
        media_b64: str,
        mediatype: str,
        mimetype: str,
        filename: str,
        caption: str = "",
    ) -> dict:
        """Send an uploaded file (image/video/audio/document) as base64 media."""
        try:
            return await self._post(f"/message/sendMedia/{instance_name}", {
                "number": jid,
                "mediatype": mediatype,
                "mimetype": mimetype,
                "media": media_b64,
                "fileName": filename,
                "caption": caption,
            })
        except Exception as e:
            raise RuntimeError(f"Failed to send media via '{instance_name}': {e}")

    async def send_audio(self, instance_name: str, jid: str, audio_b64: str) -> dict:
        """Send a voice note (PTT). `audio_b64` must already be ogg/opus for WhatsApp
        to render it as a proper microphone bubble."""
        try:
            return await self._post(f"/message/sendWhatsAppAudio/{instance_name}", {
                "number": jid,
                "audio": audio_b64,
            })
        except Exception as e:
            raise RuntimeError(f"Failed to send audio via '{instance_name}': {e}")

    async def delete_message(self, instance_name: str, key: dict) -> dict:
        """Delete a message for everyone on WhatsApp (Evolution deleteMessageForEveryone).

        `key` = {id, remoteJid, fromMe, participant?}. Only works within WhatsApp's
        delete window and only for messages the instance is allowed to revoke.
        """
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.request(
                "DELETE",
                f"{BASE}/chat/deleteMessageForEveryone/{instance_name}",
                json=key,
                headers=HEADERS,
            )
            r.raise_for_status()
            return r.json()

    async def check_number(self, instance_name: str, phone: str) -> bool:
        """Check if a phone number is on WhatsApp."""
        try:
            data = await self._post(f"/chat/whatsappNumbers/{instance_name}", {
                "numbers": [phone]
            })
            if isinstance(data, list) and data:
                return data[0].get("exists", False)
            return False
        except Exception:
            return False

    async def check_numbers(self, instance_name: str, phones: list) -> dict:
        """Check many numbers in one call. Returns {input_number: bool_on_whatsapp}.

        Evolution's whatsappNumbers accepts a list and returns one row per number;
        we match results back to the numbers we sent (comparing digit-only forms,
        since Evolution echoes the jid/number in varying formats).
        """
        if not phones:
            return {}
        try:
            data = await self._post(f"/chat/whatsappNumbers/{instance_name}", {"numbers": phones})
        except Exception as e:
            raise RuntimeError(f"whatsappNumbers check failed on '{instance_name}': {e}")
        if not isinstance(data, list):
            return {}

        def digits(s):
            return "".join(ch for ch in str(s or "") if ch.isdigit())

        by_digits = {}
        for row in data:
            num = row.get("number") or row.get("jid") or ""
            by_digits[digits(num)] = bool(row.get("exists", False))
        # Map back to the exact strings the caller passed in.
        return {p: by_digits.get(digits(p), False) for p in phones}

    async def mark_read(self, instance_name: str, keys: list) -> dict:
        """Mark messages as read."""
        try:
            return await self._post(f"/message/markMessageAsRead/{instance_name}", {
                "read_messages": keys
            })
        except Exception as e:
            logger.debug(f"Mark read failed (non-critical): {e}")
            return {}


# Singleton
evolution_service = EvolutionService()
