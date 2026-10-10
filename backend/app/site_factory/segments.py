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


def fallback_copy(segment: str, name: str, city: str | None, category: str | None) -> dict:
    """Facts-only default copy, Arabic first, with English alongside."""
    where_ar = f" في {city}" if city else ""
    where_en = f" in {city}" if city else ""
    cat = category or ""
    if segment == "manufacturer":
        return {
            "tagline_ar": f"{name} — تصنيع وتوريد{where_ar}",
            "tagline_en": f"{name} — manufacturing & supply{where_en}",
            "about_ar": f"{name}{' — ' + cat if cat else ''}{where_ar}. تواصل معنا لطلب عرض سعر أو زيارة المصنع.",
            "about_en": f"{name}{' — ' + cat if cat else ''}{where_en}. Contact us for a quotation or a factory visit.",
            "services_ar": ["طلبات الكميات والتوريد", "عروض الأسعار حسب الطلب", "التواصل المباشر مع المصنع"],
            "services_en": ["Bulk orders & supply", "Quotations on request", "Direct contact with the factory"],
            "cta_ar": "اطلب عرض سعر", "cta_en": "Request a quote",
        }
    if segment == "clinic":
        return {
            "tagline_ar": f"{name}{where_ar}",
            "tagline_en": f"{name}{where_en}",
            "about_ar": f"{name}{' — ' + cat if cat else ''}{where_ar}. للحجز والاستفسار تواصل معنا عبر الهاتف أو واتساب.",
            "about_en": f"{name}{' — ' + cat if cat else ''}{where_en}. Call or message us on WhatsApp to book or ask a question.",
            "services_ar": ["حجز المواعيد", "الاستفسارات عبر واتساب", "مواعيد العمل والعنوان"],
            "services_en": ["Appointments", "Questions on WhatsApp", "Opening hours & location"],
            "cta_ar": "احجز موعدًا", "cta_en": "Book an appointment",
        }
    return {
        "tagline_ar": f"{name}{where_ar}",
        "tagline_en": f"{name}{where_en}",
        "about_ar": f"{name}{' — ' + cat if cat else ''}{where_ar}. زورنا أو اطلب عبر واتساب.",
        "about_en": f"{name}{' — ' + cat if cat else ''}{where_en}. Visit us or order on WhatsApp.",
        "services_ar": ["الطلب عبر واتساب", "زيارة المحل", "الاستفسار عن المنتجات والأسعار"],
        "services_en": ["Order on WhatsApp", "Visit the store", "Ask about products & prices"],
        "cta_ar": "اطلب الآن عبر واتساب", "cta_en": "Order on WhatsApp",
    }
