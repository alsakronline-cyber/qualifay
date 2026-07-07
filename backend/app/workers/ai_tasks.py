"""
Celery AI Tasks — Lead qualification pipeline
"""
import asyncio
import logging
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def run_async(coro):
    # Dispose the shared async DB engine pool first: each Celery task runs in a new
    # event loop, and pooled asyncpg connections bound to a prior (closed) loop cause
    # "Future attached to a different loop" errors. Isolated to the Celery process.
    async def _wrapped():
        from app.core.database import engine
        await engine.dispose()
        # Rebuild AI SDK clients so their httpx pools bind to THIS loop, not a closed one.
        try:
            from app.services.ai_service import ai_service
            ai_service.reset()
        except Exception:
            pass
        return await coro
    return asyncio.run(_wrapped())


@celery_app.task(bind=True, max_retries=3, queue="ai")
def qualify_lead(self, lead_id: str):
    """
    Full AI qualification pipeline for a lead:
    1. Quality gate → archive if junk
    2. Enrich lead data
    3. BANT score
    4. Archive if below threshold, else pending_review
    5. Notify tenant
    6. Auto-approve if enabled
    7. Contribute to pool if eligible
    """
    try:
        return run_async(_qualify_lead(lead_id))
    except Exception as exc:
        logger.error(f"qualify_lead failed for {lead_id}: {exc}")
        raise self.retry(exc=exc, countdown=30)


async def _qualify_lead(lead_id: str):
    from app.core.database import AsyncSessionLocal
    from app.models.models import Lead, Tenant, Notification, NotificationType, LeadStage
    from app.services.ai_service import ai_service
    from app.services.lead_pool_service import lead_pool_service
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Lead).where(Lead.id == lead_id))
        lead = result.scalar_one_or_none()
        if not lead:
            logger.warning(f"Lead {lead_id} not found")
            return {"error": "lead_not_found"}

        # Fetch tenant settings
        t_result = await db.execute(select(Tenant).where(Tenant.id == lead.tenant_id))
        tenant = t_result.scalar_one_or_none()
        if not tenant:
            return {"error": "tenant_not_found"}

        lead_dict = {
            "id": lead.id,
            "name": lead.name,
            "company": lead.company,
            "phone": lead.phone,
            "email": lead.email,
            "industry": lead.industry,
            "city": lead.city,
            "source": lead.source.value if lead.source else None,
            "raw_data": lead.raw_data or {},
        }

        # Step 1: Quality gate
        gate = await ai_service.quality_gate(lead_dict)
        if not gate.get("keep", True):
            lead.stage = LeadStage.archived
            lead.ai_notes = f"[Quality Gate] Rejected: {gate.get('reason', 'unknown')}"
            await db.commit()
            logger.info(f"Lead {lead_id} archived by quality gate: {gate.get('reason')}")
            return {"archived": True, "reason": gate.get("reason")}

        # Step 2: Enrich
        enriched = await ai_service.enrich_lead({**lead_dict, **(lead.raw_data or {})})
        if enriched.get("company"):
            lead.company = enriched["company"]
        if enriched.get("industry"):
            lead.industry = enriched["industry"]
        if enriched.get("company_size"):
            lead.company_size = enriched["company_size"]
        if enriched.get("city"):
            lead.city = enriched["city"]
        if enriched.get("governorate"):
            lead.governorate = enriched["governorate"]
        if enriched.get("website"):
            lead.website = enriched["website"]
        if enriched.get("language"):
            lead.language = enriched["language"]

        # Update lead_dict with enriched data
        lead_dict.update({
            "company": lead.company,
            "industry": lead.industry,
            "company_size": lead.company_size,
            "city": lead.city,
        })

        # Step 3: BANT score
        bant = await ai_service.score_bant(lead_dict)
        lead.bant_score = bant.get("score", 0)
        lead.bant_budget = bant.get("budget")
        lead.bant_authority = bant.get("authority")
        lead.bant_need = bant.get("need")
        lead.bant_timeline = bant.get("timeline")
        lead.bant_reason = bant.get("reason")

        min_score = tenant.min_bant_score or 50

        # If the AI couldn't score (rate limit / parse failure), don't silently archive —
        # send it to the human review queue so a real lead isn't lost to a transient API error.
        if bant.get("scoring_failed"):
            lead.stage = LeadStage.pending_review
            lead.ai_notes = "[BANT] Automatic scoring unavailable (AI rate-limited or failed). Needs manual review."
            await db.commit()
            logger.warning(f"Lead {lead_id} -> pending_review (BANT scoring failed)")
            return {"pending_review": True, "reason": "scoring_failed"}

        # Step 4: Archive or pending_review
        if lead.bant_score < min_score:
            lead.stage = LeadStage.archived
            lead.ai_notes = f"[BANT] Score {lead.bant_score} below threshold {min_score}. {bant.get('reason', '')}"
            await db.commit()
            logger.info(f"Lead {lead_id} archived: BANT score {lead.bant_score} < {min_score}")
            return {"archived": True, "reason": f"BANT score {lead.bant_score} below threshold"}

        lead.stage = LeadStage.pending_review
        lead.ai_notes = f"[BANT score: {lead.bant_score}] {bant.get('reason', '')}"

        # Step 5: Notify tenant
        notif = Notification(
            tenant_id=lead.tenant_id,
            type=NotificationType.leads_ready,
            title="New Lead Ready for Review",
            message=f"Lead '{lead.company or lead.name}' qualified with BANT score {lead.bant_score}.",
            data={"lead_id": lead_id, "bant_score": lead.bant_score, "stage": "pending_review"},
        )
        db.add(notif)
        await db.commit()

        # Step 6: Auto-approve if tenant setting enabled
        if tenant.auto_approve and lead.bant_score >= min_score:
            lead.stage = LeadStage.approved
            await db.commit()
            from app.workers.outreach_tasks import process_approved_lead
            process_approved_lead.apply_async(args=[lead_id], queue="outreach")
            logger.info(f"Lead {lead_id} auto-approved and queued for outreach")

        # Step 7: Contribute to pool
        if lead.bant_score >= 60 and tenant.contribute_to_pool:
            await lead_pool_service.contribute(lead_id, db)

        return {
            "lead_id": lead_id,
            "bant_score": lead.bant_score,
            "stage": lead.stage.value,
        }


