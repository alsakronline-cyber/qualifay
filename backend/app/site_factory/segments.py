"""Per-segment configuration: what to search for, how the preview site looks, and the
safe default copy used when the LLM is unavailable.

Default copy is deliberately generic and factual-sounding only about what any business in
the category does ("contact us", "visit us"). It never claims certifications, years,
prices, awards or (for clinics) treatment outcomes — the preview banner tells the owner the
text is a draft to confirm.
"""
from __future__ import annotations

SEGMENTS = ("manufacturer", "store", "clinic")

KEYWORDS: dict[str, list[str]] = {
    "manufacturer": ["مصنع", "factory", "manufacturer", "مصنع بلاستيك", "مصنع اغذية", "مصنع معادن", "ورشة تصنيع", "packaging factory"],
    "store": ["محل", "store", "shop", "معرض", "showroom", "محل ملابس", "محل اجهزة", "سوبر ماركت"],
    "clinic": ["عيادة", "clinic", "doctor", "دكتور", "عيادة اسنان", "dental clinic", "عيادة جلدية", "مركز طبي"],
}

# Google Places types that confirm the segment (used to drop off-segment results).
PLACE_TYPES: dict[str, set[str]] = {
    "manufacturer": {"manufacturer", "factory", "industrial", "establishment", "point_of_interest", "store"},
    "store": {"store", "clothing_store", "electronics_store", "furniture_store", "home_goods_store", "shoe_store",
              "supermarket", "grocery_store", "hardware_store", "jewelry_store", "book_store", "pet_store"},
    "clinic": {"doctor", "dentist", "health", "hospital", "physiotherapist", "medical_clinic", "dental_clinic"},
}

THEMES: dict[str, dict[str, str]] = {
    "manufacturer": {"primary": "#1f4fd1", "accent": "#f2a900", "bg": "#f4f6fa", "ink": "#0f1a2c", "font": "IBM Plex Sans Arabic"},
    "store": {"primary": "#0f766e", "accent": "#f97316", "bg": "#f7f7f5", "ink": "#16201f", "font": "Cairo"},
    "clinic": {"primary": "#0e7490", "accent": "#22c55e", "bg": "#f3f8fa", "ink": "#0b1f29", "font": "Tajawal"},
}

LABEL: dict[str, dict[str, str]] = {
    "manufacturer": {"ar": "مصنع", "en": "Manufacturer"},
    "store": {"ar": "متجر", "en": "Store"},
    "clinic": {"ar": "عيادة", "en": "Clinic"},
}


SERVICES_PAGE_TITLE = {
    "manufacturer": {"ar": "منتجاتنا وخدماتنا", "en": "Products & services"},
    "store": {"ar": "منتجاتنا", "en": "Our products"},
    "clinic": {"ar": "خدمات العيادة", "en": "Clinic services"},
}
CTA = {
    "manufacturer": {"ar": "اطلب عرض سعر", "en": "Request a quote"},
    "store": {"ar": "اطلب عبر واتساب", "en": "Order on WhatsApp"},
    "clinic": {"ar": "احجز موعدًا", "en": "Book an appointment"},
}


def _svc(name_ar, name_en, desc_ar, desc_en):
    return {"name_ar": name_ar, "name_en": name_en, "desc_ar": desc_ar, "desc_en": desc_en}


DEFAULT_SERVICES = {
    "manufacturer": [
        _svc("التصنيع حسب الطلب", "Made-to-order production",
             "نستقبل طلبات التصنيع بالمواصفات والكميات التي تحتاجها. أرسل التفاصيل وسنرد بعرض سعر.",
             "We take production orders to your specifications and quantities. Send the details and we will reply with a quote."),
        _svc("التوريد بالكميات", "Bulk supply",
             "توريد للشركات والتجار. تواصل معنا لمعرفة المتاح ومواعيد التسليم.",
             "Supply for companies and traders. Contact us for availability and delivery times."),
        _svc("زيارة المصنع", "Factory visits",
             "يمكنك ترتيب زيارة للمصنع للاطلاع على المنتجات قبل الطلب.",
             "You can arrange a factory visit to see products before ordering."),
    ],
    "store": [
        _svc("الطلب عبر واتساب", "Order on WhatsApp",
             "أرسل لنا اسم المنتج أو صورته على واتساب ونرد عليك بالتوفر والسعر.",
             "Send us the product name or a photo on WhatsApp and we reply with availability and price."),
        _svc("زيارة المحل", "Visit the store",
             "تفضل بزيارتنا في مواعيد العمل لمعاينة المنتجات.",
             "Visit us during opening hours to see the products."),
        _svc("الاستفسار عن المنتجات", "Product questions",
             "اسألنا عن أي منتج قبل الشراء.",
             "Ask us about any product before you buy."),
    ],
    "clinic": [
        _svc("حجز المواعيد", "Appointments",
             "احجز موعدك بالاتصال أو برسالة واتساب.",
             "Book by phone or WhatsApp message."),
        _svc("الاستفسارات", "Questions",
             "راسلنا للاستفسار عن مواعيد الطبيب وطريقة الحجز.",
             "Message us about the doctor's schedule and how to book."),
        _svc("الموقع ومواعيد العمل", "Location & hours",
             "تجد العنوان ومواعيد العمل في صفحة التواصل.",
             "Find the address and opening hours on the contact page."),
    ],
}


