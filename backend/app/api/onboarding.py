"""AI Setup Consultant — a conversational onboarding that interviews the owner, then
drafts the whole workspace (ICP, templates, sequence, flow, A/B test, campaign) for
review, and lets them pick how autonomous the system should run."""
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.auth import get_current_user, require_admin
from app.services.ai_service import ai_service
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


async def _start_auto_scraping(db, tenant):
    """Kick off zero-touch scraping the moment onboarding completes — best-effort so a hiccup
    here never blocks the user from finishing setup."""
    try:
        from app.api.scrape import activate_growth_defaults
        await activate_growth_defaults(db, tenant)
    except Exception as e:
        logger.warning("auto-scraping activation failed for tenant %s: %s", tenant.id, e)

AUTONOMY_LEVELS = ("full", "copilot", "manual", "off")


async def _tenant(tenant_id: str, db: AsyncSession):
    from app.models.models import Tenant
    t = (await db.execute(select(Tenant).where(Tenant.id == tenant_id))).scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return t


class Msg(BaseModel):
    role: str
    content: str


class ChatIn(BaseModel):
    messages: List[Msg]


@router.get("/profile")
async def get_profile(current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    t = await _tenant(current_user["tenant_id"], db)
    return {
        "profile": t.tenant_profile or {},
        "autonomy": t.autonomy or "copilot",
        "onboarding_done": bool(t.onboarding_done),
        "build_draft": (t.tenant_profile or {}).get("_build_draft"),
    }


# The business-brief fields the owner may edit directly (mirrors what the AI interview
# extracts). Internal keys like _build_draft are deliberately excluded so a manual edit
# can never clobber generated state.
EDITABLE_PROFILE_FIELDS = frozenset({
    "business_name", "industry", "sells", "value_prop", "ideal_customer",
    "pain_points", "price_range", "cities", "current_sources",
    "monthly_lead_target", "team_size", "tone", "website", "description",
    # Document defaults — pre-fill every new sales document (editable per document).
    "default_payment_terms", "default_terms",
    # Seller header fields shown on printed documents.
    "tax_id", "address", "phone", "email",
    "logo",   # company logo (data URI) shown on documents/PDFs
})


def _public_profile(profile: dict) -> dict:
    """Strip internal keys (prefixed with _) before returning a profile to the client."""
    return {k: v for k, v in (profile or {}).items() if not k.startswith("_")}


class ProfileUpdate(BaseModel):
    profile: Dict[str, Any]


@router.patch("/profile", summary="Edit the company profile directly (no AI needed)")
async def update_profile(body: ProfileUpdate, current_user: dict = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    """Let the tenant admin correct/update any business-brief field the AI collected,
    at any time after onboarding. Only whitelisted fields are written; empty values clear
    a field. The updated brief immediately flows into outreach copy (tenant_context_str)."""
    require_admin(current_user)
    t = await _tenant(current_user["tenant_id"], db)
    prof = dict(t.tenant_profile or {})
    for k, v in (body.profile or {}).items():
        if k in EDITABLE_PROFILE_FIELDS:
            prof[k] = (v.strip() if isinstance(v, str) else v)
    t.tenant_profile = prof
    await db.commit()
    return {"profile": _public_profile(prof)}


UI_LANGS = ("ar", "en")
AI_LANGS = ("ar", "en", "masri")


class LanguageIn(BaseModel):
    # One user-facing choice drives both. "masri" keeps the UI Arabic (RTL) but makes the
    # AI write in Egyptian colloquial.
    ai_language: str          # ar | en | masri
    ui_language: Optional[str] = None   # ar | en; derived from ai_language when omitted


@router.get("/language", summary="Get the tenant's UI + AI output language")
async def get_language(current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    t = await _tenant(current_user["tenant_id"], db)
    return {"ui_language": t.language or "ar", "ai_language": t.ai_language or "ar"}


@router.post("/language", summary="Set the tenant's UI + AI output language")
async def set_language(body: LanguageIn, current_user: dict = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db)):
    """Choose the language the system UI shows and the language the AI writes messages in.
    AI: ar (فصحى) | en (English) | masri (عامية مصرية). UI: ar (RTL) | en (LTR) — colloquial
    uses the Arabic UI."""
    require_admin(current_user)
    if body.ai_language not in AI_LANGS:
        raise HTTPException(status_code=400, detail=f"ai_language must be one of {AI_LANGS}")
    ui = body.ui_language or ("en" if body.ai_language == "en" else "ar")
    if ui not in UI_LANGS:
        raise HTTPException(status_code=400, detail=f"ui_language must be one of {UI_LANGS}")
    t = await _tenant(current_user["tenant_id"], db)
    t.ai_language = body.ai_language
    t.language = ui
    await db.commit()
    return {"ui_language": t.language, "ai_language": t.ai_language}


class ScraperKeysIn(BaseModel):
    apollo: Optional[str] = None
    hunter: Optional[str] = None
    google_cse_key: Optional[str] = None
    google_cse_cx: Optional[str] = None
    facebook_adlib: Optional[str] = None


@router.get("/scraper-keys", summary="Which scraper API keys this company has set (no values)")
async def get_scraper_keys(current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from app.services.scraper_keys import get_keys, status
    return status(await get_keys(db, current_user["tenant_id"]))


@router.put("/scraper-keys", summary="Set this company's own scraper API keys (encrypted)")
async def set_scraper_keys(body: ScraperKeysIn, current_user: dict = Depends(get_current_user),
                           db: AsyncSession = Depends(get_db)):
    require_admin(current_user)
    from app.services.scraper_keys import set_keys
    # exclude_unset so untouched fields keep their stored value; empty string clears.
    return await set_keys(db, current_user["tenant_id"], body.dict(exclude_unset=True))


@router.post("/reset", summary="Start the AI setup over from scratch")
async def reset_onboarding(current_user: dict = Depends(get_current_user),
                           db: AsyncSession = Depends(get_db)):
    """Wipe the collected business profile and re-open the AI interview so the owner can
    redo their setup from scratch. Does NOT delete already-generated templates/sequences/
    campaigns (those are additive and can be managed on their own screens) — it only clears
    the profile brief and the onboarding flag so the wizard runs again."""
    require_admin(current_user)
    t = await _tenant(current_user["tenant_id"], db)
    t.tenant_profile = {}
    t.onboarding_done = False
    await db.commit()
    return {"onboarding_done": False, "profile": {}}


@router.post("/chat")
async def chat(body: ChatIn, current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """One interview turn. Merges any newly-extracted fields into the tenant profile."""
    require_admin(current_user)  # onboarding is an owner/admin setup task
    t = await _tenant(current_user["tenant_id"], db)
    profile: Dict[str, Any] = dict(t.tenant_profile or {})
    profile.pop("_build_draft", None)  # don't feed the draft back into the interview

    turn = await ai_service.interview_turn([m.dict() for m in body.messages], profile)
    patch = turn.get("profile_patch") or {}
    if isinstance(patch, dict):
        profile.update({k: v for k, v in patch.items() if v not in (None, "", [])})

    merged = dict(t.tenant_profile or {})
    merged.update(profile)
    t.tenant_profile = merged
    await db.commit()

    return {"reply": turn.get("reply", ""), "done": bool(turn.get("done")), "profile": profile}


@router.post("/build")
async def build(current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Kick off the workspace-plan generation (reasoning model, runs in Celery)."""
    require_admin(current_user)
    t = await _tenant(current_user["tenant_id"], db)
    if not t.tenant_profile:
        raise HTTPException(status_code=400, detail="Finish the interview first")
    from app.workers.onboarding_tasks import build_workspace_plan
    task = build_workspace_plan.apply_async(args=[current_user["tenant_id"]], queue="ai")
    return {"queued": True, "task_id": task.id}


class AutonomyIn(BaseModel):
    level: str


@router.post("/skip")
async def skip_onboarding(current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Mark onboarding complete without the guided setup — so a user is never trapped on
    the wizard (e.g. if the AI consultant is temporarily unavailable). Keeps existing
    autonomy; leaves everything else untouched."""
    require_admin(current_user)
    t = await _tenant(current_user["tenant_id"], db)
    t.onboarding_done = True
    await db.commit()
    await _start_auto_scraping(db, t)
    return {"onboarding_done": True}


@router.post("/autonomy")
async def set_autonomy(body: AutonomyIn, current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    require_admin(current_user)
    if body.level not in AUTONOMY_LEVELS:
        raise HTTPException(status_code=400, detail=f"level must be one of {AUTONOMY_LEVELS}")
    t = await _tenant(current_user["tenant_id"], db)
    t.autonomy = body.level
    # Full autopilot implies auto-approving qualified leads.
    t.auto_approve = (body.level == "full")
    await db.commit()
    return {"autonomy": t.autonomy, "auto_approve": t.auto_approve}


class ApplyIn(BaseModel):
    plan: Dict[str, Any]
    autonomy: Optional[str] = None


@router.post("/apply")
async def apply(body: ApplyIn, current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Materialize the (possibly edited) draft plan into real templates, a sequence, a
    conversion flow, an A/B test, and a ready campaign. Idempotency is the caller's job
    (this creates fresh rows each time)."""
    from app.models.models import (
        MessageTemplate, Sequence, SequenceStep, ConversionFlow,
        ABTest, ABVariant, Campaign,
    )
    require_admin(current_user)
    tid = current_user["tenant_id"]
    t = await _tenant(tid, db)
    plan = body.plan or {}
    # Bound what a single apply can create (a crafted plan shouldn't spawn unbounded rows).
    if len(plan.get("templates") or []) > 20 or len((plan.get("sequence") or {}).get("steps") or []) > 20:
        raise HTTPException(status_code=400, detail="Plan too large")
    created = {"templates": 0, "sequence": None, "flow": None, "ab_test": None, "campaign": None}

    # 1) Templates — keep their created ids so sequence steps can reference them.
    tmpl_ids: List[str] = []
    for tpl in (plan.get("templates") or []):
        m = MessageTemplate(
            tenant_id=tid, name=tpl.get("name", "قالب"), channel=tpl.get("channel", "whatsapp"),
            category="outreach", subject=tpl.get("subject"), body=tpl.get("body", ""),
        )
        db.add(m)
        await db.flush()
        tmpl_ids.append(m.id)
        created["templates"] += 1

    # 2) Sequence + steps (steps may reference a template by index via template_ref).
    seq_id = None
    seq = plan.get("sequence") or {}
    if seq.get("steps"):
        s = Sequence(tenant_id=tid, name=seq.get("name", "التسلسل الافتراضي"), active=True)
        db.add(s)
        await db.flush()
        for i, st in enumerate(seq["steps"]):
            ref = st.get("template_ref")
            tpl_id = tmpl_ids[ref] if isinstance(ref, int) and 0 <= ref < len(tmpl_ids) else None
            db.add(SequenceStep(
                sequence_id=s.id, step_order=i, delay_hours=int(st.get("delay_hours", 0)),
                channel=st.get("channel", "whatsapp"), template_id=tpl_id,
                subject=st.get("subject"), body=None if tpl_id else st.get("body"),
            ))
        seq_id = s.id
        created["sequence"] = seq_id

    # 3) Conversion flow.
    flow = plan.get("flow") or {}
    if flow.get("type"):
        f = ConversionFlow(tenant_id=tid, name=flow.get("name", "تحويل"), type=flow["type"], config={})
        db.add(f)
        created["flow"] = flow["type"]

    # 4) A/B test on the opener (variant A = first template, B = provided body).
    ab = plan.get("ab_test") or {}
    if ab.get("variant_b_body") and (plan.get("templates") or []):
        opener = plan["templates"][0]
        test = ABTest(tenant_id=tid, name=ab.get("name", "اختبار الافتتاحية"), channel="whatsapp", status="active")
        db.add(test)
        await db.flush()
        db.add(ABVariant(test_id=test.id, label="A", body=opener.get("body", "")))
        db.add(ABVariant(test_id=test.id, label="B", body=ab["variant_b_body"]))
        created["ab_test"] = test.id

    # 5) Campaign binding the audience to the sequence (starts as draft for launch).
    if seq_id:
        icp = plan.get("icp") or {}
        c = Campaign(
            tenant_id=tid, name=plan.get("campaign_name", "حملتي الأولى"), channel="whatsapp",
            sequence_id=seq_id, audience_filter={}, auto_enroll=True, status="draft",
        )
        db.add(c)
        await db.flush()
        created["campaign"] = c.id
        if isinstance(icp.get("min_bant_score"), int):
            t.min_bant_score = icp["min_bant_score"]

    # Autonomy + mark onboarding complete; clear the stored draft.
    if body.autonomy in AUTONOMY_LEVELS:
        t.autonomy = body.autonomy
        t.auto_approve = (body.autonomy == "full")
    prof = dict(t.tenant_profile or {})
    prof.pop("_build_draft", None)
    t.tenant_profile = prof
    t.onboarding_done = True

    await db.commit()
    await _start_auto_scraping(db, t)
    return {"applied": True, "created": created, "autonomy": t.autonomy}