@celery_app.task(queue="ai")
def cleanup_lead_pool():
    """Delete expired lead pool entries."""
    return run_async(_cleanup_lead_pool())


async def _cleanup_lead_pool():
    from app.core.database import AsyncSessionLocal
    from app.models.models import LeadPool
    from sqlalchemy import delete
    from datetime import datetime

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            delete(LeadPool).where(LeadPool.expires_at < datetime.utcnow())
        )
        await db.commit()
        deleted = result.rowcount
        logger.info(f"Cleaned up {deleted} expired lead pool entries")
        return {"deleted": deleted}


@celery_app.task(queue="ai")
def update_sentiment(conversation_id: str):
    """Analyze and update conversation sentiment from last 10 messages."""
    return run_async(_update_sentiment(conversation_id))


async def _update_sentiment(conversation_id: str):
    from app.core.database import AsyncSessionLocal
    from app.models.models import Conversation, Message
    from app.services.ai_service import ai_service
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc())
            .limit(10)
        )
        msgs = result.scalars().all()
        if not msgs:
            return {"skipped": True, "reason": "no_messages"}

        history = [{"direction": m.direction.value, "content": m.content or ""} for m in reversed(msgs)]
        sentiment_data = await ai_service.analyze_sentiment(history)

        conv_result = await db.execute(select(Conversation).where(Conversation.id == conversation_id))
        conv = conv_result.scalar_one_or_none()
        if conv:
            conv.sentiment = sentiment_data.get("sentiment", "neutral")
            await db.commit()

        return sentiment_data


# ── P7: Auto-enrich lead from scraped URLs ────────────────────

@celery_app.task(name="enrich_lead_from_urls", queue="ai")
def enrich_lead_from_urls(lead_id: str, tenant_id: str):
    """Enrich a lead using its website/social URLs via OpenRouter AI."""
    try:
        return run_async(_async_enrich_lead(lead_id, tenant_id))
    except Exception as exc:
        logger.error(f"enrich_lead_from_urls failed for {lead_id}: {exc}")


