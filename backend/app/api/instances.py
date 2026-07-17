"""
WhatsApp Instances API — WA instance management with warmup tracking
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional

from app.core.database import get_db
from app.models.models import WaInstance
from app.services.evolution_service import evolution_service
from app.services.warmup_service import get_cap_for_day
from app.api.auth import get_current_user

router = APIRouter()


class CreateInstanceRequest(BaseModel):
    instance_name: str
    display_name: Optional[str] = None


def _instance_dict(inst: WaInstance, state: str = None) -> dict:
    return {
        "id": inst.id,
        "tenant_id": inst.tenant_id,
        "instance_name": inst.instance_name,
        "display_name": inst.display_name,
        "status": state or inst.status,
        "phone_number": inst.phone_number,
        "day_of_life": inst.day_of_life,
        "daily_wa_cap": inst.daily_wa_cap,
        "sent_today_wa": inst.sent_today_wa,
        "warmup_complete": inst.warmup_complete,
        "paused": bool(getattr(inst, "paused", False)),
        "created_at": inst.created_at.isoformat() if inst.created_at else None,
    }


@router.get("", include_in_schema=False)
@router.get("/")
async def list_instances(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List tenant's WA instances with live connection status."""
    result = await db.execute(
        select(WaInstance).where(WaInstance.tenant_id == current_user["tenant_id"])
    )
    instances = result.scalars().all()

    output = []
    for inst in instances:
        try:
            status_data = await evolution_service.connect_status(inst.instance_name)
            state = (
                status_data.get("instance", {}).get("state")
                or status_data.get("state")
                or "unknown"
            )
            # Normalize Evolution states
            if state == "open":
                state = "connected"
            elif state in ("close", "closed"):
                state = "disconnected"
            inst.status = state
        except Exception:
            state = inst.status or "unknown"

        output.append(_instance_dict(inst, state=state))

    await db.commit()
    return output


