"""Render a business's site as ONE self-contained HTML file (Arabic-first, English toggle).

Why one file: it is stored in object storage and served by the API as-is — no build step,
no per-prospect deploy. Every value from the profile/copy is HTML-escaped (the data comes
from the open web and from an LLM). Previews carry `noindex` and a private-preview banner;
the published version drops both.

No third-party photos are used: we don't own a business's Google/Facebook images, so the
design relies on typography, colour and icons until the owner sends their own.
"""
from __future__ import annotations

from html import escape
from urllib.parse import quote

from app.site_factory.segments import LABEL, THEMES

ICONS = {
    "phone": '<path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1.9.4 1.8.7 2.7a2 2 0 0 1-.5 2.1L8 9.8a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.4c.9.3 1.8.6 2.7.7a2 2 0 0 1 1.7 2z"/>',
    "pin": '<path d="M21 10c0 7-9 13-9 13S3 17 3 10a9 9 0 1 1 18 0z"/><circle cx="12" cy="10" r="3"/>',
    "clock": '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
    "check": '<path d="M20 6 9 17l-5-5"/>',
    "chat": '<path d="M21 11.5a8.4 8.4 0 0 1-9 8.4 8.5 8.5 0 0 1-3.8-.9L3 21l1.9-5.2A8.4 8.4 0 0 1 12 3a8.4 8.4 0 0 1 9 8.5z"/>',
}


