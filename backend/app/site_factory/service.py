"""Site Factory orchestration (DB + network). Pure rules live in state/replies/builder.

Pipeline:
  discover()      Google Maps (no websiteUri) + OSM (cross-checked against Maps → no GBP)
  build()         enrich facts (Place Details), write facts-only copy, render + store preview
  approve()       human gate → status awaiting_approval → (intro queue)
  send_intro()    ask permission only; WhatsApp warmup caps + daily campaign cap + hours
  handle_reply()  yes → preview link · like → ask to proceed · buy → payment · no/stop → purge
  tick()          one follow-up per phase, then expire + purge
  mark_paid()     Paymob webhook or manual → publish live
"""
from __future__ import annotations

import hashlib
import logging
import secrets
import re
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.lib.phone import normalize_egyptian_phone
from app.models.models import (
    SiteFactoryCampaign, SiteProspect, SiteSuppression, Lead, LeadSource, LeadStage, LeadStatus, WaInstance,
)
from app.site_factory import state as S, replies as R, messages as M, payments
from app.site_factory.builder import build_site
from app.site_factory import insights
from app.site_factory.segments import KEYWORDS, PLACE_TYPES, fallback_copy

logger = logging.getLogger(__name__)
CAIRO = ZoneInfo("Africa/Cairo")
STORAGE_PREFIX = "site-factory"


# ── small helpers ───────────────────────────────────────────────────────────

def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def phone_hash(phone: str) -> str:
    return hashlib.sha256(f"site-factory:{phone}".encode()).hexdigest()


def is_mobile(phone_e164: str | None) -> bool:
    return bool(phone_e164 and re.fullmatch(r"\+201[0125]\d{8}", phone_e164))


def public_base() -> str:
    return (settings.SITE_FACTORY_PUBLIC_URL or settings.app_base_url_effective).rstrip("/")


def preview_url(p: SiteProspect) -> str:
    return f"{public_base()}/api/v1/site-factory/p/{p.preview_token}/"


def live_url(p: SiteProspect) -> str:
    return f"{public_base()}/api/v1/site-factory/s/{p.live_slug}/"


def log_event(p: SiteProspect, kind: str, detail: str = "") -> None:
    ev = list(p.events or [])
    ev.append({"at": utcnow().isoformat(timespec="seconds"), "type": kind, "detail": detail[:500]})
    p.events = ev[-60:]
    p.last_event_at = utcnow()


def set_status(p: SiteProspect, new: str, detail: str = "") -> None:
    S.assert_transition(p.status, new)
    log_event(p, f"status:{new}", detail)
    p.status = new


async def is_suppressed(db: AsyncSession, phone: str) -> bool:
    return (await db.get(SiteSuppression, phone_hash(phone))) is not None


# ── discovery ───────────────────────────────────────────────────────────────

async def _places_search(query: str, area: str, max_results: int) -> list:
    from scrapers.google_maps import GoogleMapsScraper
    out = []
    async for raw in GoogleMapsScraper().scrape({"query": query, "location": area, "max_results": max_results}, ""):
        out.append(raw)
    return out


async def _osm_search(query: str, area: str, max_results: int) -> list:
    from scrapers.osm import OSMScraper
    out = []
    async for raw in OSMScraper().scrape({"query": query, "location": area, "max_results": max_results}, ""):
        out.append(raw)
    return out


def _types_match(segment: str, types: list | None) -> bool:
    if segment == "manufacturer" or not types:
        return True   # Maps rarely tags factories precisely; keyword search already scoped it
    return bool(set(types) & PLACE_TYPES.get(segment, set()))


async def _known(db: AsyncSession, tenant_id: str, phone: str) -> bool:
    """Already a prospect, suppressed, or an unsubscribed lead → never re-add."""
    if await is_suppressed(db, phone):
        return True
    if (await db.execute(select(SiteProspect.id).where(SiteProspect.tenant_id == tenant_id, SiteProspect.phone == phone))).first():
        return True
    unsub = await db.execute(select(Lead.id).where(Lead.phone == phone, Lead.status == LeadStatus.unsubscribed))
    return unsub.first() is not None


