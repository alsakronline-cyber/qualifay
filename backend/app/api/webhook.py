"""
Webhook API — Inbound events from Evolution API, Paymob, Fawry, Stripe
"""
import hashlib
import hmac
import json
import logging
from fastapi import APIRouter, BackgroundTasks, Request, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.config import settings
from app.core.database import get_db
from fastapi import Depends

router = APIRouter()
logger = logging.getLogger(__name__)


# ─── Evolution API (WhatsApp) ─────────────────────────────────

@router.post("/evolution")
async def evolution_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Main webhook receiver for Evolution API events.
    Validates apikey header, STOP-checks, then queues to Celery.
    """
    # Validate API key
    apikey = request.headers.get("apikey") or request.headers.get("x-api-key")
    if not apikey or not hmac.compare_digest(apikey, settings.EVOLUTION_API_KEY):
        raise HTTPException(status_code=401, detail="Missing or invalid API key")

    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=422, detail="Invalid JSON body")

    event = data.get("event", "")
    instance = data.get("instance", "unknown")
    logger.info(f"WA webhook: event={event} instance={instance}")

    if event == "messages.upsert":
        msg_data = data.get("data", {}).get("message", {})
        key = data.get("data", {}).get("key", {})
        from_me = key.get("fromMe", False)

        content = (
            msg_data.get("conversation")
            or msg_data.get("extendedTextMessage", {}).get("text")
            or ""
        )
        message_type = "text"
        if "imageMessage" in msg_data:
            message_type = "image"
            content = content or msg_data.get("imageMessage", {}).get("caption", "") or "[صورة]"
        elif "videoMessage" in msg_data:
            message_type = "video"
            content = content or msg_data.get("videoMessage", {}).get("caption", "") or "[فيديو]"
        elif "audioMessage" in msg_data:
            message_type = "audio"
            content = content or "[رسالة صوتية]"
        elif "documentMessage" in msg_data:
            message_type = "document"
            content = content or msg_data.get("documentMessage", {}).get("fileName", "") or "[ملف]"
        elif "stickerMessage" in msg_data:
            message_type = "sticker"
            content = content or "[ملصق]"

        wa_jid = key.get("remoteJid", "")
        wa_msg_id = key.get("id")
        timestamp = data.get("data", {}).get("messageTimestamp")
        # Sender's WhatsApp profile name — so the inbox shows a name, not a bare number.
        push_name = data.get("data", {}).get("pushName")

        # Persist message to inbox DB immediately (for both inbound and outbound)
        if wa_jid and not wa_jid.endswith("@g.us"):  # skip groups
            try:
                from app.core.database import AsyncSessionLocal
                from app.models.models import WaInstance
                from app.services.inbox_sync_service import upsert_inbound_message
                async with AsyncSessionLocal() as db:
                    inst_res = await db.execute(
                        select(WaInstance).where(WaInstance.instance_name == instance)
                    )
                    wa_inst = inst_res.scalar_one_or_none()
                    if wa_inst:
                        await upsert_inbound_message(
                            instance_name=instance,
                            tenant_id=wa_inst.tenant_id,
                            wa_jid=wa_jid,
                            content=content,
                            wa_message_id=wa_msg_id,
                            from_me=from_me,
                            timestamp=timestamp,
                            message_type=message_type,
                            push_name=push_name,
                        )
            except Exception as e:
                logger.warning(f"upsert_inbound_message failed: {e}")

        # P6: Update last_contacted_at for leads when we send a message (from_me=True)
        if from_me and wa_jid and not wa_jid.endswith("@g.us"):
            try:
                from app.core.database import AsyncSessionLocal
                from app.models.models import Lead
                from sqlalchemy import update
                from datetime import datetime, timezone
                phone_normalized = "+" + wa_jid.split("@")[0] if not wa_jid.split("@")[0].startswith("+") else wa_jid.split("@")[0]
                async with AsyncSessionLocal() as db2:
                    await db2.execute(
                        update(Lead)
                        .where(Lead.phone == phone_normalized)
                        .values(last_contacted_at=datetime.now(timezone.utc))
                    )
                    await db2.commit()
            except Exception as e_lc:
                logger.debug(f"last_contacted_at update skipped: {e_lc}")

        if not from_me and content:
            # STOP/unsubscribe check — MUST be synchronous BEFORE any Celery queue
            stop_keywords = ["إيقاف", "stop", "unsubscribe", "إلغاء", "لا أريد", "remove me", "opt out"]
            if any(kw in content.lower() for kw in stop_keywords):
                # Immediate synchronous DB unsubscribe — do NOT queue to Celery
                try:
                    from app.core.database import AsyncSessionLocal
                    from app.models.models import Lead, LeadStatus
                    from app.lib.phone import normalize_egyptian_phone
                    from sqlalchemy import update as sa_update
                    raw_phone = wa_jid.split("@")[0]
                    phone = normalize_egyptian_phone(raw_phone) or ("+" + raw_phone if not raw_phone.startswith("+") else raw_phone)
                    async with AsyncSessionLocal() as unsub_db:
                        await unsub_db.execute(
                            sa_update(Lead).where(
                                Lead.phone == phone,
                                Lead.status != LeadStatus.unsubscribed,
                            ).values(status=LeadStatus.unsubscribed)
                        )
                        await unsub_db.commit()
                        logger.info(f"STOP keyword received from {phone} — lead(s) unsubscribed immediately")
                        # Site Factory: end the conversation, delete the preview + data, suppress.
                        try:
                            from app.site_factory.service import on_stop_keyword
                            await on_stop_keyword(unsub_db, phone)
                        except Exception as e_sf:
                            logger.warning(f"site-factory stop handling failed: {e_sf}")
                except Exception as e:
                    logger.error(f"STOP handler synchronous DB update failed: {e}")
                # Return immediately — do NOT queue any further processing
                return {"status": "unsubscribed", "event": event}
            else:
                # Normal inbound message — queue for AI handling
                from app.workers.outreach_tasks import handle_inbound_message
                handle_inbound_message.apply_async(
                    args=[data],
                    queue="outreach",
                )

    elif event == "connection.update":
        # Update instance status in DB
        state = data.get("data", {}).get("state") or data.get("data", {}).get("instance", {}).get("state")
        if state and instance:
            try:
                from app.core.database import AsyncSessionLocal
                from app.models.models import WaInstance, Notification, NotificationType
                async with AsyncSessionLocal() as db:
                    result = await db.execute(
                        select(WaInstance).where(WaInstance.instance_name == instance)
                    )
                    wa = result.scalar_one_or_none()
                    if wa:
                        wa.status = state
                        notif_type = NotificationType.wa_connected if state == "open" else NotificationType.wa_disconnected
                        notif = Notification(
                            tenant_id=wa.tenant_id,
                            type=notif_type,
                            title=f"WhatsApp {'Connected' if state == 'open' else 'Disconnected'}",
                            message=f"Instance '{instance}' is now {state}.",
                            data={"instance_name": instance, "state": state},
                        )
                        db.add(notif)
                        # Log activity
                        try:
                            from app.services.activity_service import log_activity
                            from app.models.models import ActivityType
                            act_type = ActivityType.instance_connected if state == 'open' else ActivityType.instance_disconnected
                            await log_activity(
                                db=db, tenant_id=wa.tenant_id,
                                activity_type=act_type,
                                summary=f"WhatsApp instance '{instance}' {'connected' if state == 'open' else 'disconnected'}",
                                entity_type='instance', entity_id=wa.id,
                            )
                        except Exception:
                            pass
                        await db.commit()

                        # On connect: import the full history (chats AND their messages)
                        # from Evolution into the inbox. Runs in the background — a busy
                        # number can take a few minutes.
                        if state == "open":
                            from app.services.inbox_sync_service import sync_instance_history
                            background_tasks.add_task(
                                sync_instance_history, instance, wa.tenant_id, str(wa.id)
                            )
                            logger.info(f"Triggered full history sync for {instance}")
            except Exception as e:
                logger.error(f"Failed to update instance status: {e}")


    elif event == "qrcode.updated":
        qr_b64 = (
            data.get("data", {}).get("qrcode", {}).get("base64")
            or data.get("data", {}).get("base64")
        )
        if qr_b64 and instance:
            try:
                from app.core.redis import get_redis
                r = await get_redis()
                await r.setex(f"qualifay:qr:{instance}", 120, qr_b64)
                logger.info(f"QR stored in Redis for instance {instance}")
            except Exception as e:
                logger.error(f"Failed to store QR: {e}")

    return {"status": "queued", "event": event}


@router.get("/evolution/health")
async def evolution_health():
    return {"status": "ready"}


# ─── Paymob ───────────────────────────────────────────────────

@router.post("/paymob")
async def paymob_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Paymob payment notification with HMAC validation.
    Updates subscription status on successful payment.
    """
    body = await request.body()
    try:
        data = json.loads(body)
    except Exception:
        raise HTTPException(status_code=422, detail="Invalid JSON")

    # HMAC validation — fail closed: if no secret is configured we cannot verify the
    # caller, so reject rather than trusting an unauthenticated "payment success" body.
    hmac_secret = settings.PAYMOB_HMAC_SECRET
    if not hmac_secret:
        raise HTTPException(status_code=503, detail="Payment webhook not configured")
    if hmac_secret:
        received_hmac = request.headers.get("x-paymob-hmac") or data.get("hmac", "")
        obj = data.get("obj", {})
        # Build concatenated string per Paymob docs
        concat_fields = [
            str(obj.get("amount_cents", "")),
            str(obj.get("created_at", "")),
            str(obj.get("currency", "")),
            str(obj.get("error_occured", "")),
            str(obj.get("has_parent_transaction", "")),
            str(obj.get("id", "")),
            str(obj.get("integration_id", "")),
            str(obj.get("is_3d_secure", "")),
            str(obj.get("is_auth", "")),
            str(obj.get("is_capture", "")),
            str(obj.get("is_refunded", "")),
            str(obj.get("is_standalone_payment", "")),
            str(obj.get("is_voided", "")),
            str(obj.get("order", {}).get("id", "")),
            str(obj.get("owner", "")),
            str(obj.get("pending", "")),
            str(obj.get("source_data", {}).get("pan", "")),
            str(obj.get("source_data", {}).get("sub_type", "")),
            str(obj.get("source_data", {}).get("type", "")),
            str(obj.get("success", "")),
        ]
        concat_str = "".join(concat_fields)
        expected = hmac.new(
            hmac_secret.encode(), concat_str.encode(), hashlib.sha512
        ).hexdigest()
        if not received_hmac:
            raise HTTPException(status_code=400, detail="Missing HMAC signature")
        if not hmac.compare_digest(received_hmac, expected):
            raise HTTPException(status_code=400, detail="HMAC validation failed")

    obj = data.get("obj", {})
    success = obj.get("success", False)
    if success:
        # Site Factory sales carry merchant reference "sf-<prospect_id>" (set via the
        # Intention API's special_reference, echoed as the order's merchant_order_id).
        from app.site_factory.payments import prospect_id_from_reference
        order = obj.get("order", {}) or {}
        sf_id = prospect_id_from_reference(order.get("merchant_order_id") or obj.get("special_reference"))
        if sf_id:
            from app.models.models import SiteProspect
            from app.site_factory import service as sf_service
            prospect = await db.get(SiteProspect, sf_id)
            if prospect:
                try:
                    await sf_service.mark_paid(db, prospect, ref=f"paymob:{obj.get('id', '')}")
                except Exception as e:
                    logger.warning(f"site-factory mark_paid failed for {sf_id}: {e}")
            return {"received": True}
        order_id = str(order.get("id", ""))
        await _update_subscription_by_provider("paymob", order_id, "active", db)

    return {"received": True}


