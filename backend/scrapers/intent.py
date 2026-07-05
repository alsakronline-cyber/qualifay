"""Buyer-intent detection for social/group posts (Egyptian Arabic + English).

Pure, dependency-free helpers so the intent logic is unit-testable independent of any
scraper. Used to pre-filter Facebook group posts down to people who want to BUY or are
ASKING for a product/service, before spending an AI call to confirm and extract details.
"""
import re

# Strip Arabic diacritics (tashkeel), superscript alef, and tatweel so keyword matching is
# robust to how people actually type.
_TASHKEEL = re.compile(r"[ً-ْٰـ]")


def normalize_ar(text: str) -> str:
    if not text:
        return ""
    t = _TASHKEEL.sub("", text)
    for a in "أإآ":
        t = t.replace(a, "ا")
    t = t.replace("ى", "ي").replace("ئ", "ي").replace("ؤ", "و")
    return t.lower()


# Buyer / request intent (written without diacritics; normalized at load).
_BUYER = [
    # Arabic — want / need
    "محتاج", "محتاجه", "محتاجين", "عايز", "عايزه", "عاوز", "عاوزه", "عايزين",
    "اريد", "اريده", "نفسي اشتري", "حابب اشتري", "حابه اشتري", "عايز اشتري", "عاوز اشتري",
    "مطلوب", "مطلوبه", "للشراء",
    # Arabic — searching / asking
    "بدور علي", "بدور على", "بدوّر", "بدور", "فين الاقي", "فين اجيب", "فين ممكن",
    "حد يعرف", "حد عنده", "حد يبيع", "مين عنده", "مين يعرف", "ممكن حد", "حد يرشح",
    "ينصحني", "توصيه", "ترشيح", "استفسار",
    # Arabic — price ask
    "بكام", "السعر كام", "عايز اعرف السعر", "عرض سعر", "سعر الـ", "بيتباع بكام",
    # English
    "looking for", "need a", "need to buy", "want to buy", "anyone selling",
    "where can i find", "where to buy", "how much", "price for", "who sells",
    "recommend", "searching for", "interested in buying", "any supplier",
]
BUYER_KEYWORDS = [normalize_ar(k) for k in _BUYER]

# Phrases that strongly indicate the poster is SELLING, not buying — used to down-rank.
_SELLER = [
    "للبيع", "للايجار", "متاح للبيع", "خصم", "عرض خاص", "اطلب الان", "تواصل معنا",
    "للتواصل والطلب", "اتصل بنا", "we sell", "for sale", "shop now", "order now", "dm to order",
]
SELLER_KEYWORDS = [normalize_ar(k) for k in _SELLER]

# Egyptian mobile numbers, tolerant of spaces/dashes (stripped before matching).
_PHONE_RE = re.compile(r"(?:\+?20|0020)?0?1[0125]\d{8}")


def detect_buyer_intent(text: str) -> bool:
    """True when the post reads like someone wanting to buy or asking for something."""
    n = normalize_ar(text)
    if not any(k in n for k in BUYER_KEYWORDS):
        return False
    # If it's clearly a sales post AND has no explicit buyer verb, treat as non-buyer.
    seller_hits = sum(1 for k in SELLER_KEYWORDS if k in n)
    strong_buyer = any(k in n for k in ("محتاج", "عايز اشتري", "عاوز اشتري", "مطلوب",
                                        "want to buy", "looking for", "need to buy"))
    if seller_hits >= 2 and not strong_buyer:
        return False
    return True


def extract_phone_from_text(text: str):
    """Return the first Egyptian mobile number found in free text, else None."""
    if not text:
        return None
    compact = re.sub(r"[\s\-()]", "", text)
    m = _PHONE_RE.search(compact)
    return m.group(0) if m else None