@router.post("", include_in_schema=False)
@router.post("/")
async def create_instance(
    req: CreateInstanceRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new WA instance in Evolution API and save to DB."""
    # Check if name already taken
    existing = await db.execute(
        select(WaInstance).where(WaInstance.instance_name == req.instance_name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Instance name already exists")

    try:
        await evolution_service.create_instance(req.instance_name)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Evolution API error: {e}")

    # Set webhook URL
    webhook_url = f"http://{current_user.get('server_ip', 'localhost')}/api/v1/webhook/evolution"
    try:
        await evolution_service.set_webhook(req.instance_name, webhook_url)
    except Exception:
        pass  # Non-critical — can be set later

    instance = WaInstance(
        tenant_id=current_user["tenant_id"],
        instance_name=req.instance_name,
        display_name=req.display_name or req.instance_name,
        status="disconnected",
        day_of_life=0,
        daily_wa_cap=get_cap_for_day(0),
    )
    db.add(instance)
    await db.commit()
    await db.refresh(instance)

    # Get QR code
    qr = await evolution_service.get_qr(req.instance_name)

    return {
        **_instance_dict(instance),
        "qr_code": qr,
    }


@router.get("/{instance_id}/qr")
async def get_qr(
    instance_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get QR code for scanning. Only available when disconnected."""
    result = await db.execute(
        select(WaInstance).where(
            WaInstance.id == instance_id,
            WaInstance.tenant_id == current_user["tenant_id"],
        )
    )
    instance = result.scalar_one_or_none()
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")

    qr = await evolution_service.get_qr(instance.instance_name)
    if not qr:
        raise HTTPException(status_code=404, detail="QR code not available — instance may already be connected")

    return {"qr_code": qr, "instance_name": instance.instance_name}


@router.get("/{instance_id}/status")
async def get_status(
    instance_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get live connection status from Evolution API."""
    result = await db.execute(
        select(WaInstance).where(
            WaInstance.id == instance_id,
            WaInstance.tenant_id == current_user["tenant_id"],
        )
    )
    instance = result.scalar_one_or_none()
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")

    try:
        status_data = await evolution_service.connect_status(instance.instance_name)
        state = (
            status_data.get("instance", {}).get("state")
            or status_data.get("state")
            or "unknown"
        )
    except Exception as e:
        state = "error"
        logger_msg = str(e)

    instance.status = state
    await db.commit()

    return {
        "instance_id": instance_id,
        "instance_name": instance.instance_name,
        "state": state,
        "phone_number": instance.phone_number,
    }


@router.delete("/{instance_id}")
async def delete_instance(
    instance_id: str,
    purge: bool = False,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Disconnect and delete a WA instance.

    Deleting an instance disconnects a *channel*, it does not delete *records*.
    By default conversations/messages are kept (they're CRM history + Law 151 consent
    data) and simply lose their live instance link — the inbox shows them as
    "disconnected". Leads are NEVER deleted here: a lead is a business asset that lives
    in the pipeline independently of the WhatsApp number it came from.

    `purge=true` is the explicit erasure path (e.g. a Law 151 / GDPR right-to-erasure
    request): it deletes this instance's conversations and their messages. Even then,
    leads are kept — erase a contact's leads through the leads API, deliberately.
    """
    from app.models.models import Conversation

    result = await db.execute(
        select(WaInstance).where(
            WaInstance.id == instance_id,
            WaInstance.tenant_id == current_user["tenant_id"],
        )
    )
    instance = result.scalar_one_or_none()
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")

    convs = (await db.execute(
        select(Conversation).where(Conversation.wa_instance_id == instance.id)
    )).scalars().all()
    conv_count = len(convs)

    try:
        await evolution_service.delete_instance(instance.instance_name)
    except Exception:
        # Evolution may already be gone; continue with local cleanup regardless.
        pass

    if purge:
        # Explicit erasure: drop the conversations (messages cascade). Leads untouched.
        for c in convs:
            await db.delete(c)

    # Non-purge: SQLAlchemy nulls each conversation's wa_instance_id on this delete,
    # so history survives and the inbox renders it as a disconnected number.
    await db.delete(instance)
    await db.commit()
    return {
        "deleted": True,
        "instance_id": instance_id,
        "purged": purge,
        "conversations_affected": conv_count,
        "note": (
            f"Deleted {conv_count} conversations; leads kept"
            if purge else
            f"Number disconnected; {conv_count} conversations kept (marked disconnected); leads kept"
        ),
    }


@router.post("/{instance_id}/disconnect")
async def disconnect_instance(
    instance_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Log the WhatsApp number out (disconnect) without deleting the instance."""
    instance = (await db.execute(
        select(WaInstance).where(
            WaInstance.id == instance_id,
            WaInstance.tenant_id == current_user["tenant_id"],
        )
    )).scalar_one_or_none()
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")
    try:
        await evolution_service.logout_instance(instance.instance_name)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Disconnect failed: {e}")
    instance.status = "disconnected"
    await db.commit()
    return {"disconnected": True, "instance_id": instance_id}


@router.post("/{instance_id}/reconnect")
async def reconnect_instance(
    instance_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Re-initiate the WhatsApp connection; returns a QR to scan if one is needed."""
    instance = (await db.execute(
        select(WaInstance).where(
            WaInstance.id == instance_id,
            WaInstance.tenant_id == current_user["tenant_id"],
        )
    )).scalar_one_or_none()
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")
    # Same webhook URL create_instance registers (localhost → nginx → backend), so the
    # recreated instance's qrcode.updated events reach us and get cached.
    webhook_url = "http://localhost/api/v1/webhook/evolution"
    qr = None
    try:
        qr = await evolution_service.regenerate_qr(instance.instance_name, webhook_url)
    except Exception:
        pass
    return {"reconnecting": True, "instance_id": instance_id, "qr": qr}


@router.get("/{instance_id}/warmup")
async def get_warmup_status(
    instance_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get warmup progress and daily limits for an instance."""
    result = await db.execute(
        select(WaInstance).where(
            WaInstance.id == instance_id,
            WaInstance.tenant_id == current_user["tenant_id"],
        )
    )
    instance = result.scalar_one_or_none()
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")

    day = instance.day_of_life or 0
    cap = instance.daily_wa_cap or get_cap_for_day(day)
    used = instance.sent_today_wa or 0

    # Build warmup schedule info
    schedule = []
    for threshold, threshold_cap in [(7, 10), (14, 30), (21, 75), (30, 150), (999, 200)]:
        label = f"Day {threshold}" if threshold < 999 else "Day 30+"
        schedule.append({
            "threshold_day": threshold,
            "label": label,
            "cap": threshold_cap,
            "reached": day >= threshold,
        })

    return {
        "instance_id": instance_id,
        "instance_name": instance.instance_name,
        "day_of_life": day,
        "warmup_complete": instance.warmup_complete,
        "daily_cap": cap,
        "sent_today": used,
        "remaining_today": max(0, cap - used),
        "warmup_percent": min(100, round(day / 30 * 100)),
        "schedule": schedule,
        "last_reset_at": instance.last_reset_at.isoformat() if instance.last_reset_at else None,
    }


@router.post('/{instance_id}/sync', summary='Sync chats from Evolution API into inbox')
async def sync_instance_chats_endpoint(
    instance_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Pull existing chats from Evolution API and create Conversation records."""
    from app.models.models import WaInstance
    from sqlalchemy import select
    tenant_id = current_user['tenant_id']

    result = await db.execute(
        select(WaInstance).where(
            WaInstance.id == instance_id,
            WaInstance.tenant_id == tenant_id,
        )
    )
    wa = result.scalar_one_or_none()
    if not wa:
        raise HTTPException(status_code=404, detail='Instance not found')

    from app.services.inbox_sync_service import sync_instance_chats
    synced = await sync_instance_chats(wa.instance_name, tenant_id, wa.id)
    return {'synced': synced or 0, 'instance_name': wa.instance_name}


class AiToggleRequest(BaseModel):
    ai_suggest_enabled: bool


@router.patch("/{instance_id}/ai-toggle")
async def toggle_ai_suggest(
    instance_id: str,
    req: AiToggleRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Enable/disable AI reply suggestions for a WA instance."""
    result = await db.execute(
        select(WaInstance).where(
            WaInstance.id == instance_id,
            WaInstance.tenant_id == current_user["tenant_id"],
        )
    )
    instance = result.scalar_one_or_none()
    if not instance:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Instance not found")

    instance.ai_suggest_enabled = req.ai_suggest_enabled
    await db.commit()
    await db.refresh(instance)

    return {
        "id": instance.id,
        "instance_name": instance.instance_name,
        "ai_suggest_enabled": instance.ai_suggest_enabled,
    }


class PauseRequest(BaseModel):
    paused: bool


@router.patch("/{instance_id}/pause")
async def set_instance_paused(
    instance_id: str,
    req: PauseRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Pause/resume sending for an instance. Pausing stops outreach without logging the
    WhatsApp number out — the session stays connected and inbound still arrives."""
    instance = (await db.execute(
        select(WaInstance).where(
            WaInstance.id == instance_id,
            WaInstance.tenant_id == current_user["tenant_id"],
        )
    )).scalar_one_or_none()
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")

    instance.paused = req.paused
    await db.commit()
    return {"id": instance.id, "instance_name": instance.instance_name, "paused": instance.paused}