async def discover(db: AsyncSession, campaign: SiteFactoryCampaign) -> int:
    """Find new website-gap businesses for one campaign. Returns how many were added."""
    keywords = campaign.keywords or KEYWORDS.get(campaign.segment, [])
    budget = campaign.max_new_per_day or 25
    added = 0
    for area in (campaign.areas or ["Cairo"]):
        for kw in keywords:
            if added >= budget:
                break
            candidates = []
            if "google_maps" in (campaign.sources or []) and settings.GOOGLE_MAPS_API_KEY:
                try:
                    for raw in await _places_search(kw, area, 20):
                        if raw.website or not _types_match(campaign.segment, raw.raw_data.get("types")):
                            continue
                        candidates.append((raw, "no_website", "google_maps", raw.raw_data.get("place_id")))
                except Exception as e:
                    logger.warning("site-factory maps search failed (%s / %s): %s", kw, area, e)
            if "osm" in (campaign.sources or []):
                try:
                    for raw in await _osm_search(kw, area, 25):
                        if raw.website:
                            continue
                        candidates.append((raw, "no_gbp", "osm", (raw.raw_data or {}).get("osm_id")))
                except Exception as e:
                    logger.warning("site-factory osm search failed (%s / %s): %s", kw, area, e)

            for raw, gap, source, ref in candidates:
                if added >= budget:
                    break
                phone = normalize_egyptian_phone(raw.phone) if raw.phone else None
                if not is_mobile(phone) or await _known(db, campaign.tenant_id, phone):
                    continue
                if source == "osm" and settings.GOOGLE_MAPS_API_KEY:
                    # Cross-check: an OSM business that IS on Maps with a website is not a prospect;
                    # one on Maps without a website is a no_website prospect, not no_gbp.
                    try:
                        hits = await _places_search(raw.name or raw.company or "", area, 1)
                    except Exception:
                        hits = []
                    if hits and hits[0].website:
                        continue
                    if hits:
                        gap, ref = "no_website", hits[0].raw_data.get("place_id") or ref
                p = SiteProspect(
                    tenant_id=campaign.tenant_id, campaign_id=campaign.id,
                    business_name=(raw.name or raw.company or "").strip()[:200] or "—",
                    segment=campaign.segment, gap=gap, phone=phone, city=raw.city or area,
                    source=source, source_ref=str(ref) if ref else None,
                    profile={
                        "name": raw.name or raw.company, "name_en": raw.name if source == "google_maps" else None,
                        "phone": phone, "city": raw.city or area,
                        "address": (raw.raw_data or {}).get("formatted_address"),
                        "category": raw.industry, "place_id": (raw.raw_data or {}).get("place_id"),
                        "location": (raw.raw_data or {}).get("location"),
                        "rating": (raw.raw_data or {}).get("rating"),
                        "reviews": (raw.raw_data or {}).get("user_ratings_total"),
                        "links": _osm_links(raw.raw_data or {}),
                    },
                    status=S.FOUND, events=[],
                )
                apply_insights(p, campaign)
                log_event(p, "found", f"{source} · {kw} · {area} · {gap}")
                try:
                    async with db.begin_nested():   # savepoint: a (tenant, phone) race skips one row only
                        db.add(p)
                    added += 1
                except Exception:
                    logger.info("site-factory duplicate skipped: %s", phone)
    campaign.last_discovery_at = utcnow()
    await db.commit()
    return added


def _osm_links(raw: dict) -> dict:
    tags = raw.get("tags") or {}
    links = {}
    for k in ("facebook", "instagram"):
        v = tags.get(f"contact:{k}") or tags.get(k)
        if isinstance(v, str) and v.startswith("https://"):
            links[k] = v
    return links


# ── enrichment + build ──────────────────────────────────────────────────────

