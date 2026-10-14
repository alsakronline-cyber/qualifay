"""End-to-end: scraped lead → AI qualification → human review → approve → WhatsApp outreach
→ inbound reply → hot-lead alert → STOP unsubscribes and blocks any further outreach.

Everything below the outside world is real: API routes, auth, the Celery task bodies, the
database. LLM answers, WhatsApp sends and Celery dispatch are stubbed (see conftest)."""
from datetime import datetime

from sqlalchemy import select

from tests.integration.conftest import evolution_message


async def _reload(db, model, id_):
    """Fresh row as the workers left it (they use their own sessions). Callers keep plain
    ids/names in locals: expiring the session makes other ORM objects lazy-load."""
    db.expire_all()
    return (await db.execute(select(model).where(model.id == id_))).scalar_one()


async def test_scrape_to_reply_to_stop(client, db, llm, whatsapp, celery,
                                       make_tenant, make_lead, make_instance):
    from app.core.config import settings
    from app.models.models import (Conversation, Lead, LeadStage, LeadStatus, Message,
                                   MessageDirection, Notification)
    from app.workers.ai_tasks import _qualify_lead
    from app.workers.outreach_tasks import _handle_inbound_message, _process_approved_lead

    tenant, _user, auth = await make_tenant("Acme", autonomy="copilot", min_bant_score=50)
    inst = await make_instance(tenant)
    lead = await make_lead(tenant, consent_method="legitimate_interest",
                           consent_at=datetime.utcnow())
    tenant_id, inst_name = tenant.id, inst.instance_name

    # 1. Qualification: quality gate keeps it, BANT scores it above the threshold.
    llm.set("quality_gate", {"keep": True, "reason": "real construction firm"})
    llm.set("lead_enricher", {"company_size": "11-50", "governorate": "Cairo"})
    llm.set("bant_scorer", {"score": 78, "budget": "likely", "authority": "unclear",
                            "need": "confirmed", "timeline": "unclear", "reason": "strong fit"})
    llm.set("aida_writer", "أهلاً منى، نساعد شركات المقاولات على تنظيم مشروعاتها.")
    out = await _qualify_lead(lead.id)
    assert out["route"] == "pending_review", out
    lead = await _reload(db, Lead, lead.id)
    assert lead.stage == LeadStage.pending_review and lead.bant_score == 78
    assert {"quality_gate", "lead_enricher", "bant_scorer"} <= {a for a, _ in llm.calls}
    assert not whatsapp.sent, "nothing may be sent before a human approves"

    # 2. Review queue shows it to the tenant (and the notification exists).
    r = await client.get("/api/v1/leads/review-queue", headers=auth)
    assert r.status_code == 200, r.text
    assert lead.id in r.text
    notes = (await db.execute(select(Notification).where(Notification.tenant_id == tenant_id))).scalars().all()
    assert any((n.data or {}).get("lead_id") == lead.id for n in notes)

    # 3. Human approves → outreach task is queued (not run inline).
    r = await client.post(f"/api/v1/leads/{lead.id}/approve", headers=auth, json={})
    assert r.status_code == 200, r.text
    assert any(args and args[0] == lead.id for args in celery.args_for("process_approved_lead"))

    # 4. The outreach worker sends the first WhatsApp message.
    llm.set("consent_checker", {"compliant": True, "reason": "legitimate interest"})
    await _process_approved_lead(lead.id)
    assert len(whatsapp.sent) == 1
    first = whatsapp.sent[0]
    assert first["jid"] == "201001234567@s.whatsapp.net" and first["instance"] == inst_name
    assert "http" not in first["text"], "no links in a first-contact message"
    lead = await _reload(db, Lead, lead.id)
    assert lead.stage == LeadStage.outreach

    # 5. The lead replies with buying intent → stage moves, message lands in the inbox.
    llm.set("intent_classifier", {"intent": "purchase_intent", "confidence": 0.9, "language": "ar",
                                  "sentiment": "positive", "requires_human": True,
                                  "summary": "asks for a price"})
    reply = evolution_message(inst_name, "201001234567", "بكام الباقة؟")
    r = await client.post("/api/v1/webhook/evolution", json=reply,
                          headers={"apikey": settings.EVOLUTION_API_KEY})
    assert r.status_code == 200, r.text
    assert celery.args_for("handle_inbound_message"), "inbound message must be queued"
    await _handle_inbound_message(reply)
    lead = await _reload(db, Lead, lead.id)
    assert lead.stage == LeadStage.replied
    conv = (await db.execute(select(Conversation).where(Conversation.lead_id == lead.id))).scalars().first()
    inbound = (await db.execute(select(Message).where(
        Message.conversation_id == conv.id, Message.direction == MessageDirection.inbound))).scalars().all()
    assert [m.content for m in inbound] == ["بكام الباقة؟"]
    hot = (await db.execute(select(Notification).where(Notification.tenant_id == tenant_id))).scalars().all()
    assert any((n.data or {}).get("source") == "hot_lead" for n in hot)

    # 6. STOP is handled synchronously in the webhook, before any queue or AI.
    calls_before = len(llm.calls)
    stop = evolution_message(inst_name, "201001234567", "إيقاف")
    r = await client.post("/api/v1/webhook/evolution", json=stop,
                          headers={"apikey": settings.EVOLUTION_API_KEY})
    assert r.json()["status"] == "unsubscribed"
    assert len(llm.calls) == calls_before
    lead = await _reload(db, Lead, lead.id)
    assert lead.status == LeadStatus.unsubscribed

    # 7. An unsubscribed lead is never messaged again, even if re-approved.
    sent_before = len(whatsapp.sent)
    out = await _process_approved_lead(lead.id)
    assert out.get("skipped") and len(whatsapp.sent) == sent_before