# ─── Fawry ────────────────────────────────────────────────────

@router.post("/fawry")
async def fawry_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Fawry payment callback with signature validation."""
    body = await request.body()
    try:
        data = json.loads(body)
    except Exception:
        raise HTTPException(status_code=422, detail="Invalid JSON")

    # Fawry signature: SHA-256 of merchantCode + merchantRefNum + paymentAmount + fawryRefNumber + paymentStatus + secureKey
    # Fail closed: if no security key is configured we cannot verify the caller.
    security_key = settings.FAWRY_SECURITY_KEY
    merchant_code = settings.FAWRY_MERCHANT_CODE
    if not security_key:
        raise HTTPException(status_code=503, detail="Payment webhook not configured")
    if security_key:
        ref_num = data.get("merchantRefNum", "")
        amount = str(data.get("paymentAmount", ""))
        fawry_ref = data.get("fawryRefNumber", "")
        payment_status = data.get("paymentStatus", "")
        concat = f"{merchant_code}{ref_num}{fawry_ref}{amount}{payment_status}{security_key}"
        expected_sig = hashlib.sha256(concat.encode()).hexdigest()
        received_sig = data.get("signature", "")
        # Require a signature to be present, then compare in constant time — an empty
        # signature must not slip through the check.
        if not received_sig or not hmac.compare_digest(received_sig, expected_sig):
            raise HTTPException(status_code=400, detail="Fawry signature validation failed")

    if data.get("paymentStatus") == "PAID":
        ref_num = data.get("merchantRefNum", "")
        await _update_subscription_by_provider("fawry", ref_num, "active", db)

    return {"received": True}


# ─── Stripe ───────────────────────────────────────────────────

@router.post("/stripe")
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Stripe webhook with signature verification."""
    body = await request.body()
    webhook_secret = settings.STRIPE_WEBHOOK_SECRET

    if webhook_secret:
        sig_header = request.headers.get("stripe-signature", "")
        try:
            import stripe
            event = stripe.Webhook.construct_event(body, sig_header, webhook_secret)
            data = event
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Stripe signature failed: {e}")
    else:
        try:
            data = json.loads(body)
        except Exception:
            raise HTTPException(status_code=422, detail="Invalid JSON")

    event_type = data.get("type", "")
    if event_type in ("invoice.payment_succeeded", "customer.subscription.updated"):
        sub_data = data.get("data", {}).get("object", {})
        stripe_sub_id = sub_data.get("subscription") or sub_data.get("id", "")
        await _update_subscription_by_provider("stripe", stripe_sub_id, "active", db)
    elif event_type == "customer.subscription.deleted":
        sub_data = data.get("data", {}).get("object", {})
        stripe_sub_id = sub_data.get("id", "")
        await _update_subscription_by_provider("stripe", stripe_sub_id, "cancelled", db)

    return {"received": True}


