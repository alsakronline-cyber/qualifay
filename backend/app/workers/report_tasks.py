"""Daily outreach report — one plain email per tenant summarising the last 24 hours:
who was emailed, who replied, who unsubscribed or bounced, and what is queued next.

Opt-in per tenant: tenant_profile["daily_report_email"] = "someone@company.com".
Sent from the tenant's own mailbox (never the platform's), at 23:50 Cairo.
"""
import logging
from datetime import datetime, timedelta

from sqlalchemy import select, text

from app.workers.celery_app import celery_app
from app.workers._loop import run_async

logger = logging.getLogger(__name__)


def build_report(tenant_name: str, sent: list, replies: list, opted_out: list, bounced: list,
                 queued: int, tomorrow_cap: int, day: str) -> tuple:
    """(subject, body). `sent` rows: (time_utc_hhmm, company, email); `replies`: (company, email, first_line)."""
    subject = f"{tenant_name} — daily outreach report {day}: {len(sent)} sent, {len(replies)} replies"
    lines = [f"Daily outreach report — {tenant_name}", f"Period: the 24 hours up to {day} 23:50 (Cairo)", ""]
    lines.append(f"EMAILS SENT: {len(sent)}")
    for i, (t, company, email) in enumerate(sent, 1):
        lines.append(f"  {i}. {company or '-'} <{email}>  at {t} UTC")
    if not sent:
        lines.append("  (none)")
    lines += ["", f"REPLIES: {len(replies)}"]
    for company, email, first in replies:
        lines.append(f"  • {company or email} <{email}>: {first}")
    if not replies:
        lines.append("  (none yet — replies also appear in Qualifay → Inbox)")
    if opted_out:
        lines += ["", f"UNSUBSCRIBED (will never be emailed again): {len(opted_out)}"]
        lines += [f"  • {c or e} <{e}>" for c, e in opted_out]
    if bounced:
        lines += ["", f"BOUNCED (address removed): {len(bounced)}"]
        lines += [f"  • {c or '-'} <{e}>" for c, e in bounced]
    lines += ["", f"STILL QUEUED: {queued} companies", f"NEXT SEND LIMIT: up to {tomorrow_cap} emails tomorrow",
              "", "— Qualifay"]
    return subject, "\n".join(lines)


@celery_app.task(name="report.daily_outreach")
def daily_outreach_report():
    return run_async(_daily_outreach_report())


async def _daily_outreach_report():
    from app.core.database import AsyncSessionLocal
    from app.models.models import Tenant
    from app.services.email_account_service import pick_account, account_cap, account_day_of_life
    from app.services.email_service import email_service
    from app.workers.drip_tasks import cold_email_cap
    from app.core.config import settings

    since = datetime.utcnow() - timedelta(hours=24)
    day = (datetime.utcnow() + timedelta(hours=3)).strftime("%Y-%m-%d")
    done = {}
    async with AsyncSessionLocal() as db:
        tenants = (await db.execute(select(Tenant))).scalars().all()
        for t in tenants:
            to = ((t.tenant_profile or {}).get("daily_report_email") or "").strip()
            if not to:
                continue
            acct = await pick_account(t.id, db)
            if not acct:
                logger.info(f"daily report for {t.name} skipped: no mailbox")
                continue
            p = {"t": t.id, "s": since}
            sent = (await db.execute(text("""
                SELECT to_char((raw_data->>'email_contacted_at')::timestamp, 'HH24:MI'), company, email
                FROM leads WHERE tenant_id=:t AND raw_data->>'email_contacted_at' ~ '^[0-9]{4}-'
                  AND (raw_data->>'email_contacted_at')::timestamp >= :s
                ORDER BY (raw_data->>'email_contacted_at')::timestamp"""), p)).all()
            replies = (await db.execute(text("""
                SELECT DISTINCT ON (c.id) l.company, coalesce(l.email, c.wa_jid), left(split_part(m.content, E'\\n', 1), 120)
                FROM messages m JOIN conversations c ON c.id=m.conversation_id LEFT JOIN leads l ON l.id=c.lead_id
                WHERE c.tenant_id=:t AND c.channel='email' AND m.direction='inbound' AND m.created_at >= :s
                ORDER BY c.id, m.created_at"""), p)).all()
            opted = (await db.execute(text("""
                SELECT company, email FROM leads WHERE tenant_id=:t AND status='unsubscribed'
                  AND raw_data->>'unsubscribed_via'='email' AND updated_at >= :s"""), p)).all()
            bounced = (await db.execute(text("""
                SELECT company, raw_data->>'bounced_email' FROM leads WHERE tenant_id=:t
                  AND raw_data->>'bounced_email' IS NOT NULL AND updated_at >= :s"""), p)).all()
            queued = (await db.execute(text("""
                SELECT count(*) FROM leads WHERE tenant_id=:t AND raw_data->'drip'->>'email_tpl' IS NOT NULL
                  AND email IS NOT NULL AND status='active' AND COALESCE(raw_data->>'email_contacted_at','')=''"""),
                p)).scalar() or 0
            cap = min(account_cap(acct), settings.DRIP_EMAIL_DAILY_MAX,
                      cold_email_cap(account_day_of_life(acct) + 1))
            subject, body = build_report(t.name, sent, replies, opted, bounced, queued, cap, day)
            try:
                await email_service.send_via_account(acct, to, subject, body)
                done[t.name] = len(sent)
            except Exception as e:
                logger.warning(f"daily report for {t.name} failed: {e}")
    logger.info("daily outreach reports sent: %s", done)
    return done