def _icon(name: str) -> str:
    return (f'<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" '
            f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{ICONS[name]}</svg>')


def _e(v) -> str:
    return escape(str(v or ""), quote=True)


def wa_link(phone_e164: str, text: str = "") -> str:
    digits = "".join(ch for ch in (phone_e164 or "") if ch.isdigit())
    return f"https://wa.me/{digits}" + (f"?text={quote(text)}" if text else "")


def maps_link(name: str, address: str | None, place_id: str | None = None) -> str:
    q = quote(", ".join(x for x in [name, address] if x))
    if place_id:
        return f"https://www.google.com/maps/search/?api=1&query={q}&query_place_id={quote(place_id)}"
    return f"https://www.google.com/maps/search/?api=1&query={q}"


GENERIC_PREFIXES = {"مصنع", "شركة", "محل", "معرض", "عيادة", "مركز", "د.", "د", "دكتور", "مؤسسة", "factory", "the", "dr", "dr."}


def _initials(name: str) -> str:
    """Logo monogram: skip generic words ("مصنع", "عيادة", "Dr."), then 1 Arabic letter or 2 Latin initials."""
    words = [w for w in (name or "").replace("-", " ").split() if w]
    core = [w for w in words if w.lower().strip(".") not in GENERIC_PREFIXES and w.lower() not in GENERIC_PREFIXES] or words
    if not core:
        return "•"
    first = core[0].removeprefix("ال") if core[0].startswith("ال") and len(core[0]) > 3 else core[0]
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


def render_site(
    *,
    profile: dict,
    copy: dict,
    segment: str,
    preview: bool,
    expires_label: str | None = None,
    brand: str = "Sdiek Marketing",
    brand_url: str = "",
) -> str:
    theme = THEMES.get(segment, THEMES["store"])
    name = profile.get("name") or "—"
    phone = profile.get("phone") or ""
    address = profile.get("address")
    city = profile.get("city")
    hours = profile.get("hours") or []          # ["السبت–الخميس 9:00–17:00", ...]
    links = profile.get("links") or {}           # {"facebook": url, "instagram": url}
    seg_label = LABEL.get(segment, LABEL["store"])

    services_ar = copy.get("services_ar") or []
    services_en = copy.get("services_en") or []
    wa_text = f"مرحبًا {name}، وصلت لكم من الموقع"

    def bi(ar: str, en: str, tag: str = "span", cls: str = "") -> str:
        c = f' class="{cls}"' if cls else ""
        return f'<{tag}{c} data-ar>{_e(ar)}</{tag}><{tag}{c} data-en hidden>{_e(en)}</{tag}>'

    services_html = "".join(
        f'<li>{_icon("check")}{bi(ar, services_en[i] if i < len(services_en) else ar)}</li>'
        for i, ar in enumerate(services_ar[:6])
    )
    hours_html = "".join(f"<li>{_e(h)}</li>" for h in hours[:7])
    social_html = "".join(
        f'<a href="{_e(url)}" target="_blank" rel="noopener">{_e(k.capitalize())}</a>'
        for k, url in links.items() if isinstance(url, str) and url.startswith("https://")
    )

    banner = ""
    if preview:
        banner = (
            '<div class="pv" role="note">'
            f'<strong>{bi("معاينة خاصة — غير منشورة", "Private preview — not published")}</strong> '
            f'{bi(f"أعدّها {brand} لـ {name}. النصوص مقترحة ونعدّلها معك.", f"Prepared by {brand} for {name}. Text is a draft we edit with you.")}'
            + (f' <span class="pv__exp">{_e(expires_label)}</span>' if expires_label else "")
            + "</div>"
        )

    robots = '<meta name="robots" content="noindex, nofollow, noarchive">' if preview else ""
    disclaimer = ""
    if segment == "clinic":
        disclaimer = (
            '<p class="note">'
            + bi("المعلومات للتعريف بالعيادة فقط ولا تغني عن الاستشارة الطبية.",
                 "Information about the clinic only — not a substitute for medical advice.")
            + "</p>"
        )

    credit = (f'<a href="{_e(brand_url)}" target="_blank" rel="noopener">{_e(brand)}</a>'
              if brand_url else _e(brand))

    return f"""<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(name)}{' — ' + _e(city) if city else ''}</title>
<meta name="description" content="{_e(copy.get('about_ar') or name)}">
{robots}
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family={quote(theme['font'])}:wght@400;600;700&display=swap" rel="stylesheet">
<style>
:root{{--p:{theme['primary']};--a:{theme['accent']};--bg:{theme['bg']};--ink:{theme['ink']};--mut:#5b6575;--line:#dde2ea}}
*{{box-sizing:border-box;margin:0}}
body{{font-family:'{theme['font']}',system-ui,sans-serif;background:var(--bg);color:var(--ink);line-height:1.7}}
a{{color:inherit}}
.wrap{{max-width:1080px;margin-inline:auto;padding-inline:20px}}
.pv{{position:sticky;top:0;z-index:9;background:#111827;color:#fff;font-size:.88rem;padding:10px 20px;text-align:center}}
.pv__exp{{opacity:.7;margin-inline-start:8px}}
header.top{{display:flex;justify-content:space-between;align-items:center;padding:18px 0;gap:12px}}
.logo{{display:flex;align-items:center;gap:10px;font-weight:700;text-decoration:none}}
.logo i{{width:40px;height:40px;border-radius:12px;background:var(--p);color:#fff;display:grid;place-items:center;font-style:normal;font-size:.95rem}}
.lang{{white-space:nowrap;flex:none;border:1px solid var(--line);background:#fff;border-radius:99px;padding:6px 14px;cursor:pointer;font:inherit;font-size:.85rem}}
.hero{{padding:56px 0 64px;display:grid;gap:22px}}
.tag{{display:inline-flex;gap:8px;align-items:center;font-size:.85rem;color:var(--p);font-weight:600;background:#fff;border:1px solid var(--line);padding:6px 12px;border-radius:99px;width:fit-content}}
h1{{font-size:clamp(2rem,6vw,3.4rem);line-height:1.2}}
.lead{{font-size:1.1rem;color:var(--mut);max-width:60ch}}
.btns{{display:flex;flex-wrap:wrap;gap:12px}}
.btn{{display:inline-flex;align-items:center;gap:10px;padding:14px 22px;border-radius:12px;font-weight:600;text-decoration:none}}
.btn--p{{background:var(--p);color:#fff}}
.btn--g{{background:#25d366;color:#08311a}}
.btn--o{{background:#fff;border:1px solid var(--line)}}
section{{padding:48px 0;border-top:1px solid var(--line)}}
h2{{font-size:1.5rem;margin-bottom:18px}}
.grid{{display:grid;gap:16px}}
@media(min-width:760px){{.grid{{grid-template-columns:repeat(3,1fr)}}}}
.card{{background:#fff;border:1px solid var(--line);border-radius:16px;padding:22px;display:grid;gap:10px;align-content:start}}
.card svg{{color:var(--p)}}
ul.svc{{list-style:none;padding:0;display:grid;gap:12px}}
ul.svc li{{display:flex;gap:10px;align-items:flex-start;background:#fff;border:1px solid var(--line);border-radius:12px;padding:14px 16px}}
ul.svc svg{{color:var(--a);flex:none;margin-top:3px}}
ul.hrs{{list-style:none;padding:0}}
.soc{{display:flex;gap:14px;flex-wrap:wrap}}
.note{{font-size:.85rem;color:var(--mut);margin-top:12px}}
footer{{padding:30px 0 90px;color:var(--mut);font-size:.85rem;border-top:1px solid var(--line)}}
.fab{{position:fixed;bottom:18px;inset-inline-start:18px;background:#25d366;color:#08311a;border-radius:99px;padding:12px 18px;font-weight:700;text-decoration:none;display:flex;gap:8px;align-items:center;box-shadow:0 10px 30px -10px rgba(0,0,0,.35)}}
[hidden]{{display:none!important}}
</style>
</head>
<body>
{banner}
<div class="wrap">
  <header class="top">
    <a class="logo" href="#top"><i>{_e(_initials(name))}</i><span>{_e(name)}</span></a>
    <button class="lang" type="button" onclick="toggleLang()">English / عربي</button>
  </header>

  <main id="top">
    <div class="hero">
      <span class="tag">{bi(seg_label['ar'] + (' · ' + city if city else ''), seg_label['en'] + (' · ' + city if city else ''))}</span>
      <h1>{bi(copy.get('tagline_ar') or name, copy.get('tagline_en') or name)}</h1>
      <p class="lead">{bi(copy.get('about_ar') or '', copy.get('about_en') or '')}</p>
      <div class="btns">
        {f'<a class="btn btn--g" href="{_e(wa_link(phone, wa_text))}" target="_blank" rel="noopener">{_icon("chat")}{bi(copy.get("cta_ar") or "واتساب", copy.get("cta_en") or "WhatsApp")}</a>' if phone else ''}
        {f'<a class="btn btn--o" href="tel:{_e(phone)}">{_icon("phone")}<span dir="ltr">{_e(local_phone(phone))}</span></a>' if phone else ''}
      </div>
    </div>

    {f'<section><h2>{bi("خدماتنا", "What we offer")}</h2><ul class="svc">{services_html}</ul></section>' if services_html else ''}

    <section>
      <h2>{bi("تواصل وزيارة", "Contact & visit")}</h2>
      <div class="grid">
        {f'<div class="card">{_icon("pin")}<strong>{bi("العنوان", "Address")}</strong><span>{_e(address)}</span><a href="{_e(maps_link(name, address, profile.get("place_id")))}" target="_blank" rel="noopener">{bi("افتح على الخريطة", "Open in Maps")}</a></div>' if address else ''}
        {f'<div class="card">{_icon("phone")}<strong>{bi("الهاتف", "Phone")}</strong><a href="tel:{_e(phone)}" dir="ltr">{_e(local_phone(phone))}</a></div>' if phone else ''}
        {f'<div class="card">{_icon("clock")}<strong>{bi("مواعيد العمل", "Opening hours")}</strong><ul class="hrs">{hours_html}</ul></div>' if hours_html else ''}
      </div>
      {f'<div class="soc" style="margin-top:18px">{social_html}</div>' if social_html else ''}
      {disclaimer}
    </section>
  </main>

  <footer>© {_e(name)} · {bi("تصميم وتطوير", "Designed & built by")} {credit}</footer>
</div>
{f'<a class="fab" href="{_e(wa_link(phone, wa_text))}" target="_blank" rel="noopener">{_icon("chat")}واتساب</a>' if phone else ''}
<script>
function toggleLang(){{var h=document.documentElement,ar=h.lang==='ar';h.lang=ar?'en':'ar';h.dir=ar?'ltr':'rtl';
document.querySelectorAll('[data-ar]').forEach(function(e){{e.hidden=ar}});document.querySelectorAll('[data-en]').forEach(function(e){{e.hidden=!ar}});}}
</script>
</body>
</html>"""