async def _place_details(place_id: str) -> dict:
    """Opening hours + Maps category for the site. Only called for prospects being built."""
    if not (place_id and settings.GOOGLE_MAPS_API_KEY):
        return {}
    headers = {
        "X-Goog-Api-Key": settings.GOOGLE_MAPS_API_KEY,
        "X-Goog-FieldMask": "displayName,regularOpeningHours.weekdayDescriptions,primaryTypeDisplayName,googleMapsUri",
    }
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.get(f"https://places.googleapis.com/v1/places/{place_id}?languageCode=ar", headers=headers)
        if r.status_code != 200:
            return {}
        d = r.json()
        return {
            "name_ar": (d.get("displayName") or {}).get("text"),
            "hours": (d.get("regularOpeningHours") or {}).get("weekdayDescriptions") or [],
            "category": (d.get("primaryTypeDisplayName") or {}).get("text"),
            "maps_url": d.get("googleMapsUri"),
        }
    except Exception as e:
        logger.info("place details failed for %s: %s", place_id, e)
        return {}


COPY_PROMPT = """أنت كاتب محتوى ومتخصص SEO لمواقع الأعمال في مصر. اكتب نصوص موقع متعدد الصفحات لهذا النشاط.
القواعد الصارمة:
- استخدم فقط الحقائق الموجودة في JSON. لا تخترع أسعارًا أو سنوات خبرة أو شهادات أو جوائز أو أرقامًا أو أسماء عملاء أو منتجات محددة غير مذكورة.
- للعيادات: لا وعود علاجية ولا ادعاءات طبية، فقط تعريف بالعيادة وطريقة الحجز.
- الخدمات: 3 إلى 6 بنود معتادة لهذا النوع من النشاط بصياغة عامة محايدة، ولكل بند وصف من جملتين يشرح كيف يطلبها العميل.
- اكتب بالعربية الفصحى البسيطة مع ترجمة إنجليزية طبيعية، وضمّن اسم النشاط والمدينة بشكل طبيعي (SEO محلي).
أعد JSON فقط بهذا الشكل:
{{"tagline_ar": "...", "tagline_en": "...", "intro_ar": "جملتان", "intro_en": "...",
 "about_ar": ["فقرة", "فقرة"], "about_en": ["...", "..."],
 "services": [{{"name_ar": "...", "name_en": "...", "desc_ar": "...", "desc_en": "..."}}],
 "cta_ar": "...", "cta_en": "..."}}
الحقائق: {facts}"""


def clean_copy(data: dict, base: dict) -> dict:
    """Keep only well-formed fields from the LLM; anything malformed falls back to `base`."""
    out = dict(base)
    for k in ("tagline_ar", "tagline_en", "intro_ar", "intro_en", "cta_ar", "cta_en"):
        v = data.get(k)
        if isinstance(v, str) and v.strip():
            out[k] = v.strip()[:300 if k.startswith("intro") else 140]
    for k in ("about_ar", "about_en"):
        v = data.get(k)
        if isinstance(v, list) and v and all(isinstance(x, str) and x.strip() for x in v):
            out[k] = [x.strip()[:700] for x in v[:4]]
    svcs = data.get("services")
    if isinstance(svcs, list):
        good = [{f: str(x.get(f, "")).strip()[:400] for f in ("name_ar", "name_en", "desc_ar", "desc_en")}
                for x in svcs if isinstance(x, dict) and str(x.get("name_ar", "")).strip()]
        if len(good) >= 3:
            out["services"] = good[:6]
    return out


async def write_copy(p: SiteProspect) -> dict:
    prof = p.profile or {}
    base = fallback_copy(p.segment, p.business_name, p.city, prof.get("category"))
    try:
        import json
        from app.services.ai_service import ai_service
        facts = {k: prof.get(k) for k in ("name", "category", "city", "address", "hours")}
        facts["segment"] = p.segment
        text = await ai_service._or_fast(
            [{"role": "user", "content": COPY_PROMPT.format(facts=json.dumps(facts, ensure_ascii=False))}], max_tokens=1800)
        data = ai_service._parse_json(text, {})
        return clean_copy(data, base) if isinstance(data, dict) else base
    except Exception as e:
        logger.info("copywriter fell back for %s: %s", p.id, e)
        return base


