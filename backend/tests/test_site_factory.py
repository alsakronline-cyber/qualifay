"""Site Factory pure-logic tests: reply understanding, consent gates, timing, rendering."""
from datetime import datetime, timedelta

import pytest

from app.site_factory import state as S
from app.site_factory import replies as R
from app.site_factory.builder import render_site, wa_link
from app.site_factory.segments import fallback_copy
from app.site_factory import messages as M


# ── replies at the intro stage (we asked: want the preview link?) ──────────

@pytest.mark.parametrize("text", ["نعم", "ايوه", "أيوة ابعت", "اه ابعتلي", "تمام", "ماشي", "ok", "Yes please",
                                  "يا ريت", "لا مانع", "مفيش مانع", "ليه لأ", "ابعت اللينك", "ايووووه"])
def test_intro_yes(text):
    assert R.classify(text, S.INTRO_SENT) == R.YES


@pytest.mark.parametrize("text", ["لا", "لأ شكرا", "مش مهتم", "عندنا موقع", "no thanks", "not interested", "شكرا"])
def test_intro_no(text):
    assert R.classify(text, S.INTRO_SENT) == R.NO


@pytest.mark.parametrize("text", ["ايقاف", "إيقاف", "STOP", "متبعتليش تاني", "احذف رقمي"])
def test_stop_wins_everywhere(text):
    for st in (S.INTRO_SENT, S.PREVIEW_SENT, S.PAYMENT_SENT):
        assert R.classify(text, st) == R.STOP


def test_intro_question_and_unknown():
    assert R.classify("بكام الموقع؟", S.INTRO_SENT) == R.QUESTION
    assert R.classify("مين حضرتك", S.INTRO_SENT) == R.QUESTION
    assert R.classify("👍👍", S.INTRO_SENT) == R.UNKNOWN


# ── replies after the preview (we asked: like it? proceed?) ────────────────

@pytest.mark.parametrize("text", ["عايز اكمل", "تمام نكمل", "موافق", "ازاي ادفع", "هاخده", "let's go", "I want it"])
def test_after_preview_buy(text):
    assert R.classify(text, S.PREVIEW_SENT) == R.BUY


@pytest.mark.parametrize("text", ["حلو جدا", "عجبني", "تحفة", "great", "تمام", "لا مانع"])
def test_after_preview_like_is_not_buy(text):
    # Approval of the design must never trigger a payment link on its own.
    assert R.classify(text, S.PREVIEW_SENT) == R.LIKE


@pytest.mark.parametrize("text", ["عايز اغير اللون", "الرقم غلط", "ممكن تعدل العنوان", "please change the logo"])
def test_after_preview_changes(text):
    assert R.classify(text, S.PREVIEW_SENT) == R.CHANGES


@pytest.mark.parametrize("text", ["الغاء", "إلغاء الطلب", "مش هكمل", "cancel", "لا مش عايز"])
def test_after_preview_cancel(text):
    assert R.classify(text, S.PREVIEW_SENT) == R.CANCEL
    assert R.classify(text, S.PAYMENT_SENT) == R.CANCEL


def test_normalize_handles_arabic_variants():
    assert R.normalize("أيـــوة") == R.normalize("ايوه")
    assert R.normalize("إلغاء") == "الغاء"


# ── consent gates ───────────────────────────────────────────────────────────

def test_intro_requires_human_approval():
    ok, why = S.may_send_intro(S.AWAITING_APPROVAL, None, suppressed=False, wa_reachable=True)
    assert not ok and why == "not_approved"
    ok, _ = S.may_send_intro(S.AWAITING_APPROVAL, "user-1", suppressed=False, wa_reachable=True)
    assert ok


def test_intro_blocked_when_suppressed_or_unreachable():
    assert S.may_send_intro(S.AWAITING_APPROVAL, "u", suppressed=True, wa_reachable=True)[1] == "suppressed"
    assert S.may_send_intro(S.AWAITING_APPROVAL, "u", suppressed=False, wa_reachable=False)[1] == "not_on_whatsapp"
    assert S.may_send_intro(S.INTRO_SENT, "u", suppressed=False, wa_reachable=True)[0] is False


def test_preview_requires_opt_in():
    assert S.may_send_preview(S.OPTED_IN, None) == (False, "no_consent")
    assert S.may_send_preview(S.INTRO_SENT, datetime(2026, 1, 1))[0] is False
    assert S.may_send_preview(S.OPTED_IN, datetime(2026, 1, 1)) == (True, "ok")


