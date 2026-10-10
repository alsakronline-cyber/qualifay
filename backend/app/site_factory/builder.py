"""Build a business's complete website as a set of static files (Arabic at the root, English
under /en/). Pure function: data in, {path: text} out — stored in object storage and served
by the API under a base path, or exported to any static host.

Pages: home · about · services (+ one page per service) · FAQ · contact · privacy · 404,
plus sitemap.xml, robots.txt, assets/site.css, assets/site.js.

SEO/UX built in: unique <title>/description per page, canonical + hreflang, Open Graph,
LocalBusiness / MedicalClinic / Store JSON-LD, BreadcrumbList, FAQPage, Service schema,
semantic landmarks, skip link, mobile nav without JS, sticky WhatsApp button, a contact form
that composes a WhatsApp message (no backend, no data stored), map embed.

Rules: every value is HTML-escaped (open-web + LLM data); no third-party photos; no review
markup (Google reviews can't be republished as our own structured data); previews are
noindex and carry a "private preview" banner on every page.
"""
from __future__ import annotations

import json
from html import escape
from urllib.parse import quote

from app.site_factory.segments import CTA, LABEL, SERVICES_PAGE_TITLE, THEMES

LANGS = ("ar", "en")

ICONS = {
    "phone": '<path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1.9.4 1.8.7 2.7a2 2 0 0 1-.5 2.1L8 9.8a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.4c.9.3 1.8.6 2.7.7a2 2 0 0 1 1.7 2z"/>',
    "pin": '<path d="M21 10c0 7-9 13-9 13S3 17 3 10a9 9 0 1 1 18 0z"/><circle cx="12" cy="10" r="3"/>',
    "clock": '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
    "check": '<path d="M20 6 9 17l-5-5"/>',
    "chat": '<path d="M21 11.5a8.4 8.4 0 0 1-9 8.4 8.5 8.5 0 0 1-3.8-.9L3 21l1.9-5.2A8.4 8.4 0 0 1 12 3a8.4 8.4 0 0 1 9 8.5z"/>',
    "star": '<path d="m12 2 3.1 6.3 6.9 1-5 4.9 1.2 6.8L12 17.8 5.8 21l1.2-6.8-5-4.9 6.9-1z"/>',
    "arrow": '<path d="M5 12h14M13 6l6 6-6 6"/>',
    "menu": '<path d="M4 7h16M4 12h16M4 17h16"/>',
}

T = {  # UI strings: (ar, en)
    "home": ("الرئيسية", "Home"), "about": ("من نحن", "About"), "faq": ("الأسئلة الشائعة", "FAQ"),
    "contact": ("تواصل معنا", "Contact"), "privacy": ("سياسة الخصوصية", "Privacy"),
    "address": ("العنوان", "Address"), "phone": ("الهاتف", "Phone"), "hours": ("مواعيد العمل", "Opening hours"),
    "maps": ("افتح على الخريطة", "Open in Maps"), "more": ("التفاصيل", "Details"), "skip": ("انتقل إلى المحتوى", "Skip to content"),
    "lang": ("English", "العربية"), "menu": ("القائمة", "Menu"), "preview": ("معاينة خاصة — غير منشورة", "Private preview — not published"),
    "draft": ("النصوص مقترحة ونعدّلها معك.", "Text is a draft we edit with you."),
    "how": ("كيف تطلب الخدمة", "How to request it"), "other": ("خدمات أخرى", "Other services"),
    "reviews": ("تقييمًا على جوجل", "reviews on Google"), "expires": ("تنتهي المعاينة", "Preview expires"),
    "ready": ("جاهزين نساعدك", "Ready when you are"), "ready_sub": ("راسلنا على واتساب وهنرد عليك بسرعة.", "Message us on WhatsApp and we will reply quickly."),
    "name": ("اسمك", "Your name"), "need": ("ماذا تحتاج؟", "What do you need?"), "send": ("إرسال عبر واتساب", "Send on WhatsApp"),
    "form_note": ("الرسالة تُرسل من واتساب الخاص بك مباشرة إلينا — لا نخزّن أي بيانات على هذا الموقع.",
                  "Your message is sent from your own WhatsApp straight to us — this site stores no data."),
    "facts": ("معلومات سريعة", "Quick facts"), "category": ("النشاط", "Business"), "city": ("المدينة", "City"),
    "notfound": ("الصفحة غير موجودة", "Page not found"), "back": ("العودة للرئيسية", "Back home"),
    "by": ("تصميم وتطوير", "Designed & built by"),
    "medical": ("المعلومات للتعريف بالعيادة فقط ولا تغني عن الاستشارة الطبية.",
                "Information about the clinic only — not a substitute for medical advice."),
    "steps": (["راسلنا على واتساب أو اتصل بنا", "أرسل التفاصيل التي تحتاجها", "نرد عليك بالتأكيد والتفاصيل"],
              ["Message us on WhatsApp or call", "Send the details you need", "We confirm and reply with details"]),
}


def tr(key: str, lang: str):
    v = T[key]
    return v[0] if lang == "ar" else v[1]


