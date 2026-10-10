"""WhatsApp texts the Site Factory sends. Short, polite Egyptian Arabic; every first-contact
message says who we are, why we're writing, and how to stop."""
from __future__ import annotations


def intro(business: str, sender: str, brand: str, gap: str) -> str:
    why = "مالوش موقع على الإنترنت" if gap == "no_website" else "مش ظاهر على خرائط جوجل ومالوش موقع"
    return (
        f"السلام عليكم، معاك {sender} من {brand} 👋\n"
        f"لاحظنا إن {business} {why}، فعملنا له نموذج موقع كامل كمعاينة مجانية من غير أي التزام.\n"
        "تحب أبعتلك اللينك تشوفه؟ رد بـ *نعم*.\n"
        "ولو مش مهتم ابعت *إيقاف* ومش هنراسلك تاني."
    )


def intro_followup(business: str) -> str:
    return (
        f"تذكير بسيط بخصوص معاينة موقع {business} اللي جهزناها 🙂\n"
        "لو تحب تشوفها رد بـ *نعم*، ولو مش مهتم ابعت *إيقاف*. ده آخر تذكير مننا."
    )


def preview(business: str, url: str, days: int) -> str:
    return (
        f"اتفضل معاينة موقع {business} 👇\n{url}\n\n"
        f"المعاينة خاصة بيك ومش منشورة، ومتاحة لمدة {days} يوم. "
        "الكلام والصور مقترحات بنعدّلها معاك.\n"
        "عجبك؟ تحب نكمّل وننشره باسمك؟"
    )


def preview_followup(business: str) -> str:
    return f"لحقت تشوف معاينة موقع {business}؟ لو عايز تعديل قولّي، ولو عجبك نقدر ننشره النهارده."


def ask_to_proceed() -> str:
    return "مبسوطين إنه عجبك 🙏 تحب نكمّل وننشره باسمك؟ رد بـ *نكمل* أو قولّي لو عايز تعديل."


def price_answer(price_egp: int) -> str:
    return (
        f"سعر الموقع {price_egp:,} جنيه مرة واحدة، شامل التصميم والنشر وربط واتساب والخرائط. "
        "الدومين والاستضافة السنوية بنوضحهم معاك قبل الدفع. تحب نكمّل؟"
    )


def payment(business: str, price_egp: int, card_url: str | None, instapay: str | None) -> str:
    lines = [f"تمام 👌 تكلفة موقع {business}: *{price_egp:,} جنيه*."]
    if card_url:
        lines.append(f"• الدفع بالكارت أو المحفظة: {card_url}")
    if instapay:
        lines.append(f"• أو InstaPay على: {instapay} وابعتلنا صورة التحويل هنا.")
    lines.append("أول ما الدفع يوصل بننشر الموقع ونبعتلك اللينك النهائي.")
    lines.append("لو غيرت رأيك ابعت *إلغاء* وبنمسح كل بياناتك.")
    return "\n".join(lines)


def payment_followup() -> str:
    return "تذكير بلينك الدفع لموقعك 🙂 لو عندك أي سؤال قبل الدفع أنا موجود. ولو مش هتكمل ابعت *إلغاء*."


def changes_ack() -> str:
    return "تمام، وصلني طلب التعديل ✍️ هنظبطه ونبعتلك المعاينة الجديدة."


def paid_thanks(business: str, live_url: str | None) -> str:
    tail = f"\nلينك الموقع: {live_url}" if live_url else "\nهنبعتلك اللينك النهائي خلال ساعات."
    return f"وصل الدفع، شكرًا لثقتك 🙏 موقع {business} اتنشر.{tail}"


def goodbye_deleted() -> str:
    return "تمام، تم إلغاء كل حاجة ومسح بياناتك ومش هنراسلك تاني. شكرًا لوقتك 🙏"


def handoff() -> str:
    return "تمام، هرد عليك بنفسي خلال وقت قصير 🙏"