def fallback_copy(segment: str, name: str, city: str | None, category: str | None) -> dict:
    """Facts-only default copy for every page, Arabic first, English alongside."""
    seg = segment if segment in DEFAULT_SERVICES else "store"
    where_ar = f" في {city}" if city else ""
    where_en = f" in {city}" if city else ""
    cat = f" — {category}" if category else ""
    tagline = {
        "manufacturer": (f"{name} — تصنيع وتوريد{where_ar}", f"{name} — manufacturing & supply{where_en}"),
        "store": (f"{name}{where_ar}", f"{name}{where_en}"),
        "clinic": (f"{name}{where_ar}", f"{name}{where_en}"),
    }[seg]
    how_ar = {"manufacturer": "تواصل معنا لطلب عرض سعر أو ترتيب زيارة.",
              "store": "زورنا أو اطلب مباشرة عبر واتساب.",
              "clinic": "للحجز والاستفسار تواصل معنا بالهاتف أو واتساب."}[seg]
    how_en = {"manufacturer": "Contact us for a quotation or to arrange a visit.",
              "store": "Visit us or order directly on WhatsApp.",
              "clinic": "Call or message us on WhatsApp to book or ask a question."}[seg]
    return {
        "tagline_ar": tagline[0], "tagline_en": tagline[1],
        "intro_ar": f"{name}{cat}{where_ar}. {how_ar}",
        "intro_en": f"{name}{cat}{where_en}. {how_en}",
        "about_ar": [f"{name}{cat}{where_ar}.", how_ar],
        "about_en": [f"{name}{cat}{where_en}.", how_en],
        "services": [dict(x) for x in DEFAULT_SERVICES[seg]],
        "cta_ar": CTA[seg]["ar"], "cta_en": CTA[seg]["en"],
    }


# Words that turn a factual draft into an unverifiable claim. A field containing any of them is
# replaced by the safe default (the owner can still write their own claims before publishing).
CLAIM_WORDS = [
    "متميز", "متميزة", "الأفضل", "افضل", "أفضل", "رائد", "رائدة", "الأول", "الاولى", "الأولى", "متكامل", "متكاملة",
    "عالمي", "عالمية", "مضمون", "مضمونة", "ضمان", "خبرة طويلة", "سنوات من الخبرة", "أعلى جودة", "اعلى جودة", "الأرخص", "ارخص",
    "best", "leading", "top", "premium", "world-class", "guaranteed", "number one", "no. 1", "#1", "cheapest", "unmatched", "excellent",
    "comprehensive", "state-of-the-art", "cutting-edge",
]


def has_claim(text: str) -> bool:
    t = (text or "").lower()
    return any(w in t for w in CLAIM_WORDS)


def sanitize_copy(data: dict, base: dict, segment: str) -> dict:
    """Merge LLM copy over the facts-only `base`, keeping a field only if it is well-formed and
    claim-free. Clinics always keep the neutral services list: specific procedures/tests are
    medical claims we can't verify from public data."""
    out = dict(base)
    for k in ("tagline_ar", "tagline_en", "intro_ar", "intro_en", "cta_ar", "cta_en"):
        v = data.get(k)
        if isinstance(v, str) and v.strip() and not has_claim(v):
            out[k] = v.strip()[:300 if k.startswith("intro") else 140]
    for k in ("about_ar", "about_en"):
        v = data.get(k)
        if isinstance(v, list) and v and all(isinstance(x, str) and x.strip() for x in v):
            paras = [x.strip()[:700] for x in v[:4] if not has_claim(x)]
            if paras:
                out[k] = paras
    svcs = data.get("services")
    if segment != "clinic" and isinstance(svcs, list):
        good = [{f: str(x.get(f, "")).strip()[:400] for f in ("name_ar", "name_en", "desc_ar", "desc_en")}
                for x in svcs if isinstance(x, dict) and str(x.get("name_ar", "")).strip()]
        good = [g for g in good if not any(has_claim(g[f]) for f in g)]
        if len(good) >= 3:
            out["services"] = good[:6]
    return out