async def _async_enrich_lead(lead_id: str, tenant_id: str):
    from app.core.database import AsyncSessionLocal
    from app.models.models import Lead
    from app.core.config import settings
    from sqlalchemy import select
    import httpx, json

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Lead).where(Lead.id == lead_id, Lead.tenant_id == tenant_id)
        )
        lead = result.scalar_one_or_none()
        if not lead:
            logger.warning(f"enrich_lead_from_urls: lead {lead_id} not found")
            return

        raw = lead.raw_data or {}
        urls_to_check = [u for u in [
            raw.get("website"), raw.get("facebook_url"),
            raw.get("linkedin_url"), lead.website
        ] if u]

        if not urls_to_check:
            logger.debug(f"enrich_lead_from_urls: no URLs for lead {lead_id}")
            return

        prompt = (
            f"Extract company information from these URLs: {urls_to_check}\n\n"
            "Return JSON only:\n"
            "{\n"
            '  "company_size": "1-10|11-50|51-200|200+",\n'
            '  "industry": "string",\n'
            '  "description": "string (max 100 chars)",\n'
            '  "email": "string or null",\n'
            '  "phone": "string or null"\n'
            "}"
        )

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": f"Bearer {settings.OPENROUTER_API_KEY}"},
                    json={
                        "model": "meta-llama/llama-3.3-70b-instruct",
                        "messages": [{"role": "user", "content": prompt}],
                        "response_format": {"type": "json_object"},
                    }
                )
                if r.status_code != 200:
                    logger.warning(f"OpenRouter returned {r.status_code} for lead {lead_id}")
                    return
                content_str = r.json()["choices"][0]["message"]["content"]
                enriched = json.loads(content_str)
        except Exception as e:
            logger.error(f"OpenRouter call failed for lead {lead_id}: {e}")
            return

        # Only fill empty fields (don't overwrite user data)
        if enriched.get("industry") and not lead.industry:
            lead.industry = enriched["industry"]
        if enriched.get("email") and not lead.email:
            lead.email = enriched["email"]
        if enriched.get("phone") and not lead.phone:
            lead.phone = enriched["phone"]

        raw = lead.raw_data or {}
        if enriched.get("company_size"):
            raw["company_size"] = enriched["company_size"]
        if enriched.get("description"):
            raw["description"] = enriched["description"]
        lead.raw_data = raw
        await db.commit()
        logger.info(f"enrich_lead_from_urls: lead {lead_id} enriched successfully")


# Pipeline stages a WhatsApp chat can map to (subset of LeadStage, kept as strings so this
# is unit-testable without importing the ORM enum).
VALID_WA_STAGES = frozenset({
    "replied", "qualifying", "meeting", "proposal", "negotiation", "won", "lost",
})


def clamp_score(value) -> int:
    """Coerce an AI-returned BANT score to a safe 0-100 int (defensive against the LLM
    returning strings, floats, negatives, or >100)."""
    try:
        return max(0, min(100, int(value)))
    except (TypeError, ValueError):
        return 0


def normalize_stage(name) -> str:
    """Map an AI-returned stage name to a valid pipeline stage string, defaulting to
    'replied' for anything unrecognized (a WA chat with intent has at least replied)."""
    if isinstance(name, str) and name in VALID_WA_STAGES:
        return name
    return "replied"


@celery_app.task(name="sync_wa_to_pipeline", queue="ai")
def sync_wa_to_pipeline(tenant_id: str):
    """Background: analyze a tenant's WhatsApp chats and push intent leads into the pipeline."""
    return run_async(_sync_wa_to_pipeline_async(tenant_id))


