"""Who is worth pursuing, and what to sell them — from the data that exists about them online.

Both functions are transparent rules (no LLM): every point in the score comes with a reason
the salesperson can read, and every recommended service names the gap it fixes.
"""
from __future__ import annotations

SERVICE_IDS = ("website", "gbp", "social", "whatsapp")

DEFAULT_PRICES_EGP = {"website": 4500, "gbp": 1500, "social": 2500, "whatsapp": 2000}

SERVICE_TITLES = {
    "website": {"ar": "موقع إلكتروني متكامل", "en": "Full website"},
    "gbp_create": {"ar": "إنشاء بروفايل جوجل للنشاط", "en": "Create Google Business Profile"},
    "gbp_fix": {"ar": "تحسين بروفايل جوجل", "en": "Optimise Google Business Profile"},
    "social": {"ar": "إنشاء صفحات السوشيال ومحتوى شهري", "en": "Social pages setup & monthly content"},
    "whatsapp_store": {"ar": "كتالوج واتساب وردود تلقائية للطلبات", "en": "WhatsApp catalogue & order auto-replies"},
    "whatsapp_clinic": {"ar": "حجز المواعيد عبر واتساب بردود تلقائية", "en": "WhatsApp appointment booking replies"},
    "whatsapp_factory": {"ar": "ردود تلقائية لطلبات عروض الأسعار على واتساب", "en": "WhatsApp quote-request auto-replies"},
}


import re as _re

# Not prospects: government, military, public bodies, universities.
EXCLUDE_PATTERNS = [
    "قوات المسلحة", "قوات مسلحة", "وزارة", "هيئة", "محافظة", "الحكومة", "جامعة", "مستشفى جامعي", "جهاز مشروعات",
    "armed forces", "ministry", "authority", "government", "governorate", "university",
]
_GENERIC = {"مصنع", "شركة", "شركه", "محل", "معرض", "عيادة", "عياده", "عيادات", "مركز", "فرع", "ستور", "store", "stores",
            "factory", "company", "co", "clinic", "clinics", "center", "centre", "branch", "the", "for", "and", "of", "-", "_",
            "د", "دكتور", "dr", "للصناعات", "لصناعة", "للتجارة", "egypt", "مصر", "ال"}


def is_excluded(name: str | None) -> bool:
    n = (name or "").lower()
    return any(p in n for p in EXCLUDE_PATTERNS)


def name_tokens(name: str | None, drop: set[str] | None = None) -> set[str]:
    """Distinctive words of a business name (generic words, area names and short tokens removed)."""
    t = (name or "").lower()
    t = _re.sub(r"[إأآ]", "ا", t).replace("ة", "ه").replace("ى", "ي")
    words = set(_re.findall(r"[\w']+", t))
    stop = _GENERIC | {w.lower() for w in (drop or set())}
    return {w for w in words if len(w) > 2 and w not in stop and not w.isdigit()}


def same_business(a: str | None, b: str | None, area_words: set[str] | None = None) -> bool:
    """True when two listing names clearly refer to the same brand (e.g. a branch vs the HQ listing)."""
    ta, tb = name_tokens(a, area_words), name_tokens(b, area_words)
    if not ta or not tb:
        return False
    overlap = len(ta & tb) / min(len(ta), len(tb))
    return overlap >= 0.6


def score(*, segment: str, gap: str, rating: float | None, reviews: int | None, has_hours: bool,
          has_address: bool, wa_reachable: bool | None, social_links: int) -> tuple[int, list[str]]:
    """0–100 'worth pursuing' score + Arabic reasons (shown in the dashboard)."""
    if wa_reachable is False:
        return 0, ["الرقم غير موجود على واتساب — لا يمكن التواصل"]
    s, why = 40, []

    seg_pts = {"manufacturer": 15, "clinic": 10, "store": 5}.get(segment, 0)
    if seg_pts:
        s += seg_pts
        why.append({"manufacturer": "مصنع — قيمة صفقة أعلى وعملاء B2B يبحثون أونلاين",
                    "clinic": "عيادة — المرضى يبحثون عن الأطباء أونلاين قبل الحجز",
                    "store": "محل — يستفيد من الظهور المحلي والطلب عبر واتساب"}[segment])

    if gap == "no_gbp":
        s += 10
        why.append("غير موجود على خرائط جوجل — احتياج واضح وخدمتان للبيع")
    else:
        s += 5
        why.append("موجود على خرائط جوجل لكن بدون موقع")

    r = reviews or 0
    if r >= 50:
        s += 15; why.append(f"{r} تقييم على جوجل — نشاط مزدحم وقادر على الدفع")
    elif r >= 10:
        s += 8; why.append(f"{r} تقييم على جوجل — نشاط فعّال")
    elif r >= 1:
        s += 3; why.append(f"{r} تقييمات فقط — نشاط صغير")
    elif gap == "no_website":
        s -= 5; why.append("بدون تقييمات — قد يكون غير نشط")

    if rating is not None:
        if rating >= 4.3:
            s += 5; why.append(f"تقييم {rating} — سمعة جيدة تستحق العرض")
        elif rating < 3.5:
            s -= 10; why.append(f"تقييم {rating} — سمعة ضعيفة، البيع أصعب")

    if has_hours:
        s += 3
    if has_address:
        s += 3
    if wa_reachable:
        s += 5; why.append("الرقم على واتساب — تواصل مباشر")
    if social_links:
        s += 4; why.append("له صفحات سوشيال — يهتم بالتسويق")

    return max(0, min(100, s)), why


def tier(value: int) -> str:
    return "hot" if value >= 70 else "warm" if value >= 50 else "cold"


def recommend(*, segment: str, gap: str, reviews: int | None, has_hours: bool, social_links: int,
              wa_reachable: bool | None, prices: dict | None = None) -> list[dict]:
    """Services this business lacks online, each with the reason and a price."""
    prices = {**DEFAULT_PRICES_EGP, **(prices or {})}
    out: list[dict] = []

    def add(sid: str, key: str, reason_ar: str):
        out.append({"id": sid, "title_ar": SERVICE_TITLES[key]["ar"], "title_en": SERVICE_TITLES[key]["en"],
                    "reason_ar": reason_ar, "price_egp": prices.get(sid, 0)})

    add("website", "website", "لا يوجد موقع — العملاء لا يجدون معلومات كاملة أو طريقة طلب واضحة")
    if gap == "no_gbp":
        add("gbp", "gbp_create", "غير ظاهر على خرائط جوجل — يخسر عملاء البحث القريبين")
    elif (reviews or 0) < 10 or not has_hours:
        add("gbp", "gbp_fix", "بروفايل جوجل ضعيف (تقييمات قليلة أو بدون مواعيد عمل)")
    if not social_links:
        add("social", "social", "لم نجد صفحات فيسبوك أو إنستجرام")
    if wa_reachable:
        key = {"store": "whatsapp_store", "clinic": "whatsapp_clinic"}.get(segment, "whatsapp_factory")
        add("whatsapp", key, "يستقبل العملاء على واتساب — الردود التلقائية توفر وقته وتزيد الطلبات")
    return out


def package_total(services: list[dict]) -> int:
    return sum(int(s.get("price_egp") or 0) for s in services)
