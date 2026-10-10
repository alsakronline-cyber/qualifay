"""Site Factory pure-logic tests: reply understanding, consent gates, timing, rendering."""
from datetime import datetime, timedelta

import json

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
    html = render_site(profile=_profile(), copy=copy, segment="manufacturer", preview=True, expires_on="2026-10-24")
    assert 'name="robots" content="noindex' in html
    assert "معاينة خاصة" in html
    live = render_site(profile=_profile(), copy=copy, segment="manufacturer", preview=False)
    assert "noindex" not in live and "معاينة خاصة" not in live


def test_untrusted_values_are_escaped():
    evil = '<script>alert(1)</script>"><img src=x onerror=alert(2)>'
    copy = fallback_copy("store", evil, None, None)
    copy["services"] = [{"name_ar": evil, "name_en": evil, "desc_ar": evil, "desc_en": evil}]
    html = render_site(profile=_profile(name=evil, address=evil, hours=[evil],
                                        links={"facebook": "javascript:alert(3)"}), copy=copy, segment="store", preview=True)
    assert "<script>alert(1)" not in html
    assert "onerror=alert(2)>" not in html
    assert "javascript:alert(3)" not in html          # only https:// social links are rendered


def test_clinic_has_medical_disclaimer_and_no_claims():
    copy = fallback_copy("clinic", "عيادة د. سارة", "المعادي", "عيادة أسنان")
    html = render_site(profile=_profile(name="عيادة د. سارة"), copy=copy, segment="clinic", preview=True)
    assert "لا تغني عن الاستشارة الطبية" in html
    joined = json.dumps(copy, ensure_ascii=False)
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


# ── multi-page site ─────────────────────────────────────────────────────────

from app.site_factory.builder import build_site
from app.site_factory import insights


def _site(preview=True, **prof):
    copy = fallback_copy("manufacturer", "مصنع النور", "العاشر من رمضان", "مصنع بلاستيك")
    return build_site(profile=_profile(**prof), copy=copy, segment="manufacturer",
                      base="/api/v1/site-factory/p/TOKEN/", preview=preview, site_url="https://sites.example.com/x/")


def test_full_site_has_every_page_in_both_languages():
    files = _site()
    for pre in ("", "en/"):
        for page in ("index.html", "about/index.html", "services/index.html", "services/1/index.html",
                     "services/3/index.html", "faq/index.html", "contact/index.html", "privacy/index.html"):
            assert pre + page in files, pre + page
    for extra in ("404.html", "sitemap.xml", "robots.txt", "assets/site.css", "assets/site.js"):
        assert extra in files
    assert '<html lang="en" dir="ltr">' in files["en/about/index.html"]
    assert '<html lang="ar" dir="rtl">' in files["about/index.html"]


def test_links_use_base_and_seo_tags_present():
    files = _site()
    home = files["index.html"]
    assert 'href="/api/v1/site-factory/p/TOKEN/about/"' in home
    assert 'href="/api/v1/site-factory/p/TOKEN/assets/site.css"' in home
    assert 'rel="canonical" href="https://sites.example.com/x/"' in home
    assert 'hreflang="en" href="https://sites.example.com/x/en/"' in home
    assert '"@type": "LocalBusiness"' in home
    assert '"BreadcrumbList"' in files["about/index.html"]
    assert '"FAQPage"' in files["faq/index.html"]
    assert '"@type": "Service"' in files["services/1/index.html"]
    titles = {files[f].split("<title>")[1].split("</title>")[0] for f in files if f.endswith("index.html")}
    assert len(titles) == len([f for f in files if f.endswith("index.html")])   # unique title per page


def test_preview_vs_live_indexing():
    prev, live = _site(preview=True), _site(preview=False)
    assert prev["robots.txt"].startswith("User-agent: *\nDisallow: /")
    assert "Sitemap: https://sites.example.com/x/sitemap.xml" in live["robots.txt"]
    assert all("noindex" in prev[f] for f in prev if f.endswith(".html"))
    assert not any("noindex" in live[f] for f in live if f.endswith(".html"))
    assert "<loc>https://sites.example.com/x/en/faq/</loc>" in live["sitemap.xml"]


def test_jsonld_cannot_break_out_of_script():
    files = _site(name='x</script><script>alert(1)</script>')
    assert "</script><script>alert(1)" not in files["index.html"]