def _e(v) -> str:
    return escape(str(v or ""), quote=True)


def _icon(name: str, size: int = 22) -> str:
    return (f'<svg viewBox="0 0 24 24" width="{size}" height="{size}" fill="none" stroke="currentColor" stroke-width="1.8" '
            f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{ICONS[name]}</svg>')


def _ld(obj: dict) -> str:
    """JSON-LD block; <, > and & are \\u-escaped so data can never close the script tag."""
    safe = json.dumps(obj, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return '<script type="application/ld+json">' + safe + "</script>"


def wa_link(phone_e164: str, text: str = "") -> str:
    digits = "".join(ch for ch in (phone_e164 or "") if ch.isdigit())
    return f"https://wa.me/{digits}" + (f"?text={quote(text)}" if text else "")


def maps_link(name: str, address: str | None, place_id: str | None = None) -> str:
    q = quote(", ".join(x for x in [name, address] if x))
    return f"https://www.google.com/maps/search/?api=1&query={q}" + (f"&query_place_id={quote(place_id)}" if place_id else "")


def maps_embed(name: str, address: str | None) -> str:
    return f"https://www.google.com/maps?q={quote(', '.join(x for x in [name, address] if x))}&output=embed"


GENERIC_PREFIXES = {"مصنع", "شركة", "محل", "معرض", "عيادة", "مركز", "د.", "د", "دكتور", "مؤسسة", "factory", "the", "dr", "dr."}


def _initials(name: str) -> str:
    """Logo monogram: skip generic words ("مصنع", "عيادة", "Dr."), then 1 Arabic letter or 2 Latin initials."""
    words = [w for w in (name or "").replace("-", " ").split() if w]
    core = [w for w in words if w.lower().strip(".") not in GENERIC_PREFIXES and w.lower() not in GENERIC_PREFIXES] or words
    if not core:
        return "•"
    first = core[0][2:] if core[0].startswith("ال") and len(core[0]) > 3 else core[0]
    if first and "؀" <= first[0] <= "ۿ":
        return first[0]
    return "".join(w[0] for w in core[:2]).upper()


def local_phone(e164: str) -> str:
    """+201001234567 → 0100 123 4567 (how Egyptians read a number)."""
    d = "".join(ch for ch in (e164 or "") if ch.isdigit())
    if d.startswith("20") and len(d) == 12:
        n = "0" + d[2:]
        return f"{n[:4]} {n[4:7]} {n[7:]}"
    return e164 or ""


def _schema_type(segment: str, category: str | None) -> str:
    if segment == "clinic":
        return "Dentist" if category and any(k in category.lower() for k in ("اسنان", "أسنان", "dent")) else "MedicalClinic"
    return "Store" if segment == "store" else "LocalBusiness"


def _css(theme: dict) -> str:
    return f""":root{{--p:{theme['primary']};--a:{theme['accent']};--bg:{theme['bg']};--ink:{theme['ink']};--mut:#5b6575;--line:#dde2ea;--card:#fff;--r:16px}}
*{{box-sizing:border-box;margin:0}}html{{scroll-behavior:smooth}}
body{{font-family:'{theme['font']}','IBM Plex Sans Arabic',system-ui,sans-serif;background:var(--bg);color:var(--ink);line-height:1.75;-webkit-font-smoothing:antialiased}}
html[lang=en] body{{font-family:'Inter',system-ui,sans-serif}}
a{{color:inherit}}img,svg{{display:block;max-width:100%}}
.wrap{{max-width:1120px;margin-inline:auto;padding-inline:20px}}
.skip{{position:absolute;inset-inline-start:10px;top:-60px;background:var(--ink);color:#fff;padding:8px 14px;border-radius:8px;z-index:20}}.skip:focus{{top:10px}}
:focus-visible{{outline:2px solid var(--p);outline-offset:3px;border-radius:6px}}
.pv{{background:#111827;color:#fff;font-size:.86rem;padding:9px 20px;text-align:center}}.pv span{{opacity:.75;margin-inline-start:8px}}
.hdr{{position:sticky;top:0;z-index:10;background:rgba(255,255,255,.9);backdrop-filter:blur(10px);border-bottom:1px solid var(--line)}}
.hdr .wrap{{display:flex;align-items:center;justify-content:space-between;gap:16px;min-height:68px}}
.logo{{display:flex;align-items:center;gap:10px;font-weight:700;text-decoration:none;min-width:0}}
.logo i{{width:40px;height:40px;flex:none;border-radius:12px;background:var(--p);color:#fff;display:grid;place-items:center;font-style:normal}}
.logo span{{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
nav.main ul{{display:flex;gap:22px;list-style:none;padding:0}}
nav.main a{{text-decoration:none;font-weight:600;font-size:.95rem;color:var(--mut)}}nav.main a[aria-current=page],nav.main a:hover{{color:var(--p)}}
.hdr-actions{{display:flex;align-items:center;gap:12px;flex:none}}
.lang{{font-size:.88rem;text-decoration:none;color:var(--mut)}}
.btn{{display:inline-flex;align-items:center;justify-content:center;gap:10px;padding:13px 22px;border-radius:12px;text-decoration:none;border:0;cursor:pointer;font:inherit;font-weight:700}}
.btn--p{{background:var(--p);color:#fff}}.btn--g{{background:#25d366;color:#06301a}}.btn--o{{background:#fff;border:1px solid var(--line)}}.btn--sm{{padding:9px 16px;font-size:.9rem}}
.mnav{{display:none}}
@media(max-width:860px){{nav.main{{display:none}}.mnav{{display:block}}.hdr .btn--sm{{display:none}}}}
.mnav summary{{list-style:none;cursor:pointer;width:42px;height:42px;display:grid;place-items:center;border:1px solid var(--line);border-radius:12px;background:#fff}}
.mnav summary::-webkit-details-marker{{display:none}}
.mnav ul{{position:absolute;inset-inline:12px;top:72px;background:#fff;border:1px solid var(--line);border-radius:var(--r);padding:10px;list-style:none;display:grid;box-shadow:0 20px 50px -20px rgba(0,0,0,.3)}}
.mnav li a{{display:block;padding:12px 14px;text-decoration:none;font-weight:600;border-radius:10px}}.mnav li a:hover{{background:var(--bg)}}
.crumbs{{font-size:.85rem;color:var(--mut);padding-top:22px}}.crumbs ol{{display:flex;flex-wrap:wrap;gap:6px;list-style:none;padding:0}}.crumbs li+li::before{{content:"/";margin-inline-end:6px;opacity:.5}}.crumbs a{{text-decoration:none}}
.hero{{padding:56px 0 48px;display:grid;gap:20px}}
.tag{{display:inline-flex;gap:8px;align-items:center;font-size:.86rem;color:var(--p);font-weight:700;background:#fff;border:1px solid var(--line);padding:6px 12px;border-radius:99px;width:fit-content}}
h1{{font-size:clamp(2rem,5.6vw,3.3rem);line-height:1.2}}h2{{font-size:clamp(1.4rem,3vw,1.9rem);line-height:1.3;margin-bottom:18px}}h3{{font-size:1.12rem}}
.lead{{font-size:1.12rem;color:var(--mut);max-width:62ch}}
.btns{{display:flex;flex-wrap:wrap;gap:12px}}
.rating{{display:inline-flex;align-items:center;gap:8px;font-size:.92rem;color:var(--mut);text-decoration:none}}.rating svg{{color:#f5b301;fill:#f5b301}}
section{{padding:48px 0}}section+section{{border-top:1px solid var(--line)}}
.grid{{display:grid;gap:16px}}@media(min-width:720px){{.grid{{grid-template-columns:repeat(2,1fr)}}}}@media(min-width:1000px){{.grid--3{{grid-template-columns:repeat(3,1fr)}}}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:var(--r);padding:24px;display:grid;gap:10px;align-content:start}}
a.card{{text-decoration:none;transition:border-color .2s,transform .2s}}a.card:hover{{border-color:var(--p);transform:translateY(-3px)}}
.card>svg{{color:var(--p)}}.card p{{color:var(--mut)}}.card .go{{color:var(--p);font-weight:700;display:inline-flex;gap:6px;align-items:center}}
[dir=rtl] .go svg{{transform:scaleX(-1)}}
ol.steps{{list-style:none;padding:0;display:grid;gap:12px;counter-reset:s}}ol.steps li{{counter-increment:s;display:flex;gap:14px;align-items:center;background:#fff;border:1px solid var(--line);border-radius:12px;padding:14px 16px}}
ol.steps li::before{{content:counter(s);width:30px;height:30px;flex:none;border-radius:50%;background:var(--p);color:#fff;display:grid;place-items:center;font-weight:700}}
.prose{{max-width:72ch}}.prose p+p{{margin-top:14px}}
.facts{{display:grid;border-top:1px solid var(--line)}}.facts div{{display:flex;justify-content:space-between;gap:16px;padding:12px 0;border-bottom:1px solid var(--line)}}.facts dd{{margin:0;font-weight:600;text-align:end}}
details.faq{{background:#fff;border:1px solid var(--line);border-radius:12px;padding:0 18px}}details.faq+details.faq{{margin-top:10px}}
details.faq summary{{cursor:pointer;font-weight:700;padding:16px 0;list-style:none}}details.faq summary::-webkit-details-marker{{display:none}}details.faq p{{padding-bottom:16px;color:var(--mut)}}
.band{{background:var(--p);color:#fff;border-radius:24px;padding:40px clamp(20px,5vw,56px);display:grid;gap:14px;justify-items:start;margin:24px 0}}.band p{{opacity:.85}}.band h2{{margin:0}}
form.wa{{display:grid;gap:14px;background:#fff;border:1px solid var(--line);border-radius:var(--r);padding:24px;align-content:start}}
form.wa label{{display:grid;gap:6px;font-weight:600;font-size:.92rem}}
form.wa input,form.wa textarea{{font:inherit;padding:12px 14px;border:1px solid var(--line);border-radius:10px;background:var(--bg)}}form.wa textarea{{min-height:110px;resize:vertical}}
.note{{font-size:.85rem;color:var(--mut)}}
.map{{width:100%;min-height:320px;border:0;border-radius:var(--r);background:#e6e9ef}}
ul.hrs{{list-style:none;padding:0}}
footer.ftr{{margin-top:40px;background:var(--ink);color:#d7dde7;padding:44px 0 100px;font-size:.93rem}}
footer.ftr .grid{{gap:28px}}@media(min-width:900px){{footer.ftr .grid{{grid-template-columns:1.4fr 1fr 1fr}}}}
footer.ftr h3{{color:#fff;margin-bottom:10px;font-size:1rem}}footer.ftr ul{{list-style:none;padding:0;display:grid;gap:6px}}footer.ftr a{{text-decoration:none}}footer.ftr a:hover{{text-decoration:underline}}
footer.ftr .base{{margin-top:30px;padding-top:18px;border-top:1px solid rgba(255,255,255,.12);display:flex;flex-wrap:wrap;justify-content:space-between;gap:10px;opacity:.75}}
.fab{{position:fixed;bottom:18px;inset-inline-end:18px;z-index:12;background:#25d366;color:#06301a;border-radius:99px;padding:13px 18px;font-weight:800;text-decoration:none;display:flex;gap:8px;align-items:center;box-shadow:0 12px 30px -10px rgba(0,0,0,.4)}}
.err{{min-height:60vh;display:grid;place-items:center;align-content:center;text-align:center;gap:16px}}
@media(prefers-reduced-motion:reduce){{*{{transition:none!important;scroll-behavior:auto!important}}}}
"""


JS = """document.querySelectorAll('form.wa').forEach(function(f){f.addEventListener('submit',function(e){e.preventDefault();
var n=f.querySelector('[name=name]').value.trim(),m=f.querySelector('[name=msg]').value.trim();
var t=(f.dataset.prefix||'')+(n?('\\n'+f.dataset.nameLabel+': '+n):'')+(m?('\\n'+m):'');
window.open(f.dataset.wa+'?text='+encodeURIComponent(t),'_blank','noopener');});});
document.querySelectorAll('details.mnav a').forEach(function(a){a.addEventListener('click',function(){a.closest('details').removeAttribute('open')})});"""


def build_site(
    *,
    profile: dict,
    copy: dict,
    segment: str,
    base: str,
    preview: bool,
    expires_on: str | None = None,
    brand: str = "Sdiek Marketing",
    brand_url: str = "",
    site_url: str | None = None,
) -> dict[str, str]:
    """Return {relative_path: file_text}. `base` is the URL path the site is served under
    (ends with '/'); `site_url` (absolute, for canonical/sitemap) defaults to `base`."""
    if not base.endswith("/"):
        base += "/"
    site_url = (site_url or base).rstrip("/") + "/"
    seg = segment if segment in THEMES else "store"
    theme = THEMES[seg]
    names = {"ar": profile.get("name") or "—", "en": profile.get("name_en") or profile.get("name") or "—"}
    name = names["ar"]
    phone = profile.get("phone") or ""
    address = profile.get("address")
    city = profile.get("city")
    hours = [h for h in (profile.get("hours") or []) if isinstance(h, str)][:7]
    category = profile.get("category")
    rating, reviews = profile.get("rating"), profile.get("reviews")
    place_id = profile.get("place_id")
    socials = {k: v for k, v in (profile.get("links") or {}).items() if isinstance(v, str) and v.startswith("https://")}
    services = [s for s in (copy.get("services") or []) if isinstance(s, dict) and s.get("name_ar")][:8]

    def L(lang, ar, en):
        return ar if lang == "ar" else en

    def href(lang: str, path: str = "") -> str:
        return base + ("en/" if lang == "en" else "") + path

    def absolute(lang: str, path: str = "") -> str:
        return site_url + ("en/" if lang == "en" else "") + path

    def sname(s, lang):
        return s.get("name_" + lang) or s["name_ar"]

    def sdesc(s, lang):
        return s.get("desc_" + lang) or s.get("desc_ar") or ""

    wa_text = {"ar": f"مرحبًا {names['ar']}، وصلت لكم من الموقع", "en": f"Hello {names['en']}, I found you on your website"}
    cta = {lang: copy.get(f"cta_{lang}") or CTA[seg][lang] for lang in LANGS}
    page_paths = ["", "about/", "services/"] + [f"services/{i + 1}/" for i in range(len(services))] + ["faq/", "contact/", "privacy/"]

    business_ld = {
        "@context": "https://schema.org", "@type": _schema_type(seg, category), "@id": site_url + "#business",
        "name": name, "url": site_url, "telephone": phone or None,
        "address": {"@type": "PostalAddress", "streetAddress": address, "addressLocality": city, "addressCountry": "EG"} if address or city else None,
        "areaServed": city, "sameAs": list(socials.values()) or None,
    }
    loc = profile.get("location") or {}
    if isinstance(loc, dict) and loc.get("latitude") is not None:
        business_ld["geo"] = {"@type": "GeoCoordinates", "latitude": loc.get("latitude"), "longitude": loc.get("longitude")}
    business_ld = {k: v for k, v in business_ld.items() if v}

    # ── shared chrome ───────────────────────────────────────────────────────
    def nav_items(lang, path):
        items = [("", tr("home", lang)), ("about/", tr("about", lang)), ("services/", SERVICES_PAGE_TITLE[seg][lang]),
                 ("faq/", tr("faq", lang)), ("contact/", tr("contact", lang))]
        out = []
        for pth, label in items:
            current = (pth == path) or (pth != "" and path.startswith(pth))
            out.append(f'<li><a href="{_e(href(lang, pth))}"{" aria-current=page" if current else ""}>{_e(label)}</a></li>')
        return "".join(out)

    def header(lang: str, path: str) -> str:
        other = "en" if lang == "ar" else "ar"
        items = nav_items(lang, path)
        return (
            f'<header class="hdr"><div class="wrap">'
            f'<a class="logo" href="{_e(href(lang))}"><i aria-hidden="true">{_e(_initials(name))}</i><span>{_e(name)}</span></a>'
            f'<nav class="main" aria-label="{_e(tr("menu", lang))}"><ul>{items}</ul></nav>'
            f'<div class="hdr-actions"><a class="lang" href="{_e(href(other, path))}" hreflang="{other}" lang="{other}">{_e(tr("lang", lang))}</a>'
            + (f'<a class="btn btn--g btn--sm" href="{_e(wa_link(phone, wa_text[lang]))}" target="_blank" rel="noopener">{_e(cta[lang])}</a>' if phone else "")
            + f'<details class="mnav"><summary aria-label="{_e(tr("menu", lang))}">{_icon("menu")}</summary><ul>{items}</ul></details>'
            f'</div></div></header>'
        )

    def footer(lang: str) -> str:
        credit = f'<a href="{_e(brand_url)}" target="_blank" rel="noopener">{_e(brand)}</a>' if brand_url else _e(brand)
        svc_links = "".join(f'<li><a href="{_e(href(lang, f"services/{i + 1}/"))}">{_e(sname(s, lang))}</a></li>' for i, s in enumerate(services))
        contact = []
        if phone:
            contact.append(f'<li><a href="tel:{_e(phone)}" dir="ltr">{_e(local_phone(phone))}</a></li>')
            contact.append(f'<li><a href="{_e(wa_link(phone, wa_text[lang]))}" target="_blank" rel="noopener">WhatsApp</a></li>')
        if address:
            contact.append(f'<li>{_e(address)}</li>')
        contact += [f'<li><a href="{_e(u)}" target="_blank" rel="noopener">{_e(k.capitalize())}</a></li>' for k, u in socials.items()]
        return (
            f'<footer class="ftr"><div class="wrap"><div class="grid">'
            f'<div><h3>{_e(name)}</h3><p>{_e(copy.get("intro_" + lang) or "")}</p></div>'
            f'<div><h3>{_e(SERVICES_PAGE_TITLE[seg][lang])}</h3><ul>{svc_links}</ul></div>'
            f'<div><h3>{_e(tr("contact", lang))}</h3><ul>{"".join(contact)}</ul></div>'
            f'</div>'
            + (f'<p class="note" style="color:#aab4c3;margin-top:22px">{_e(tr("medical", lang))}</p>' if seg == "clinic" else "")
            + f'<div class="base"><span>© {_e(name)} ·<a href="{_e(href(lang, "privacy/"))}">{_e(tr("privacy", lang))}</a></span>'
            f'<span>{_e(tr("by", lang))} {credit}</span></div></div></footer>'
        )

    def crumbs(lang: str, trail: list[tuple[str, str]]):
        full = [("", tr("home", lang))] + trail
        items = []
        for i, (pth, label) in enumerate(full):
            items.append(f'<li aria-current="page">{_e(label)}</li>' if i == len(full) - 1
                         else f'<li><a href="{_e(href(lang, pth))}">{_e(label)}</a></li>')
        ld = {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "name": label, "item": absolute(lang, pth)} for i, (pth, label) in enumerate(full)]}
        return f'<nav class="crumbs wrap" aria-label="breadcrumb"><ol>{"".join(items)}</ol></nav>', ld

    def page(lang: str, path: str, title: str, description: str, body: str,
             extra_ld: list[dict] | None = None, trail: list[tuple[str, str]] | None = None) -> str:
        bc_html, bc_ld = crumbs(lang, trail) if trail is not None else ("", None)
        lds = [business_ld] + ([bc_ld] if bc_ld else []) + (extra_ld or [])
        banner = ""
        if preview:
            banner = (f'<div class="pv" role="note"><strong>{_e(tr("preview", lang))}</strong> — {_e(tr("draft", lang))}'
                      + (f'<span>{_e(tr("expires", lang))} {_e(expires_on)}</span>' if expires_on else "") + "</div>")
        full_title = title if title.startswith(name) else f"{title} | {name}"
        fonts = quote(theme["font"])
        return (
            f'<!doctype html><html lang="{lang}" dir="{"rtl" if lang == "ar" else "ltr"}"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1"><title>{_e(full_title)}</title>'
            f'<meta name="description" content="{_e(description[:160])}">'
            + ('<meta name="robots" content="noindex, nofollow, noarchive">' if preview else "")
            + f'<link rel="canonical" href="{_e(absolute(lang, path))}">'
            f'<link rel="alternate" hreflang="ar" href="{_e(absolute("ar", path))}"><link rel="alternate" hreflang="en" href="{_e(absolute("en", path))}">'
            f'<link rel="alternate" hreflang="x-default" href="{_e(absolute("ar", path))}">'
            f'<meta property="og:type" content="website"><meta property="og:title" content="{_e(full_title)}">'
            f'<meta property="og:description" content="{_e(description[:200])}"><meta property="og:url" content="{_e(absolute(lang, path))}">'
            f'<meta property="og:locale" content="{"ar_EG" if lang == "ar" else "en_US"}"><meta name="theme-color" content="{_e(theme["primary"])}">'
            f'<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
            f'<link href="https://fonts.googleapis.com/css2?family={fonts}:wght@400;600;700;800&family=Inter:wght@400;600;700&display=swap" rel="stylesheet">'
            f'<link rel="stylesheet" href="{_e(base)}assets/site.css">'
            + "".join(_ld(x) for x in lds)
            + f'</head><body><a class="skip" href="#main">{_e(tr("skip", lang))}</a>{banner}{header(lang, path)}{bc_html}'
            f'<main id="main">{body}</main>{footer(lang)}'
            + (f'<a class="fab" href="{_e(wa_link(phone, wa_text[lang]))}" target="_blank" rel="noopener" aria-label="WhatsApp">{_icon("chat")}WhatsApp</a>' if phone else "")
            + f'<script src="{_e(base)}assets/site.js" defer></script></body></html>'
        )

    # ── reusable blocks ─────────────────────────────────────────────────────
    def cta_buttons(lang):
        if not phone:
            return ""
        return (f'<div class="btns"><a class="btn btn--g" href="{_e(wa_link(phone, wa_text[lang]))}" target="_blank" rel="noopener">{_icon("chat")}{_e(cta[lang])}</a>'
                f'<a class="btn btn--o" href="tel:{_e(phone)}">{_icon("phone")}<span dir="ltr">{_e(local_phone(phone))}</span></a></div>')

    def info_cards(lang):
        cards = []
        if address:
            cards.append(f'<div class="card">{_icon("pin")}<h3>{_e(tr("address", lang))}</h3><p>{_e(address)}</p>'
                         f'<a class="go" href="{_e(maps_link(name, address, place_id))}" target="_blank" rel="noopener">{_e(tr("maps", lang))}</a></div>')
        if phone:
            cards.append(f'<div class="card">{_icon("phone")}<h3>{_e(tr("phone", lang))}</h3><a href="tel:{_e(phone)}" dir="ltr">{_e(local_phone(phone))}</a></div>')
        if hours:
            cards.append(f'<div class="card">{_icon("clock")}<h3>{_e(tr("hours", lang))}</h3><ul class="hrs">{"".join(f"<li>{_e(h)}</li>" for h in hours)}</ul></div>')
        return f'<div class="grid grid--3">{"".join(cards)}</div>' if cards else ""

    def band(lang):
        return (f'<div class="wrap"><div class="band"><h2>{_e(tr("ready", lang))}</h2><p>{_e(tr("ready_sub", lang))}</p>'
                + (f'<a class="btn" style="background:#fff;color:var(--ink)" href="{_e(wa_link(phone, wa_text[lang]))}" target="_blank" rel="noopener">{_e(cta[lang])}</a>' if phone else "")
                + "</div></div>")

    def svc_cards(lang, exclude: int | None = None):
        out = []
        for i, s in enumerate(services):
            if i == exclude:
                continue
            out.append(f'<a class="card" href="{_e(href(lang, f"services/{i + 1}/"))}">{_icon("check")}<h3>{_e(sname(s, lang))}</h3>'
                       f'<p>{_e(sdesc(s, lang))}</p><span class="go">{_e(tr("more", lang))}{_icon("arrow", 16)}</span></a>')
        return f'<div class="grid grid--3">{"".join(out)}</div>'

    def faqs(lang) -> list[tuple[str, str]]:
        """Templated from facts only — nothing invented."""
        q = []
        if hours:
            q.append((L(lang, "ما هي مواعيد العمل؟", "What are your opening hours?"), " · ".join(hours)))
        if address:
            q.append((L(lang, f"أين يقع {name}؟", f"Where is {name}?"), address))
        if phone:
            p = local_phone(phone)
            q.append({
                "manufacturer": (L(lang, "كيف أطلب عرض سعر؟", "How do I request a quote?"),
                                 L(lang, f"أرسل المواصفات والكمية على واتساب أو اتصل على {p}.", f"Send the specifications and quantity on WhatsApp or call {p}.")),
                "store": (L(lang, "هل يمكنني الطلب عبر واتساب؟", "Can I order on WhatsApp?"),
                          L(lang, "نعم، أرسل اسم المنتج أو صورته على واتساب ونرد عليك بالتوفر والسعر.",
                            "Yes — send the product name or a photo on WhatsApp and we reply with availability and price.")),
                "clinic": (L(lang, "كيف أحجز موعدًا؟", "How do I book an appointment?"),
                           L(lang, f"اتصل على {p} أو أرسل رسالة واتساب بالاسم واليوم المناسب.", f"Call {p} or send a WhatsApp message with your name and a suitable day.")),
            }[seg])
        if services:
            sep = "، " if lang == "ar" else ", "
            q.append((L(lang, "ما الخدمات المتاحة؟", "What do you offer?"), sep.join(sname(s, lang) for s in services)))
        return q

    # ── pages ───────────────────────────────────────────────────────────────
    files: dict[str, str] = {}
    for lang in LANGS:
        name = names[lang]   # closures below read `name` at call time → the right language per page
        pre = "en/" if lang == "en" else ""
        intro = copy.get("intro_" + lang) or ""
        st = SERVICES_PAGE_TITLE[seg][lang]
        rating_html = ""
        if isinstance(rating, (int, float)) and isinstance(reviews, int) and reviews >= 5:
            rating_html = (f'<a class="rating" href="{_e(maps_link(name, address, place_id))}" target="_blank" rel="noopener">'
                           f'{_icon("star", 18)}<strong>{rating:.1f}</strong> · {reviews} {_e(tr("reviews", lang))}</a>')

        # Home
        body = (
            f'<div class="wrap"><div class="hero"><span class="tag">{_e(LABEL[seg][lang] + (" · " + city if city else ""))}</span>'
            f'<h1>{_e(copy.get("tagline_" + lang) or name)}</h1><p class="lead">{_e(intro)}</p>{cta_buttons(lang)}{rating_html}</div>'
            + (f'<section><h2>{_e(st)}</h2>{svc_cards(lang)}</section>' if services else "")
            + (f'<section><h2>{_e(tr("contact", lang))}</h2>{info_cards(lang)}</section>' if (address or phone or hours) else "")
            + f'</div>{band(lang)}'
        )
        files[pre + "index.html"] = page(lang, "", copy.get("tagline_" + lang) or name, intro or name, body)

        # About
        paras = copy.get("about_" + lang) or []
        paras = paras if isinstance(paras, list) else [str(paras)]
        facts = [(tr("category", lang), category, False), (tr("city", lang), city, False),
                 (tr("address", lang), address, False), (tr("phone", lang), local_phone(phone) if phone else None, True)]
        facts_html = "".join(f'<div><dt>{_e(k)}</dt><dd{" dir=ltr" if ltr else ""}>{_e(v)}</dd></div>' for k, v, ltr in facts if v)
        body = (f'<div class="wrap"><div class="hero"><h1>{_e(tr("about", lang))} — {_e(name)}</h1></div>'
                f'<div class="grid"><div class="prose">{"".join(f"<p>{_e(p)}</p>" for p in paras)}</div>'
                f'<div class="card"><h3>{_e(tr("facts", lang))}</h3><dl class="facts">{facts_html}</dl></div></div></div>{band(lang)}')
        files[pre + "about/index.html"] = page(lang, "about/", tr("about", lang), " ".join(paras) or intro, body,
                                               trail=[("about/", tr("about", lang))])

        # Services + one page per service
        body = f'<div class="wrap"><div class="hero"><h1>{_e(st)}</h1><p class="lead">{_e(intro)}</p></div>{svc_cards(lang)}</div>{band(lang)}'
        files[pre + "services/index.html"] = page(lang, "services/", st, f"{st} — {name}", body, trail=[("services/", st)])
        for i, s in enumerate(services):
            n, d = sname(s, lang), sdesc(s, lang)
            steps = "".join(f"<li>{_e(x)}</li>" for x in tr("steps", lang))
            body = (f'<div class="wrap"><div class="hero"><span class="tag">{_e(st)}</span><h1>{_e(n)}</h1><p class="lead">{_e(d)}</p>{cta_buttons(lang)}</div>'
                    f'<section><h2>{_e(tr("how", lang))}</h2><ol class="steps">{steps}</ol></section>'
                    + (f'<section><h2>{_e(tr("other", lang))}</h2>{svc_cards(lang, exclude=i)}</section>' if len(services) > 1 else "")
                    + f'</div>{band(lang)}')
            svc_ld = {k: v for k, v in {"@context": "https://schema.org", "@type": "Service", "name": n, "description": d,
                                        "provider": {"@id": site_url + "#business"}, "areaServed": city}.items() if v}
            files[pre + f"services/{i + 1}/index.html"] = page(lang, f"services/{i + 1}/", n, d or n, body, extra_ld=[svc_ld],
                                                               trail=[("services/", st), (f"services/{i + 1}/", n)])

        # FAQ
        qa = faqs(lang)
        body = (f'<div class="wrap"><div class="hero"><h1>{_e(tr("faq", lang))}</h1></div>'
                + "".join(f'<details class="faq"><summary>{_e(q)}</summary><p>{_e(a)}</p></details>' for q, a in qa)
                + f'</div>{band(lang)}')
        faq_ld = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in qa]}
        files[pre + "faq/index.html"] = page(lang, "faq/", tr("faq", lang), f'{tr("faq", lang)} — {name}', body,
                                             extra_ld=[faq_ld] if qa else None, trail=[("faq/", tr("faq", lang))])

        # Contact: WhatsApp form (nothing stored) + map
        form = ""
        if phone:
            form = (f'<form class="wa" data-wa="{_e(wa_link(phone))}" data-prefix="{_e(wa_text[lang])}" data-name-label="{_e(tr("name", lang))}">'
                    f'<label>{_e(tr("name", lang))}<input name="name" autocomplete="name" required></label>'
                    f'<label>{_e(tr("need", lang))}<textarea name="msg" required></textarea></label>'
                    f'<button class="btn btn--g" type="submit">{_icon("chat")}{_e(tr("send", lang))}</button>'
                    f'<p class="note">{_e(tr("form_note", lang))}</p></form>')
        mp = (f'<iframe class="map" title="{_e(tr("address", lang))}" loading="lazy" referrerpolicy="no-referrer-when-downgrade" '
              f'src="{_e(maps_embed(name, address))}"></iframe>') if address else ""
        body = (f'<div class="wrap"><div class="hero"><h1>{_e(tr("contact", lang))}</h1><p class="lead">{_e(intro)}</p></div>'
                f'{info_cards(lang)}<section><div class="grid">{form}{mp}</div></section></div>')
        files[pre + "contact/index.html"] = page(lang, "contact/", tr("contact", lang), f'{tr("contact", lang)} — {name}', body,
                                                 trail=[("contact/", tr("contact", lang))])

        # Privacy
        priv = L(lang,
                 [f"هذا الموقع يخص {name}. لا يستخدم الموقع ملفات تعريف ارتباط للتتبع ولا يخزّن أي بيانات شخصية.",
                  "عند استخدام نموذج التواصل، تُفتح رسالة في تطبيق واتساب الخاص بك وتُرسل منه مباشرة؛ لا تمر الرسالة عبر هذا الموقع.",
                  "يتم تحميل الخطوط من Google Fonts والخريطة من خرائط Google، وقد تخضع لسياسات الخصوصية الخاصة بهما.",
                  "لأي استفسار عن بياناتك تواصل معنا عبر الهاتف أو واتساب."],
                 [f"This website belongs to {name}. It uses no tracking cookies and stores no personal data.",
                  "The contact form opens a message in your own WhatsApp app and sends it from there; the message never passes through this site.",
                  "Fonts load from Google Fonts and the map from Google Maps, which have their own privacy policies.",
                  "For any question about your data, contact us by phone or WhatsApp."])
        body = f'<div class="wrap"><div class="hero"><h1>{_e(tr("privacy", lang))}</h1></div><div class="prose">{"".join(f"<p>{_e(p)}</p>" for p in priv)}</div></div>'
        files[pre + "privacy/index.html"] = page(lang, "privacy/", tr("privacy", lang), priv[0], body,
                                                 trail=[("privacy/", tr("privacy", lang))])

    name = names["ar"]
    files["404.html"] = page("ar", "", tr("notfound", "ar"), tr("notfound", "ar"),
                             f'<div class="wrap err"><h1>404</h1><p class="lead">{_e(tr("notfound", "ar"))} · Page not found</p>'
                             f'<a class="btn btn--p" href="{_e(href("ar"))}">{_e(tr("back", "ar"))}</a></div>')
    files["assets/site.css"] = _css(theme)
    files["assets/site.js"] = JS
    urls = "".join(
        f"<url><loc>{_e(absolute(lang, p))}</loc>"
        + "".join(f'<xhtml:link rel="alternate" hreflang="{x}" href="{_e(absolute(x, p))}"/>' for x in LANGS)
        + "</url>" for lang in LANGS for p in page_paths)
    files["sitemap.xml"] = ('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
                            f'xmlns:xhtml="http://www.w3.org/1999/xhtml">{urls}</urlset>')
    files["robots.txt"] = "User-agent: *\nDisallow: /\n" if preview else f"User-agent: *\nAllow: /\n\nSitemap: {site_url}sitemap.xml\n"
    return files


def render_site(*, profile: dict, copy: dict, segment: str, preview: bool, expires_on: str | None = None,
                brand: str = "Sdiek Marketing", brand_url: str = "") -> str:
    """Convenience: the Arabic home page as one string (tests, quick checks)."""
    return build_site(profile=profile, copy=copy, segment=segment, base="/", preview=preview,
                      expires_on=expires_on, brand=brand, brand_url=brand_url)["index.html"]
