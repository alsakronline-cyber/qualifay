"""Understand a business's WhatsApp reply in the context of where it is in the funnel.

Rule-based first (fast, predictable, Arabic/Egyptian/English). Anything the rules can't
place returns UNKNOWN, and the service asks the LLM, then a human if still unsure — a
wrong guess here would send a payment link to someone who said no.
"""
from __future__ import annotations

import re

from app.site_factory import state as S

YES, NO, STOP, LIKE, BUY, CANCEL, CHANGES, QUESTION, UNKNOWN = (
    "yes", "no", "stop", "like", "buy", "cancel", "changes", "question", "unknown",
)

_DIACRITICS = re.compile(r"[ً-ْـ]")  # harakat + tatweel


def normalize(text: str) -> str:
    t = (text or "").strip().lower()
    t = _DIACRITICS.sub("", t)
    t = re.sub(r"[إأآٱ]", "ا", t)
    t = t.replace("ى", "ي").replace("ة", "ه").replace("ؤ", "و").replace("ئ", "ي")
    t = re.sub(r"(.)\1{2,}", r"\1", t)          # stretched letters: "ايووووه" → "ايوه" (real words never triple a letter)
    return re.sub(r"\s+", " ", t)


def _words(t: str) -> set[str]:
    return set(re.findall(r"[\w']+", t))


def _has_word(t: str, words: set[str]) -> bool:
    return bool(_words(t) & words)


def _has_phrase(t: str, phrases: list[str]) -> bool:
    return any(p in t for p in phrases)


# Patterns are written in normalized form (no hamza on alef, ه for ة, ي for ى).
STOP_WORDS = {"stop", "unsubscribe", "ايقاف"}
STOP_PHRASES = ["لا اريد", "متبعتليش تاني", "ماتبعتليش", "remove me", "opt out", "متكلمنيش", "احذف رقمي"]

CANCEL_WORDS = {"الغاء", "الغي", "cancel", "كنسل", "لغي"}
CANCEL_PHRASES = ["مش عايز اكمل", "مش هكمل", "مش عاوز اكمل", "غيرت رايي", "changed my mind"]

NO_WORDS = {"لا", "لاء", "no", "nope"}
# Phrases that contain a "no" word but mean yes ("no objection", "why not").
NOT_NO_PHRASES = ["لا مانع", "مفيش مانع", "معنديش مانع", "ماعنديش مانع", "ليه لا", "ليه لاء", "why not", "no problem"]
NO_PHRASES = ["مش مهتم", "مش محتاج", "مش عايز", "مش عاوز", "not interested", "no thanks",
              "عندي موقع", "عندنا موقع", "مش دلوقتي", "مش الوقت"]

YES_WORDS = {"نعم", "ايوه", "ايوا", "ايوة", "اه", "اها", "تمام", "ماشي", "اوك", "اوكي", "ok", "okay",
             "yes", "yeah", "yep", "sure", "اكيد", "ابعت", "ابعته", "ابعتها", "ابعتلي", "اتفضل", "send", "يلا", "موافق"}
YES_PHRASES = ["ياريت", "يا ريت", "ابعت اللينك", "ابعتلي اللينك", "go ahead", "why not", "ليه لا"]

BUY_WORDS = {"اشتري", "اشتريه", "ادفع", "buy", "pay", "proceed", "نكمل", "اكمل", "هكمل", "موافق", "confirm", "حجز"}
BUY_PHRASES = ["عايز اكمل", "عاوز اكمل", "عايزه", "عاوزه", "نبدا", "خلينا نكمل", "تمام نكمل", "ابعت لينك الدفع",
               "ازاي ادفع", "هاخده", "let's go", "lets go", "i'll take it", "i want it"]

LIKE_WORDS = {"حلو", "حلوه", "جميل", "جميله", "ممتاز", "رائع", "تحفه", "عجبني", "عجبتني", "جامد", "nice",
              "great", "love", "awesome", "perfect", "beautiful", "تمام"}
CHANGES_WORDS = {"عدل", "اعدل", "تعدل", "نعدل", "تعديل", "تعديلات", "غير", "اغير", "تغير", "نغير", "تغيير", "اضيف", "ضيف", "شيل", "change", "edit", "update", "add", "remove"}
CHANGES_PHRASES = ["بس عايز", "ممكن تغير", "ممكن تعدل", "ناقصه", "مش مظبوط", "غلط في", "الرقم غلط", "العنوان غلط"]

QUESTION_PHRASES = ["بكام", "كام", "السعر", "سعر", "price", "how much", "cost", "تمنه", "ثمن", "مين انتو", "مين حضرتك",
                    "who are you", "الدومين", "domain", "استضافه", "hosting", "مده", "how long"]


def classify(text: str, status: str) -> str:
    """Return the intent of `text` given the prospect's current funnel `status`."""
    t = normalize(text)
    if not t:
        return UNKNOWN

    # Opt-out always wins, in every stage.
    if _has_word(t, STOP_WORDS) or _has_phrase(t, STOP_PHRASES):
        return STOP

    if status in {S.PREVIEW_SENT, S.CHANGES_REQUESTED, S.PAYMENT_SENT, S.OPTED_IN}:
        if _has_word(t, CANCEL_WORDS) or _has_phrase(t, CANCEL_PHRASES):
            return CANCEL

    positive_override = _has_phrase(t, NOT_NO_PHRASES)
    if not positive_override and (_has_phrase(t, NO_PHRASES) or (_has_word(t, NO_WORDS) and not _has_word(t, YES_WORDS))):
        return NO if status == S.INTRO_SENT else CANCEL

    if status == S.INTRO_SENT:
        if positive_override or _has_word(t, YES_WORDS) or _has_phrase(t, YES_PHRASES):
            return YES
        if _has_phrase(t, QUESTION_PHRASES) or "?" in t or "؟" in t:
            return QUESTION
        if t in {"شكرا", "شكرا ليك", "thanks", "thank you"}:
            return NO
        return UNKNOWN

    # After the preview: buying beats liking beats editing (a reply can carry several).
    if _has_word(t, BUY_WORDS) or _has_phrase(t, BUY_PHRASES):
        return BUY
    if _has_word(t, CHANGES_WORDS) or _has_phrase(t, CHANGES_PHRASES):
        return CHANGES
    if _has_phrase(t, QUESTION_PHRASES) or "?" in t or "؟" in t:
        return QUESTION
    # "No objection" after the preview is approval of the site, not a purchase decision —
    # a payment link only ever follows an explicit buy intent.
    if positive_override or _has_word(t, LIKE_WORDS):
        return LIKE
    return UNKNOWN