def test_faq_is_built_from_facts_only():
    faq = _site()["faq/index.html"]
    assert "السبت: 9:00 – 17:00" in faq and "المنطقة الصناعية B3" in faq
    no_hours = _site(hours=[], address=None)["faq/index.html"]
    assert "مواعيد العمل؟" not in no_hours and "أين يقع" not in no_hours


def test_contact_form_goes_to_whatsapp_not_a_server():
    contact = _site()["contact/index.html"]
    assert 'class="wa" data-wa="https://wa.me/201001234567"' in contact
    assert "<form" in contact and "action=" not in contact


def test_no_review_markup():
    home = _site(rating=4.7, reviews=120)["index.html"]
    assert "120" in home and "aggregateRating" not in home


# ── insights ────────────────────────────────────────────────────────────────

def test_score_prefers_busy_reachable_manufacturers():
    hot, why = insights.score(segment="manufacturer", gap="no_gbp", rating=4.6, reviews=80, has_hours=True,
                              has_address=True, wa_reachable=True, social_links=1)
    cold, _ = insights.score(segment="store", gap="no_website", rating=3.1, reviews=0, has_hours=False,
                             has_address=False, wa_reachable=None, social_links=0)
    assert hot >= 70 and insights.tier(hot) == "hot" and why
    assert cold < 50 and insights.tier(cold) == "cold"
    assert insights.score(segment="clinic", gap="no_website", rating=5, reviews=999, has_hours=True,
                          has_address=True, wa_reachable=False, social_links=3)[0] == 0


def test_recommendations_follow_data_gaps():
    r = insights.recommend(segment="clinic", gap="no_gbp", reviews=None, has_hours=False, social_links=0, wa_reachable=True)
    ids = [x["id"] for x in r]
    assert ids == ["website", "gbp", "social", "whatsapp"]
    assert "إنشاء بروفايل جوجل" in r[1]["title_ar"] and "حجز" in r[3]["title_ar"]
    r2 = insights.recommend(segment="store", gap="no_website", reviews=200, has_hours=True, social_links=2,
                            wa_reachable=False, prices={"website": 6000})
    assert [x["id"] for x in r2] == ["website"] and r2[0]["price_egp"] == 6000
    assert insights.package_total(r) == sum(insights.DEFAULT_PRICES_EGP.values())


def test_exclusions_and_same_business():
    assert insights.is_excluded("مجمع الصناعات الغذائية والتعبئة للقوات المسلحة")
    assert insights.is_excluded("Ministry of Health clinic")
    assert not insights.is_excluded("مصنع النور للبلاستيك")
    area = {"10th", "of", "ramadan"}
    assert insights.same_business("EIPICO -10 of Ramadan", "EIPICO", area)
    assert insights.same_business("Heart Care Clinics Maadi", "Heart Care Clinics", {"maadi"})
    assert not insights.same_business("مصنع النور للبلاستيك", "مصنع الأمل للبلاستيك")
    assert not insights.same_business("مصنع العاشر من رمضان", "مصنع النور", area)


def test_copy_guard_blocks_claims_and_clinic_procedures():
    from app.site_factory.segments import sanitize_copy
    base = fallback_copy("clinic", "هارت كير", "المعادي", "عيادة قلب")
    llm = {"tagline_ar": "رعاية قلبية متميزة في المعادي", "intro_ar": "عيادة هارت كير في المعادي. احجز بالهاتف.",
           "services": [{"name_ar": "اختبار تخطيط القلب (ECG)", "name_en": "ECG", "desc_ar": "x", "desc_en": "x"}] * 3}
    out = sanitize_copy(llm, base, "clinic")
    assert out["tagline_ar"] == base["tagline_ar"]                      # claim rejected
    assert out["intro_ar"] == "عيادة هارت كير في المعادي. احجز بالهاتف."  # factual text kept
    assert out["services"] == base["services"]                           # clinics: neutral services only
    store = sanitize_copy({"services": [{"name_ar": f"خدمة {i}", "name_en": f"S{i}", "desc_ar": "وصف", "desc_en": "d"} for i in range(4)]
                           + [{"name_ar": "أفضل خدمة", "name_en": "best", "desc_ar": "", "desc_en": ""}]},
                          fallback_copy("store", "محل", None, None), "store")
    assert len(store["services"]) == 4 and all("أفضل" not in s["name_ar"] for s in store["services"])