def apply_insights(p: SiteProspect, campaign: SiteFactoryCampaign | None) -> None:
    """Score + recommended services from what exists about the business online."""
    prof = p.profile or {}
    common = dict(segment=p.segment, gap=p.gap, reviews=prof.get("reviews"),
                  has_hours=bool(prof.get("hours")), wa_reachable=p.wa_reachable,
                  social_links=len(prof.get("links") or {}))
    p.score, p.score_reasons = insights.score(rating=prof.get("rating"), has_address=bool(prof.get("address")), **common)
    p.services = insights.recommend(prices=(campaign.service_prices if campaign else None), **common)


async def _check_whatsapp(db: AsyncSession, tenant_id: str, phone: str) -> Optional[bool]:
    from app.services.evolution_service import evolution_service
    inst = (await db.execute(select(WaInstance).where(
        WaInstance.tenant_id == tenant_id, WaInstance.status.in_(["open", "connected"])).limit(1))).scalar_one_or_none()
    if not inst:
        return None
    try:
        return await evolution_service.check_number(inst.instance_name, phone.replace("+", ""))
    except Exception:
        return None


CONTENT_TYPES = {"html": "text/html; charset=utf-8", "css": "text/css; charset=utf-8", "js": "text/javascript; charset=utf-8",
                 "xml": "application/xml; charset=utf-8", "txt": "text/plain; charset=utf-8"}


def content_type(path: str) -> str:
    return CONTENT_TYPES.get(path.rsplit(".", 1)[-1] if "." in path else "", "application/octet-stream")


def site_prefix(p: SiteProspect, kind: str) -> str:
    return f"{STORAGE_PREFIX}/{p.tenant_id}/{p.id}/{kind}/"


def render_files(p: SiteProspect, preview: bool) -> dict[str, str]:
    if preview:
        base = f"/api/v1/site-factory/p/{p.preview_token}/"
        expires = p.preview_expires_at.date().isoformat() if p.preview_expires_at else None
    else:
        base = f"/api/v1/site-factory/s/{p.live_slug}/"
        expires = None
    return build_site(profile=p.profile or {}, copy=p.site_copy or {}, segment=p.segment, base=base, preview=preview,
                      expires_on=expires, brand_url=settings.SITE_FACTORY_BRAND_URL, site_url=public_base() + base)


def store_site(p: SiteProspect, preview: bool) -> bool:
    """Render every page and upload under the prospect's prefix. Returns False on any failure."""
    from app.services.storage_service import upload_attachment
    prefix = site_prefix(p, "preview" if preview else "live")
    ok = all(upload_attachment(prefix + path, text.encode("utf-8"), content_type(path))
             for path, text in render_files(p, preview).items())
    if ok:
        p.site_key = prefix
    return ok


def delete_site_files(p: SiteProspect) -> None:
    from app.services.storage_service import _client, BUCKET
    try:
        c = _client()
        for obj in c.list_objects(BUCKET, prefix=f"{STORAGE_PREFIX}/{p.tenant_id}/{p.id}/", recursive=True):
            c.remove_object(BUCKET, obj.object_name)
    except Exception as e:
        logger.info("site file cleanup failed for %s: %s", p.id, e)


async def build(db: AsyncSession, p: SiteProspect) -> bool:
    """found → built → awaiting_approval (or unreachable)."""
    reach = await _check_whatsapp(db, p.tenant_id, p.phone)
    p.wa_reachable = reach
    if reach is False:
        set_status(p, S.UNREACHABLE, "not on WhatsApp")
        await db.commit()
        return False

    details = await _place_details((p.profile or {}).get("place_id"))
    prof = dict(p.profile or {})
    name_ar = details.pop("name_ar", None)
    if name_ar and name_ar != prof.get("name"):
        # Search ran in English, details in Arabic: keep both so each language shows its own name.
        prof["name_en"] = prof.get("name_en") or prof.get("name")
        prof["name"] = name_ar
        p.business_name = name_ar[:200]
    for k, v in details.items():
        if v and not prof.get(k):
            prof[k] = v
    p.profile = prof
    p.site_copy = await write_copy(p)
    campaign = await db.get(SiteFactoryCampaign, p.campaign_id) if p.campaign_id else None
    apply_insights(p, campaign)
    p.preview_token = p.preview_token or secrets.token_urlsafe(18)
    p.preview_expires_at = utcnow() + S.PREVIEW_TTL
    if not store_site(p, preview=True):
        log_event(p, "build_failed", "storage upload failed")
        await db.commit()
        return False
    set_status(p, S.BUILT, "preview rendered")
    set_status(p, S.AWAITING_APPROVAL, "waiting for a human to approve the intro")
    await db.commit()
    return True