async def _sync_wa_to_pipeline_async(tenant_id: str):
    from app.core.database import AsyncSessionLocal
    from app.models.models import (
        Conversation, Message, MessageDirection, Lead, LeadStage, LeadStatus,
        LeadSource, Notification, NotificationType,
    )
    from app.services.ai_service import ai_service
    from app.lib.phone import normalize_egyptian_phone
    from sqlalchemy import select

    STAGE_MAP = {
        "replied": LeadStage.replied, "qualifying": LeadStage.qualifying,
        "meeting": LeadStage.meeting, "proposal": LeadStage.proposal,
        "negotiation": LeadStage.negotiation, "won": LeadStage.won, "lost": LeadStage.lost,
    }
    created = updated = skipped = failed = 0

    async with AsyncSessionLocal() as db:
        convs = (await db.execute(
            select(Conversation).where(Conversation.tenant_id == tenant_id).limit(500)
        )).scalars().all()
        conv_ids = [c.id for c in convs]

        # Batch-load all messages once (avoids N+1).
        by_conv: dict = {}
        if conv_ids:
            all_msgs = (await db.execute(
                select(Message).where(Message.conversation_id.in_(conv_ids))
                .order_by(Message.created_at.asc())
            )).scalars().all()
            for m in all_msgs:
                by_conv.setdefault(m.conversation_id, []).append(m)

        for i, conv in enumerate(convs):
            cmsgs = by_conv.get(conv.id, [])
            if not any(m.direction == MessageDirection.inbound for m in cmsgs):
                skipped += 1
                continue
            try:
                msg_dicts = [
                    {"direction": m.direction.value if hasattr(m.direction, "value") else str(m.direction),
                     "content": m.content or ""}
                    for m in cmsgs
                ]
                analysis = await ai_service.analyze_conversation_for_pipeline(msg_dicts, conv.contact_name or "")
            except Exception as e:
                failed += 1
                logger.warning(f"sync_wa_to_pipeline: analysis failed for {conv.id}: {e}")
                continue

            if not analysis.get("is_lead"):
                skipped += 1
                continue

            stage = STAGE_MAP[normalize_stage(analysis.get("stage"))]
            score = clamp_score(analysis.get("score"))
            reason = analysis.get("reason", "")
            raw_phone = conv.wa_jid.split("@")[0] if conv.wa_jid else ""
            phone = normalize_egyptian_phone(raw_phone) or ("+" + raw_phone if raw_phone else None)

            lead = None
            if conv.lead_id:
                lead = (await db.execute(select(Lead).where(Lead.id == conv.lead_id))).scalar_one_or_none()
            elif phone:
                lead = (await db.execute(
                    select(Lead).where(Lead.tenant_id == tenant_id, Lead.phone == phone)
                )).scalar_one_or_none()

            notes = f"[WA] {analysis.get('intent', '')}: {reason}"
            if lead:
                lead.stage = stage
                lead.bant_score = score
                lead.ai_notes = notes
                conv.lead_id = lead.id
                updated += 1
            else:
                lead = Lead(
                    tenant_id=tenant_id, source=LeadSource.inbound_wa,
                    name=conv.contact_name, company=conv.contact_name, phone=phone,
                    stage=stage, status=LeadStatus.active, bant_score=score, ai_notes=notes,
                )
                db.add(lead)
                await db.flush()
                conv.lead_id = lead.id
                created += 1

            # Periodic commit so progress survives a mid-run failure.
            if (i + 1) % 10 == 0:
                await db.commit()

        await db.commit()

        # Notify the tenant that the sync finished.
        try:
            db.add(Notification(
                tenant_id=tenant_id,
                type=NotificationType.leads_ready,
                title="مزامنة واتساب للأنابيب",
                message=f"تمت المزامنة: {created} عميل جديد، {updated} محدّث، {skipped} تم تجاهله.",
                data={"created": created, "updated": updated, "skipped": skipped, "failed": failed},
            ))
            await db.commit()
        except Exception as e:
            logger.warning(f"sync_wa_to_pipeline notification failed: {e}")

    logger.info(f"sync_wa_to_pipeline done for {tenant_id}: +{created} ~{updated} skip{skipped} fail{failed}")
    return {"created": created, "updated": updated, "skipped": skipped, "failed": failed, "total": len(convs)}


# ─── Browser-extension agent ingest (LinkedIn contacts / Facebook buyer intent) ─────

@celery_app.task(name="ingest_agent_leads", queue="ai")
def ingest_agent_leads(tenant_id: str, task_id: str, platform: str, items: list):
    """Background: turn what the browser extension scraped into qualified leads.

    Fire-and-forget from POST /api/v1/agent/ingest so the extension's poll loop never
    blocks on an AI call. LinkedIn contacts go through the same BANT qualify_lead pipeline
    every other scraper uses; Facebook posts are AI-confirmed as buyer intent and scored
    directly (the post text itself is already the qualifying signal).
    """
    return run_async(_ingest_agent_leads_async(tenant_id, task_id, platform, items))


