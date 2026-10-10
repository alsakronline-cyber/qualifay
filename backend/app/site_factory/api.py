"""Site Factory API — dashboard routes (auth) + public preview/live pages (no auth)."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user, require_admin_dep
from app.core.database import get_db
from app.models.models import SiteFactoryCampaign, SiteProspect
from app.site_factory import service, state as S
from app.site_factory.segments import SEGMENTS
from app.site_factory import insights

router = APIRouter()
public_router = APIRouter()


# ── schemas ─────────────────────────────────────────────────────────────────

class CampaignIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    segment: str
    areas: List[str] = Field(default_factory=list, max_length=20)
    keywords: List[str] = Field(default_factory=list, max_length=30)
    sources: List[str] = Field(default_factory=lambda: ["google_maps", "osm"])
    price_egp: int = Field(default=4500, ge=0, le=500000)
    max_new_per_day: int = Field(default=25, ge=1, le=200)
    max_intros_per_day: int = Field(default=15, ge=1, le=60)
    instapay_handle: Optional[str] = None
    service_prices: dict = Field(default_factory=dict)
    sender_name: str = "محمد"
    brand_name: str = "Sdiek Marketing"
    active: bool = True


class BulkIds(BaseModel):
    ids: List[str] = Field(min_length=1, max_length=200)


class AssignIn(BaseModel):
    ids: List[str] = Field(min_length=1, max_length=200)
    user_id: Optional[str] = None      # None = unassign


class ManualPaid(BaseModel):
    reference: str = Field(min_length=2, max_length=120)


def _campaign(c: SiteFactoryCampaign) -> dict:
    return {k: getattr(c, k) for k in (
        "id", "name", "segment", "areas", "keywords", "sources", "price_egp", "max_new_per_day",
        "max_intros_per_day", "instapay_handle", "service_prices", "sender_name", "brand_name", "active")} | {
        "last_discovery_at": c.last_discovery_at.isoformat() if c.last_discovery_at else None}


def _prospect(p: SiteProspect, detail: bool = False) -> dict:
    d = {
        "id": p.id, "campaign_id": p.campaign_id, "business_name": p.business_name, "segment": p.segment,
        "gap": p.gap, "phone": p.phone if not (p.phone or "").startswith("purged:") else None,
        "city": p.city, "source": p.source, "status": p.status, "wa_reachable": p.wa_reachable,
        "approved": bool(p.intro_approved_by), "followups_sent": p.followups_sent,
        "score": p.score, "tier": insights.tier(p.score or 0), "score_reasons": p.score_reasons or [],
        "services": p.services or [], "package_egp": insights.package_total(p.services or []),
        "assigned_to": p.assigned_to,
        "preview_url": service.preview_url(p) if p.preview_token else None,
        "live_url": service.live_url(p) if p.live_slug else None,
        "last_inbound": p.last_inbound,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "last_event_at": p.last_event_at.isoformat() if p.last_event_at else None,
    }
    if detail:
        d |= {"profile": p.profile, "copy": p.site_copy, "events": p.events,
              "preview_expires_at": p.preview_expires_at.isoformat() if p.preview_expires_at else None}
    return d


async def _own(db: AsyncSession, model, obj_id: str, tenant_id: str):
    obj = await db.get(model, obj_id)
    if not obj or obj.tenant_id != tenant_id:
        raise HTTPException(404, "Not found")
    return obj


# ── campaigns ───────────────────────────────────────────────────────────────

@router.get("/campaigns")
async def list_campaigns(user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(SiteFactoryCampaign).where(SiteFactoryCampaign.tenant_id == user["tenant_id"])
                             .order_by(desc(SiteFactoryCampaign.created_at)))).scalars().all()
    return [_campaign(c) for c in rows]


@router.post("/campaigns")
async def create_campaign(body: CampaignIn, user=Depends(require_admin_dep), db: AsyncSession = Depends(get_db)):
    if body.segment not in SEGMENTS:
        raise HTTPException(422, f"segment must be one of {SEGMENTS}")
    c = SiteFactoryCampaign(tenant_id=user["tenant_id"], **body.model_dump())
    db.add(c)
    await db.commit()
    return _campaign(c)


@router.put("/campaigns/{cid}")
async def update_campaign(cid: str, body: CampaignIn, user=Depends(require_admin_dep), db: AsyncSession = Depends(get_db)):
    c = await _own(db, SiteFactoryCampaign, cid, user["tenant_id"])
    if body.segment not in SEGMENTS:
        raise HTTPException(422, f"segment must be one of {SEGMENTS}")
    for k, v in body.model_dump().items():
        setattr(c, k, v)
    await db.commit()
    return _campaign(c)


@router.post("/campaigns/{cid}/discover")
async def run_discovery_now(cid: str, user=Depends(require_admin_dep), db: AsyncSession = Depends(get_db)):
    await _own(db, SiteFactoryCampaign, cid, user["tenant_id"])
    from app.site_factory.tasks import discover_campaign
    discover_campaign.apply_async(args=[cid], queue="scrape")
    return {"queued": True}


# ── prospects ───────────────────────────────────────────────────────────────

@router.get("/stats")
async def stats(user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(SiteProspect.status, func.count(SiteProspect.id))
                             .where(SiteProspect.tenant_id == user["tenant_id"]).group_by(SiteProspect.status))).all()
    return {s: n for s, n in rows}


@router.get("/prospects")
async def list_prospects(status: Optional[str] = None, campaign_id: Optional[str] = None, assigned: Optional[str] = None,
                         min_score: Optional[int] = None, sort: str = "score", limit: int = 100,
                         user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """`assigned`: "me" | "none" | <user_id>. `sort`: "score" (best first) | "recent"."""
    q = select(SiteProspect).where(SiteProspect.tenant_id == user["tenant_id"])
    if status:
        q = q.where(SiteProspect.status.in_(status.split(",")))
    if campaign_id:
        q = q.where(SiteProspect.campaign_id == campaign_id)
    if assigned == "me":
        q = q.where(SiteProspect.assigned_to == user["user_id"])
    elif assigned == "none":
        q = q.where(SiteProspect.assigned_to.is_(None))
    elif assigned:
        q = q.where(SiteProspect.assigned_to == assigned)
    if min_score is not None:
        q = q.where(SiteProspect.score >= min_score)
    order = [desc(SiteProspect.score).nullslast(), desc(SiteProspect.last_event_at)] if sort == "score" else [desc(SiteProspect.last_event_at)]
    rows = (await db.execute(q.order_by(*order).limit(min(limit, 500)))).scalars().all()
    return [_prospect(p) for p in rows]


@router.get("/prospects/{pid}")
async def get_prospect(pid: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return _prospect(await _own(db, SiteProspect, pid, user["tenant_id"]), detail=True)


@router.post("/prospects/approve")
async def approve_intros(body: BulkIds, user=Depends(require_admin_dep), db: AsyncSession = Depends(get_db)):
    """The human gate: only approved prospects ever receive an intro."""
    ok, skipped = 0, 0
    for pid in body.ids:
        p = await db.get(SiteProspect, pid)
        if not p or p.tenant_id != user["tenant_id"] or p.status != S.AWAITING_APPROVAL:
            skipped += 1
            continue
        await service.approve(db, p, user["user_id"])
        ok += 1
    return {"approved": ok, "skipped": skipped}


@router.post("/prospects/assign")
async def assign_prospects(body: AssignIn, user=Depends(require_admin_dep), db: AsyncSession = Depends(get_db)):
    """Give prospects to a team member (or unassign). The assignee must be in the same company."""
    from app.models.models import User
    if body.user_id:
        member = await db.get(User, body.user_id)
        if not member or member.tenant_id != user["tenant_id"]:
            raise HTTPException(422, "Unknown team member")
    n = 0
    for pid in body.ids:
        p = await db.get(SiteProspect, pid)
        if p and p.tenant_id == user["tenant_id"]:
            p.assigned_to = body.user_id
            service.log_event(p, "assigned", body.user_id or "unassigned")
            n += 1
    await db.commit()
    return {"assigned": n}


@router.post("/prospects/reject")
async def reject_prospects(body: BulkIds, user=Depends(require_admin_dep), db: AsyncSession = Depends(get_db)):
    ok = 0
    for pid in body.ids:
        p = await db.get(SiteProspect, pid)
        if p and p.tenant_id == user["tenant_id"] and S.can_transition(p.status, S.REJECTED):
            await service.reject(db, p, user["user_id"])
            ok += 1
    return {"rejected": ok}


@router.post("/prospects/{pid}/rebuild")
async def rebuild(pid: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Re-render the preview (e.g. after editing copy following a change request)."""
    p = await _own(db, SiteProspect, pid, user["tenant_id"])
    if not p.site_key or p.status in S.TERMINAL:
        raise HTTPException(409, "No preview to rebuild")
    ok = service.store_site(p, preview=p.status != S.LIVE)
    await db.commit()
    return {"ok": ok}


