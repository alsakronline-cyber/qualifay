"""Notification service — one place to raise an alert. Always records an in-app
Notification; for urgent ones it also pushes to the OWNER's WhatsApp (via a connected
Evolution instance), so revenue-critical events reach them even when they're not in the
app. This is what makes the system feel like a coworker that taps you on the shoulder."""
import logging

from sqlalchemy import select, and_

logger = logging.getLogger(__name__)


async def notify(db, tenant_id: str, ntype, title: str, message: str,
                 data: dict = None, urgent: bool = False):
    """Create an in-app notification; if urgent, also WhatsApp the tenant owner.
    `ntype` is a NotificationType. Never raises — a failed push must not break the caller."""
    from app.models.models import Notification
    data = data or {}
    db.add(Notification(tenant_id=tenant_id, type=ntype, title=title, message=message, data=data))
    if urgent:
        try:
            await _whatsapp_owner(db, tenant_id, f"*{title}*\n{message}")
        except Exception as e:
            logger.warning("owner WhatsApp push failed for tenant %s: %s", tenant_id, e)


async def _owner_phone(db, tenant_id: str):
    """The tenant admin's phone (E.164) — where owner alerts go."""
    from app.models.models import User
    u = (await db.execute(select(User).where(and_(
        User.tenant_id == tenant_id, User.is_tenant_admin == True, User.phone.isnot(None)  # noqa: E712
    )))).scalars().first()
    return u.phone if u else None


async def _connected_instance(db, tenant_id: str):
    from app.models.models import WaInstance
    return (await db.execute(select(WaInstance).where(and_(
        WaInstance.tenant_id == tenant_id, WaInstance.status.in_(["connected", "open"])
    )))).scalars().first()


async def _whatsapp_owner(db, tenant_id: str, text: str) -> bool:
    """Send `text` to the owner's WhatsApp via one of the tenant's connected instances."""
    phone = await _owner_phone(db, tenant_id)
    if not phone:
        return False
    inst = await _connected_instance(db, tenant_id)
    if not inst:
        return False
    from app.services.evolution_service import evolution_service
    jid = f"{phone.replace('+', '')}@s.whatsapp.net"
    await evolution_service.send_text(inst.instance_name, jid, text)
    logger.info("owner alert sent to %s via %s", phone, inst.instance_name)
    return True