# ── human gate ──────────────────────────────────────────────────────────────

async def approve(db: AsyncSession, p: SiteProspect, user_id: str) -> None:
    if p.status != S.AWAITING_APPROVAL:
        raise S.TransitionError(f"cannot approve from {p.status}")
    p.intro_approved_by = user_id
    log_event(p, "approved", user_id)
    await db.commit()


async def reject(db: AsyncSession, p: SiteProspect, user_id: str) -> None:
    set_status(p, S.REJECTED, f"by {user_id}")
    await purge(db, p, reason="rejected", suppress=False)


# ── sending ─────────────────────────────────────────────────────────────────

async def _pick_instance(db: AsyncSession, tenant_id: str) -> Optional[WaInstance]:
    from app.services.warmup_service import warmup_service
    rows = (await db.execute(select(WaInstance).where(
        WaInstance.tenant_id == tenant_id,
        WaInstance.status.in_(["open", "connected"]),
        WaInstance.paused == False,  # noqa: E712
    ))).scalars().all()
    for inst in rows:
        allowed, _, _ = await warmup_service.check_wa_limit(inst.id, db)
        if allowed:
            return inst
    return None


async def send_wa(db: AsyncSession, p: SiteProspect, text: str, count_against_cap: bool = True) -> bool:
    """Send one message. Replies inside an active conversation still respect the number's
    pause state but are not blocked by the cold-outreach cap."""
    from app.services.evolution_service import evolution_service
    from app.services.warmup_service import warmup_service
    if count_against_cap:
        inst = await _pick_instance(db, p.tenant_id)
    else:
        inst = (await db.execute(select(WaInstance).where(
            WaInstance.tenant_id == p.tenant_id, WaInstance.status.in_(["open", "connected"]),
            WaInstance.paused == False).limit(1))).scalar_one_or_none()  # noqa: E712
    if not inst:
        log_event(p, "send_skipped", "no WhatsApp number with capacity")
        return False
    try:
        await evolution_service.send_text(inst.instance_name, f"{p.phone.replace('+', '')}@s.whatsapp.net", text)
    except Exception as e:
        log_event(p, "send_failed", str(e))
        return False
    if count_against_cap:
        await warmup_service.increment_wa_sent(inst.id, db)
    log_event(p, "sent", text[:120])
    return True


async def _ensure_lead(db: AsyncSession, p: SiteProspect) -> None:
    """Mirror the prospect into the CRM so the conversation shows up in the shared inbox."""
    if p.lead_id:
        return
    existing = (await db.execute(select(Lead).where(Lead.tenant_id == p.tenant_id, Lead.phone == p.phone))).scalar_one_or_none()
    if existing:
        p.lead_id = existing.id
        return
    lead = Lead(
        tenant_id=p.tenant_id, source=LeadSource.google_maps if p.source == "google_maps" else LeadSource.web_scrape,
        name=p.business_name, company=p.business_name, phone=p.phone, city=p.city, industry=p.segment,
        stage=LeadStage.outreach, wa_reachable=p.wa_reachable,
        raw_data={"site_factory_prospect": p.id, "gap": p.gap}, language="ar",
    )
    db.add(lead)
    await db.flush()
    p.lead_id = lead.id