async def _queue_profile_enrichment(db, tenant_id: str, profile_url: str):
    """Queue a linkedin_profile_visit task so the extension enriches a lead's contact
    info. Dedupes against tasks already waiting for the same URL so a re-scrape of the
    same search doesn't pile up duplicate visits."""
    from app.models.models import AgentTask, AgentPlatform
    from sqlalchemy import select

    pending = await db.execute(
        select(AgentTask).where(
            AgentTask.tenant_id == tenant_id,
            AgentTask.type == "linkedin_profile_visit",
            AgentTask.status.in_(["pending", "in_progress"]),
        )
    )
    for t in pending.scalars():
        if (t.params or {}).get("profile_url") == profile_url:
            return  # already queued for this profile

    db.add(AgentTask(
        tenant_id=tenant_id,
        platform=AgentPlatform.linkedin,
        type="linkedin_profile_visit",
        params={"profile_url": profile_url, "max_results": 1},
        status="pending",
    ))
    await db.commit()


async def _ingest_agent_leads_async(tenant_id: str, task_id: str, platform: str, items: list):
    from datetime import datetime, timedelta
    from app.core.database import AsyncSessionLocal
    from app.models.models import (
        AgentTask, Lead, LeadStage, LeadStatus, LeadSource, Notification, NotificationType,
    )
    from app.lib.phone import normalize_egyptian_phone
    from scrapers.intent import detect_buyer_intent, extract_phone_from_text
    from sqlalchemy import select

    created = 0

    async with AsyncSessionLocal() as db:
        task_result = await db.execute(select(AgentTask).where(AgentTask.id == task_id))
        task = task_result.scalar_one_or_none()
        if not task:
            logger.warning(f"ingest_agent_leads: task {task_id} not found")
            return {"created": 0}

        try:
            if platform == "linkedin" and task.type == "linkedin_profile_visit":
                # Profile visits enrich an ALREADY-scraped lead with contact info (search
                # results never expose email/phone — only the profile's own Contact Info
                # modal does). Match by linkedin_url so this updates, never duplicates.
                for item in items:
                    url = (item.get("url") or "").split("?")[0]
                    if not url:
                        continue
                    lead_res = await db.execute(
                        select(Lead).where(Lead.tenant_id == tenant_id, Lead.linkedin_url == url)
                    )
                    lead = lead_res.scalar_one_or_none()
                    raw_phone = item.get("phone")
                    phone = normalize_egyptian_phone(raw_phone) if raw_phone else None
                    email = item.get("email")

                    if lead:
                        gained_contact = False
                        if phone and not lead.phone:
                            lead.phone = phone
                            gained_contact = True
                        if email and not lead.email:
                            lead.email = email
                            gained_contact = True
                        lead.ai_notes = ((lead.ai_notes or "").strip() + " [contact info enriched via extension]").strip()
                        await db.commit()
                        created += 1
                        if gained_contact:
                            try:
                                from app.workers.ai_tasks import qualify_lead
                                qualify_lead.delay(lead.id)  # new contact info can change BANT score
                            except Exception as e:
                                logger.warning(f"ingest_agent_leads: failed to queue qualify_lead: {e}")
                    else:
                        name = (item.get("name") or "").strip()
                        if not name:
                            continue
                        new_lead = Lead(
                            tenant_id=tenant_id, source=LeadSource.linkedin,
                            name=name, company=item.get("company"), industry=item.get("title"),
                            phone=phone, email=email, linkedin_url=url, stage=LeadStage.new,
                            raw_data={"via": "browser_extension"},
                        )
                        db.add(new_lead)
                        await db.commit()
                        created += 1
                        try:
                            from app.workers.ai_tasks import qualify_lead
                            qualify_lead.delay(new_lead.id)
                        except Exception as e:
                            logger.warning(f"ingest_agent_leads: failed to queue qualify_lead: {e}")

            elif platform == "linkedin":
                for item in items:
                    name = (item.get("name") or "").strip()
                    if not name:
                        continue
                    raw_phone = item.get("phone")
                    phone = normalize_egyptian_phone(raw_phone) if raw_phone else None

                    existing = None
                    if phone:
                        dup = await db.execute(
                            select(Lead).where(Lead.tenant_id == tenant_id, Lead.phone == phone)
                        )
                        existing = dup.scalar_one_or_none()
                    if existing:
                        continue  # already have this contact — skip, don't duplicate

                    lead = Lead(
                        tenant_id=tenant_id, source=LeadSource.linkedin,
                        name=name, company=item.get("company"), industry=item.get("title"),
                        city=item.get("location"), phone=phone, email=item.get("email"),
                        linkedin_url=item.get("url"), stage=LeadStage.new,
                        raw_data={"via": "browser_extension"},
                    )
                    db.add(lead)
                    # Commit (not just flush) per lead — qualify_lead is dispatched right
                    # after, so the row must actually be durable before another process
                    # tries to load it, and a later error in this loop can't roll it back.
                    await db.commit()
                    created += 1
                    # Auto-enrich: a LinkedIn search result has a profile URL but no phone/
                    # email. Queue a profile-visit task so the extension opens the profile and
                    # pulls contact info from the "Contact info" modal — turning an unreachable
                    # lead into a contactable one without any manual step.
                    if lead.linkedin_url and not lead.phone and not lead.email:
                        await _queue_profile_enrichment(db, tenant_id, lead.linkedin_url)
                    try:
                        from app.workers.ai_tasks import qualify_lead
                        qualify_lead.delay(lead.id)
                    except Exception as e:
                        logger.warning(f"ingest_agent_leads: failed to queue qualify_lead: {e}")

            elif platform == "facebook":
                from app.services.ai_service import ai_service
                from app.models.models import Tenant
                t_res = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
                tenant = t_res.scalar_one_or_none()
                min_score = (tenant.min_bant_score if tenant else 50) or 50

                for item in items:
                    text = (item.get("text") or "").strip()
                    if not text or not detect_buyer_intent(text):
                        continue  # cheap keyword pre-filter already applied client-side too
                    try:
                        analysis = await ai_service.classify_buyer_intent(text)
                    except Exception as e:
                        logger.warning(f"ingest_agent_leads: FB intent classify failed: {e}")
                        continue
                    if not analysis.get("is_buyer"):
                        continue
                    score = clamp_score(analysis.get("score"))
                    if score < min_score:
                        continue

                    raw_phone = extract_phone_from_text(text) or item.get("phone")
                    phone = normalize_egyptian_phone(raw_phone) if raw_phone else None
                    if phone:
                        dup = await db.execute(
                            select(Lead).where(Lead.tenant_id == tenant_id, Lead.phone == phone)
                        )
                        if dup.scalar_one_or_none():
                            continue

                    lead = Lead(
                        tenant_id=tenant_id, source=LeadSource.facebook,
                        name=item.get("name"), phone=phone,
                        industry=analysis.get("wants") or "buyer intent",
                        stage=LeadStage.pending_review, bant_score=score,
                        ai_notes=f"[FB] {analysis.get('urgency','')}: {analysis.get('reason','')}",
                        raw_data={"post_text": text[:500], "post_url": item.get("url"), "via": "browser_extension"},
                    )
                    db.add(lead)
                    await db.commit()
                    created += 1

            task.result_count = created
            task.total_results = (task.total_results or 0) + created
            task.completed_at = datetime.utcnow()
            if task.recurring:
                task.status = "pending"
                task.next_eligible_at = datetime.utcnow() + timedelta(minutes=task.interval_minutes or 120)
            else:
                task.status = "done"

        except Exception as exc:
            task.status = "error"
            task.error_message = str(exc)[:500]
            task.completed_at = datetime.utcnow()
            logger.error(f"ingest_agent_leads failed for task {task_id}: {exc}", exc_info=True)

        await db.commit()

        if created > 0:
            try:
                db.add(Notification(
                    tenant_id=tenant_id,
                    type=NotificationType.leads_ready,
                    title="عملاء جدد من المتصفح",
                    message=f"تم استقبال {created} عميل جديد من {'LinkedIn' if platform == 'linkedin' else 'Facebook'}.",
                    data={"created": created, "platform": platform, "task_id": task_id},
                ))
                await db.commit()
            except Exception as e:
                logger.warning(f"ingest_agent_leads notification failed: {e}")

    logger.info(f"ingest_agent_leads done: platform={platform} task={task_id} created={created}")
    return {"created": created}