def test_transitions():
    assert S.can_transition(S.INTRO_SENT, S.OPTED_IN)
    assert not S.can_transition(S.INTRO_SENT, S.PREVIEW_SENT)       # can't skip consent
    assert not S.can_transition(S.PREVIEW_SENT, S.PAID)              # can't skip payment request
    assert not S.can_transition(S.DECLINED, S.INTRO_SENT)            # terminal stays terminal
    with pytest.raises(S.TransitionError):
        S.assert_transition(S.FOUND, S.PAYMENT_SENT)


# ── timing ──────────────────────────────────────────────────────────────────

def test_one_followup_then_expire():
    t0 = datetime(2026, 10, 1, 12)
    assert S.due_action(S.INTRO_SENT, t0, 0, t0 + timedelta(days=1)) is None
    assert S.due_action(S.INTRO_SENT, t0, 0, t0 + timedelta(days=3)) == "followup"
    assert S.due_action(S.INTRO_SENT, t0, 1, t0 + timedelta(days=4)) is None
    assert S.due_action(S.INTRO_SENT, t0, 1, t0 + timedelta(days=6)) == "expire"
    assert S.due_action(S.CHANGES_REQUESTED, t0, 0, t0 + timedelta(days=10)) == "expire"
    assert S.due_action(S.LIVE, t0, 0, t0 + timedelta(days=99)) is None


def test_send_window():
    assert S.in_send_window(datetime(2026, 10, 1, 10, 0))
    assert not S.in_send_window(datetime(2026, 10, 1, 22, 0))
    assert not S.in_send_window(datetime(2026, 10, 1, 7, 30))


# ── rendering ───────────────────────────────────────────────────────────────

def _profile(**kw):
    base = {"name": "مصنع النور", "phone": "+201001234567", "city": "العاشر من رمضان", "address": "المنطقة الصناعية B3",
            "hours": ["السبت: 9:00 – 17:00"], "category": "مصنع بلاستيك"}
    base.update(kw)
    return base


def test_preview_is_noindex_and_bannered():
    copy = fallback_copy("manufacturer", "مصنع النور", "العاشر من رمضان", "مصنع بلاستيك")
    html = render_site(profile=_profile(), copy=copy, segment="manufacturer", preview=True, expires_label="x")
    assert 'name="robots" content="noindex' in html
    assert "معاينة خاصة" in html
    live = render_site(profile=_profile(), copy=copy, segment="manufacturer", preview=False)
    assert "noindex" not in live and "معاينة خاصة" not in live


def test_untrusted_values_are_escaped():
    evil = '<script>alert(1)</script>"><img src=x onerror=alert(2)>'
    copy = fallback_copy("store", evil, None, None)
    copy["services_ar"] = [evil]
    html = render_site(profile=_profile(name=evil, address=evil, hours=[evil],
                                        links={"facebook": "javascript:alert(3)"}), copy=copy, segment="store", preview=True)
    assert "<script>alert(1)" not in html
    assert "onerror=alert(2)>" not in html
    assert "javascript:alert(3)" not in html          # only https:// social links are rendered


def test_clinic_has_medical_disclaimer_and_no_claims():
    copy = fallback_copy("clinic", "عيادة د. سارة", "المعادي", "عيادة أسنان")
    html = render_site(profile=_profile(name="عيادة د. سارة"), copy=copy, segment="clinic", preview=True)
    assert "لا تغني عن الاستشارة الطبية" in html
    joined = " ".join(str(v) for v in copy.values())
    for claim in ("علاج مضمون", "أفضل", "شهادة", "سنوات خبرة"):
        assert claim not in joined


def test_wa_link():
    assert wa_link("+201001234567", "مرحبا").startswith("https://wa.me/201001234567?text=")


def test_intro_message_identifies_sender_and_how_to_stop():
    text = M.intro("مصنع النور", "محمد", "Sdiek Marketing", "no_website")
    assert "Sdiek Marketing" in text and "محمد" in text
    assert "إيقاف" in text                              # opt-out offered in the first message
    assert "http" not in text                           # no link before consent


def test_monogram_and_local_phone():
    from app.site_factory.builder import _initials, local_phone
    assert _initials("مصنع النور للبلاستيك") == "ن"
    assert _initials("عيادة د. سارة") == "س"
    assert _initials("Delta Plast") == "DP"
    assert local_phone("+201001234567") == "0100 123 4567"