async def intros_sent_today(db: AsyncSession, campaign_id: str) -> int:
    start = datetime.now(CAIRO).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc).replace(tzinfo=None)
    return (await db.execute(select(func.count(SiteProspect.id)).where(
        SiteProspect.campaign_id == campaign_id, SiteProspect.intro_sent_at >= start))).scalar() or 0


async def send_intro(db: AsyncSession, p: SiteProspect, campaign: SiteFactoryCampaign, now_cairo: datetime | None = None) -> bool:
    ok, why = S.may_send_intro(p.status, p.intro_approved_by, await is_suppressed(db, p.phone), p.wa_reachable)
    if not ok:
        log_event(p, "intro_blocked", why)
        return False
    if not S.in_send_window(now_cairo or datetime.now(CAIRO)):
        return False
    if await intros_sent_today(db, campaign.id) >= (campaign.max_intros_per_day or 15):
        return False
    text = M.intro(p.business_name, campaign.sender_name or "محمد", campaign.brand_name or "Sdiek Marketing", p.gap)
    if not await send_wa(db, p, text):
        await db.commit()
        return False
    await _ensure_lead(db, p)
    p.intro_sent_at = utcnow()
    p.followups_sent = 0
    set_status(p, S.INTRO_SENT)
    await db.commit()
    return True


async def send_preview(db: AsyncSession, p: SiteProspect) -> bool:
    ok, why = S.may_send_preview(p.status, p.opted_in_at)
    if not ok:
        log_event(p, "preview_blocked", why)
        await db.commit()
        return False
    p.preview_expires_at = utcnow() + S.PREVIEW_TTL
    days = S.PREVIEW_TTL.days
    if not await send_wa(db, p, M.preview(p.business_name, preview_url(p), days), count_against_cap=False):
        await db.commit()
        return False
    p.preview_sent_at = utcnow()
    p.followups_sent = 0
    set_status(p, S.PREVIEW_SENT)
    await db.commit()
    return True


async def send_payment(db: AsyncSession, p: SiteProspect, campaign: SiteFactoryCampaign | None) -> bool:
    price = (campaign.price_egp if campaign else None) or 4500
    link = await payments.create_checkout_link(prospect_id=p.id, business=p.business_name, phone=p.phone, amount_egp=price)
    text = M.payment(p.business_name, price, link, campaign.instapay_handle if campaign else None)
    if not await send_wa(db, p, text, count_against_cap=False):
        await db.commit()
        return False
    p.payment_sent_at = utcnow()
    p.followups_sent = 0
    set_status(p, S.PAYMENT_SENT, "card link" if link else "manual/InstaPay")
    await db.commit()
    return True


# ── replies ─────────────────────────────────────────────────────────────────

async def find_active_by_phone(db: AsyncSession, phone: str) -> Optional[SiteProspect]:
    return (await db.execute(select(SiteProspect).where(
        SiteProspect.phone == phone, SiteProspect.status.in_(S.ACTIVE_CONVERSATION)
    ).order_by(SiteProspect.last_event_at.desc()).limit(1))).scalar_one_or_none()


async def _llm_intent(text: str, status: str) -> str:
    """Second opinion when the rules can't place a reply. Constrained to known labels."""
    try:
        from app.services.ai_service import ai_service
        prompt = (
            "Classify this WhatsApp reply from an Egyptian business owner. Context: "
            + ("we asked if they want to see a free website preview." if status == S.INTRO_SENT
               else "we sent them a website preview and asked if they want to buy it.")
            + " Answer with exactly one word from: yes, no, like, buy, changes, question, cancel, unknown.\n"
            f"Reply: {text[:500]}"
        )
        out = (await ai_service._or_fast([{"role": "user", "content": prompt}], max_tokens=5)).strip().lower()
        allowed = {R.YES, R.NO, R.LIKE, R.BUY, R.CHANGES, R.QUESTION, R.CANCEL}
        out = out.split()[0] if out else ""
        if status == S.INTRO_SENT and out in {R.LIKE, R.BUY}:
            out = R.YES
        return out if out in allowed else R.UNKNOWN
    except Exception:
        return R.UNKNOWN