async def _update_subscription_by_provider(
    provider: str, external_id: str, status: str, db: AsyncSession
):
    """Helper to update subscription status by provider and external_id."""
    from app.models.models import Subscription
    if not external_id:
        return
    result = await db.execute(
        select(Subscription).where(
            Subscription.provider == provider,
            Subscription.external_id == external_id,
        )
    )
    sub = result.scalar_one_or_none()
    if sub:
        sub.status = status
        await db.commit()
        logger.info(f"Subscription {sub.id} ({provider}/{external_id}) updated to {status}")


# ─── Email Unsubscribe ────────────────────────────────────────

@router.get("/unsubscribe")
async def email_unsubscribe(
    token: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Unsubscribe a lead via JWT token from email footer."""
    import jwt
    from jwt import PyJWTError as JWTError
    from app.models.models import Lead, LeadStatus

    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        lead_id = payload.get("lead_id")
        if not lead_id:
            raise HTTPException(status_code=400, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=400, detail="Invalid or expired token")

    result = await db.execute(select(Lead).where(Lead.id == lead_id))
    lead = result.scalar_one_or_none()
    if lead and lead.status != LeadStatus.unsubscribed:
        lead.status = LeadStatus.unsubscribed
        await db.commit()
        logger.info(f"Lead {lead_id} unsubscribed via email link")

    return {"unsubscribed": True, "message": "You have been successfully unsubscribed."}