async def test_low_score_is_archived_and_never_reaches_review(db, llm, make_tenant, make_lead):
    from app.models.models import Lead, LeadStage
    from app.workers.ai_tasks import _qualify_lead
    tenant, _, _ = await make_tenant("Lowco", min_bant_score=50)
    lead = await make_lead(tenant)
    llm.set("quality_gate", {"keep": True})
    llm.set("bant_scorer", {"score": 20, "reason": "poor fit"})
    out = await _qualify_lead(lead.id)
    assert out.get("archived")
    lead = await _reload(db, Lead, lead.id)
    assert lead.stage == LeadStage.archived


async def test_ai_outage_parks_lead_for_review_instead_of_archiving(db, llm, make_tenant, make_lead):
    """No LLM answer at all (rate-limited everywhere) must not silently lose the lead."""
    from app.models.models import Lead, LeadStage
    from app.workers.ai_tasks import _qualify_lead
    tenant, _, _ = await make_tenant("Outage")
    lead = await make_lead(tenant)
    await _qualify_lead(lead.id)          # llm stub returns "" for every agent
    lead = await _reload(db, Lead, lead.id)
    assert lead.stage == LeadStage.pending_review


async def test_full_autopilot_still_requires_a_verified_lead(db, llm, celery, make_tenant, make_lead):
    from app.models.models import Lead, LeadStage
    from app.workers.ai_tasks import _qualify_lead
    tenant, _, _ = await make_tenant("Auto", autonomy="full")
    real = await make_lead(tenant)
    junk = await make_lead(tenant, name="test", company="", phone=None, website=None,
                           email=None)
    llm.set("quality_gate", {"keep": True})
    llm.set("bant_scorer", {"score": 90, "reason": "great"})
    assert (await _qualify_lead(real.id))["route"] == "approved"
    assert any(a and a[0] == real.id for a in celery.args_for("process_approved_lead"))
    await _qualify_lead(junk.id)
    junk = await _reload(db, Lead, junk.id)
    assert junk.stage != LeadStage.approved
    assert not any(a and a[0] == junk.id for a in celery.args_for("process_approved_lead"))