async def _notify_owner(db: AsyncSession, p: SiteProspect, title: str, body: str, urgent: bool = False) -> None:
    try:
        from app.services.notification_service import notify
        from app.models.models import NotificationType
        await notify(db, p.tenant_id, NotificationType.system, title, body, data={"site_prospect_id": p.id}, urgent=urgent)
    except Exception as e:
        logger.info("site-factory notify failed: %s", e)


async def handle_reply(db: AsyncSession, p: SiteProspect, text: str) -> str:
    """Advance the funnel from a business's reply. Returns the intent acted on."""
    p.last_inbound = (text or "")[:1000]
    intent = R.classify(text, p.status)
    if intent == R.UNKNOWN:
        intent = await _llm_intent(text, p.status)
    log_event(p, f"reply:{intent}", text[:200])
    campaign = await db.get(SiteFactoryCampaign, p.campaign_id) if p.campaign_id else None

    if intent == R.STOP or intent == R.CANCEL:
        await send_wa(db, p, M.goodbye_deleted(), count_against_cap=False)
        set_status(p, S.CANCELLED, intent)
        await purge(db, p, reason=intent)
        return intent

    if intent == R.NO:
        await send_wa(db, p, M.goodbye_deleted(), count_against_cap=False)
        set_status(p, S.DECLINED if S.can_transition(p.status, S.DECLINED) else S.CANCELLED, "no")
        await purge(db, p, reason="declined")
        return intent

    if p.status == S.INTRO_SENT:
        if intent == R.YES:
            p.opted_in_at = utcnow()
            set_status(p, S.OPTED_IN, "consent: replied yes")
            await db.commit()
            await send_preview(db, p)
        elif intent == R.QUESTION:
            await _notify_owner(db, p, "Site Factory: سؤال قبل المعاينة", f"{p.business_name}: {text[:300]}")
            await db.commit()
        else:
            await _notify_owner(db, p, "Site Factory: رد غير واضح", f"{p.business_name}: {text[:300]}")
            await db.commit()
        return intent

    if intent == R.BUY and p.status in {S.PREVIEW_SENT, S.CHANGES_REQUESTED}:
        await send_payment(db, p, campaign)
    elif intent == R.LIKE and p.status in {S.PREVIEW_SENT, S.CHANGES_REQUESTED}:
        await send_wa(db, p, M.ask_to_proceed(), count_against_cap=False)
        await db.commit()
    elif intent == R.CHANGES:
        await send_wa(db, p, M.changes_ack(), count_against_cap=False)
        if p.status != S.CHANGES_REQUESTED:
            set_status(p, S.CHANGES_REQUESTED, text[:200])
        await _notify_owner(db, p, "Site Factory: طلب تعديل", f"{p.business_name}: {text[:300]}", urgent=True)
        await db.commit()
    elif intent == R.QUESTION:
        t = R.normalize(text)
        if any(k in t for k in ("بكام", "كام", "السعر", "سعر", "price", "how much", "cost")):
            await send_wa(db, p, M.price_answer((campaign.price_egp if campaign else None) or 4500), count_against_cap=False)
        else:
            await send_wa(db, p, M.handoff(), count_against_cap=False)
            await _notify_owner(db, p, "Site Factory: سؤال", f"{p.business_name}: {text[:300]}")
        await db.commit()
    else:
        await _notify_owner(db, p, "Site Factory: رد يحتاج متابعة", f"{p.business_name}: {text[:300]}")
        await db.commit()
    return intent


async def on_stop_keyword(db: AsyncSession, phone: str) -> None:
    """Called from the webhook's synchronous STOP path: end any Site Factory conversation."""
    p = (await db.execute(select(SiteProspect).where(
        SiteProspect.phone == phone, SiteProspect.status.notin_(S.TERMINAL | {S.PAID, S.LIVE})))).scalars().all()
    for row in p:
        if S.can_transition(row.status, S.CANCELLED):
            set_status(row, S.CANCELLED, "stop keyword")
        await purge(db, row, reason="stop")
    if not p:
        db.add(SiteSuppression(phone_hash=phone_hash(phone), reason="stop"))
        try:
            await db.commit()
        except Exception:
            await db.rollback()


