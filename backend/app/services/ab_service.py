"""A/B testing for outreach — when a tenant has an active test on a channel, hand the
outreach path a variant (least-sent wins, so allocation stays balanced) and remember
which lead got which variant so reply rates can be attributed later."""
import logging
from sqlalchemy import select, func

logger = logging.getLogger(__name__)


async def assign_variant(db, tenant_id: str, channel: str, lead):
    """Return (variant, rendered_body, subject) for an active test on this channel, or
    None if there's no active test. Records the assignment and bumps sent_count."""
    from app.models.models import ABTest, ABVariant, ABAssignment

    test = (await db.execute(
        select(ABTest).where(ABTest.tenant_id == tenant_id, ABTest.channel == channel,
                             ABTest.status == "active").order_by(ABTest.created_at.desc())
    )).scalars().first()
    if not test:
        return None

    variants = (await db.execute(
        select(ABVariant).where(ABVariant.test_id == test.id).order_by(ABVariant.sent_count.asc())
    )).scalars().all()
    if not variants:
        return None

    # Already assigned this lead? Reuse the same variant (a lead should never flip arms).
    existing = (await db.execute(select(ABAssignment).where(
        ABAssignment.test_id == test.id, ABAssignment.lead_id == lead.id))).scalar_one_or_none()
    if existing:
        variant = next((v for v in variants if v.id == existing.variant_id), variants[0])
    else:
        variant = variants[0]  # least-sent
        db.add(ABAssignment(test_id=test.id, variant_id=variant.id, lead_id=lead.id))
        variant.sent_count = (variant.sent_count or 0) + 1

    body = _render(variant.body, lead)
    subject = _render(variant.subject, lead) if variant.subject else None
    return variant, body, subject


def _render(text: str, lead) -> str:
    if not text:
        return text
    repl = {
        "{{name}}": getattr(lead, "name", "") or "",
        "{{company}}": getattr(lead, "company", "") or "",
        "{{industry}}": getattr(lead, "industry", "") or "",
        "{{city}}": getattr(lead, "city", "") or "",
    }
    for k, v in repl.items():
        text = text.replace(k, v)
    return text


async def mark_replied(db, lead_id: str):
    """Called when a lead replies — flips their assignments to replied and bumps the
    variant reply counters. Idempotent."""
    from app.models.models import ABAssignment, ABVariant

    assignments = (await db.execute(select(ABAssignment).where(
        ABAssignment.lead_id == lead_id, ABAssignment.replied == False))).scalars().all()  # noqa: E712
    for a in assignments:
        a.replied = True
        v = (await db.execute(select(ABVariant).where(ABVariant.id == a.variant_id))).scalar_one_or_none()
        if v:
            v.reply_count = (v.reply_count or 0) + 1