class CopyPatch(BaseModel):
    fields: dict


@router.put("/prospects/{pid}/copy")
async def edit_copy(pid: str, body: CopyPatch, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    p = await _own(db, SiteProspect, pid, user["tenant_id"])
    merged = dict(p.site_copy or {})
    for k, v in body.fields.items():
        if k in {"tagline_ar", "tagline_en", "intro_ar", "intro_en", "cta_ar", "cta_en"} and isinstance(v, str):
            merged[k] = v.strip()[:400]
        elif k in {"about_ar", "about_en"} and isinstance(v, list) and all(isinstance(x, str) for x in v):
            merged[k] = [x.strip()[:1000] for x in v[:6]]
        elif k == "services" and isinstance(v, list) and all(isinstance(x, dict) and x.get("name_ar") for x in v):
            merged[k] = [{f: str(x.get(f, ""))[:400] for f in ("name_ar", "name_en", "desc_ar", "desc_en")} for x in v[:8]]
    p.site_copy = merged
    service.log_event(p, "copy_edited", user["user_id"])
    await db.commit()
    return await rebuild(pid, user, db)


@router.post("/prospects/{pid}/resend-preview")
async def resend_preview(pid: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """After edits on a change request: send the updated preview (consent already given)."""
    p = await _own(db, SiteProspect, pid, user["tenant_id"])
    if p.status != S.CHANGES_REQUESTED:
        raise HTTPException(409, "Only for prospects that requested changes")
    return {"sent": await service.send_preview(db, p)}


@router.post("/prospects/{pid}/mark-paid")
async def mark_paid_manual(pid: str, body: ManualPaid, user=Depends(require_admin_dep), db: AsyncSession = Depends(get_db)):
    """InstaPay / cash: the owner confirms the transfer and the site goes live."""
    p = await _own(db, SiteProspect, pid, user["tenant_id"])
    try:
        await service.mark_paid(db, p, ref=body.reference, by=f"manual:{user['id']}")
    except S.TransitionError as e:
        raise HTTPException(409, str(e))
    return _prospect(p)


# ── public pages (no auth) ──────────────────────────────────────────────────

CSP = ("default-src 'self'; img-src 'self' data: https:; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
       "font-src https://fonts.gstatic.com; script-src 'self'; frame-src https://www.google.com; frame-ancestors 'self'")


def _serve(prefix: str, path: str, preview: bool) -> Response:
    """Serve one file of a stored site; directories map to index.html, misses to 404.html."""
    from app.services.storage_service import get_attachment
    path = (path or "").lstrip("/")
    if ".." in path.split("/"):
        raise HTTPException(400, "Bad path")
    if path == "" or path.endswith("/"):
        path += "index.html"
    elif "." not in path.rsplit("/", 1)[-1]:
        path += "/index.html"
    data, _ = get_attachment(prefix + path)
    status = 200
    if not data:
        data, _ = get_attachment(prefix + "404.html")
        status = 404
        path = "404.html"
        if not data:
            raise HTTPException(404, "Not found")
    headers = {"Cache-Control": "no-store" if preview else "public, max-age=300", "Content-Security-Policy": CSP,
               "X-Content-Type-Options": "nosniff"}
    if preview:
        headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    return Response(content=data, status_code=status, media_type=service.content_type(path), headers=headers)


@public_router.get("/p/{token}")
async def preview_root(token: str):
    return RedirectResponse(url=f"{token}/", status_code=308)


@public_router.get("/p/{token}/{path:path}")
async def public_preview(token: str, path: str = "", db: AsyncSession = Depends(get_db)):
    p = (await db.execute(select(SiteProspect).where(SiteProspect.preview_token == token))).scalar_one_or_none()
    if not p or not p.site_key or p.status in S.TERMINAL or p.status == S.LIVE:
        raise HTTPException(404, "This preview is no longer available")
    if p.preview_expires_at and service.utcnow() > p.preview_expires_at:
        raise HTTPException(410, "This preview has expired")
    return _serve(service.site_prefix(p, "preview"), path, preview=True)


@public_router.get("/s/{slug}")
async def live_root(slug: str):
    return RedirectResponse(url=f"{slug}/", status_code=308)


@public_router.get("/s/{slug}/{path:path}")
async def public_live(slug: str, path: str = "", db: AsyncSession = Depends(get_db)):
    p = (await db.execute(select(SiteProspect).where(SiteProspect.live_slug == slug))).scalar_one_or_none()
    if not p or p.status != S.LIVE:
        raise HTTPException(404, "Site not found")
    return _serve(service.site_prefix(p, "live"), path, preview=False)