# ── scheduler ───────────────────────────────────────────────────────────────

async def tick(db: AsyncSession, p: SiteProspect, now: datetime | None = None) -> Optional[str]:
    """One follow-up per phase, then expire. Returns the action taken."""
    now = now or utcnow()
    action = S.due_action(p.status, p.last_event_at or p.created_at, p.followups_sent or 0, now)
    if action == "followup" and S.in_send_window(datetime.now(CAIRO)):
        text = {S.INTRO_SENT: M.intro_followup(p.business_name), S.PREVIEW_SENT: M.preview_followup(p.business_name),
                S.PAYMENT_SENT: M.payment_followup()}[p.status]
        if await send_wa(db, p, text, count_against_cap=(p.status == S.INTRO_SENT)):
            p.followups_sent = (p.followups_sent or 0) + 1
        await db.commit()
        return "followup"
    if action == "expire":
        set_status(p, S.EXPIRED, "no reply")
        await purge(db, p, reason="expired", suppress=p.intro_sent_at is not None)
        return "expire"
    # Previews that were never sent still expire after the TTL.
    if p.status in {S.BUILT, S.AWAITING_APPROVAL} and p.preview_expires_at and now > p.preview_expires_at + S.PREVIEW_TTL:
        set_status(p, S.REJECTED, "never approved")
        await purge(db, p, reason="stale", suppress=False)
        return "stale"
    return None


# ── payment + publish ───────────────────────────────────────────────────────

async def mark_paid(db: AsyncSession, p: SiteProspect, ref: str, by: str = "paymob") -> None:
    if p.status == S.PAID or p.status == S.LIVE:
        return
    if p.status != S.PAYMENT_SENT:
        raise S.TransitionError(f"payment for prospect in status {p.status}")
    p.paid_at = utcnow()
    p.payment_ref = ref
    set_status(p, S.PAID, by)
    base = re.sub(r"[^a-z0-9]+", "-", (p.business_name or "").lower()).strip("-")[:30] or "site"
    p.live_slug = f"{base}-{secrets.token_hex(3)}"
    if not store_site(p, preview=False):
        log_event(p, "publish_failed", "storage upload failed — use Rebuild to retry")
    set_status(p, S.LIVE, p.live_slug)
    if p.lead_id:
        lead = await db.get(Lead, p.lead_id)
        if lead:
            lead.stage = LeadStage.won
    await db.commit()
    await send_wa(db, p, M.paid_thanks(p.business_name, live_url(p)), count_against_cap=False)
    await _notify_owner(db, p, "Site Factory: تم الدفع ✅", f"{p.business_name} — {ref}", urgent=True)
    await db.commit()


# ── data deletion ───────────────────────────────────────────────────────────

async def purge(db: AsyncSession, p: SiteProspect, reason: str, suppress: bool = True) -> None:
    """Delete the business's data and preview; keep only a phone hash so we never re-contact.
    The row stays (status + timestamps, no personal data) for funnel statistics."""
    delete_site_files(p)
    if suppress and p.phone and not (await db.get(SiteSuppression, phone_hash(p.phone))):
        db.add(SiteSuppression(phone_hash=phone_hash(p.phone), reason=reason))
    if p.lead_id:
        lead = await db.get(Lead, p.lead_id)
        if lead and suppress:
            lead.status = LeadStatus.unsubscribed   # the phone stays on the lead only to honour the opt-out
            lead.name = None
            lead.company = None
            lead.raw_data = {"site_factory": "purged"}
            lead.stage = LeadStage.lost
    p.business_name = "—"
    p.profile = {}
    p.site_copy = {}
    p.last_inbound = None
    p.preview_token = None
    p.site_key = None
    p.phone = f"purged:{phone_hash(p.phone)[:16]}" if p.phone and not p.phone.startswith("purged:") else p.phone
    p.events = [e for e in (p.events or []) if e.get("type", "").startswith("status:")]
    log_event(p, "purged", reason)
    await db.commit()
