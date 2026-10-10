"""Owner-chosen design for a business site: a reference site's *style* + the business's logo colors.

The owner picks a reference (from the Awwwards board or any URL). We read its computed style
in a real browser — light/dark, font character, heading case and weight, corner radius — and
map that onto our own templates. We never copy the reference's code, text or images.
Colors come from the business's own logo (owner confirms/edits before building).
"""
from __future__ import annotations

import base64
import io
import re

# ── fonts we can serve (Google Fonts), and how reference fonts map onto them ──
LATIN_FONTS = {
    "inter": "Inter", "poppins": "Poppins", "montserrat": "Montserrat", "manrope": "Manrope", "dm sans": "DM Sans",
    "outfit": "Outfit", "sora": "Sora", "plus jakarta sans": "Plus Jakarta Sans", "space grotesk": "Space Grotesk",
    "work sans": "Work Sans", "roboto": "Roboto", "open sans": "Open Sans", "lato": "Lato", "rubik": "Rubik",
    "playfair display": "Playfair Display", "cormorant garamond": "Cormorant Garamond", "dm serif display": "DM Serif Display",
    "lora": "Lora", "libre baskerville": "Libre Baskerville", "fraunces": "Fraunces", "syne": "Syne", "archivo": "Archivo",
}
ARABIC_FOR = {"serif": "Noto Naskh Arabic", "display": "Cairo", "sans": "IBM Plex Sans Arabic"}
SERIF_HINTS = ("serif", "garamond", "playfair", "times", "georgia", "baskerville", "cormorant", "fraunces", "lora", "canela", "tiempos", "freight")
DISPLAY_HINTS = ("syne", "grotesk", "druk", "anton", "bebas", "archivo black", "monument", "neue machina", "clash")


def _hex(c: tuple[int, int, int]) -> str:
    return "#%02x%02x%02x" % c


def parse_css_color(value: str | None) -> tuple[int, int, int] | None:
    if not value:
        return None
    m = re.match(r"rgba?\(\s*(\d+)[,\s]+(\d+)[,\s]+(\d+)(?:[,\s/]+([\d.]+))?", value)
    if m:
        if m.group(4) is not None and float(m.group(4)) < 0.1:
            return None   # transparent
        return int(m.group(1)), int(m.group(2)), int(m.group(3))
    m = re.match(r"#([0-9a-f]{6})", value.strip().lower())
    if m:
        h = m.group(1)
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return None


def luminance(c: tuple[int, int, int]) -> float:
    def ch(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = c
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    la, lb = sorted([luminance(a), luminance(b)], reverse=True)
    return (la + 0.05) / (lb + 0.05)


def font_character(family: str | None) -> str:
    f = (family or "").lower()
    if any(h in f for h in SERIF_HINTS) and "sans" not in f:
        return "serif"
    if any(h in f for h in DISPLAY_HINTS):
        return "display"
    return "sans"


def map_font(family: str | None) -> str:
    """First family in a CSS font stack that we can serve, else a same-character equivalent."""
    for part in (family or "").split(","):
        name = part.strip().strip("'\"").lower()
        if name in LATIN_FONTS:
            return LATIN_FONTS[name]
    return {"serif": "Playfair Display", "display": "Space Grotesk", "sans": "Inter"}[font_character(family)]


def style_from_computed(raw: dict) -> dict:
    """Turn computed styles read from the reference page into our style profile."""
    bg = parse_css_color(raw.get("bodyBg")) or parse_css_color(raw.get("htmlBg")) or (255, 255, 255)
    ink = parse_css_color(raw.get("bodyColor")) or ((20, 20, 20) if luminance(bg) > 0.4 else (240, 240, 240))
    dark = luminance(bg) < 0.25
    heading_family = raw.get("headingFont") or raw.get("bodyFont")
    radius_vals = [float(x) for x in re.findall(r"[\d.]+", str(raw.get("radius") or "0"))[:1]] or [0.0]
    radius = max(0, min(28, int(radius_vals[0])))
    weight = int(re.sub(r"\D", "", str(raw.get("headingWeight") or "600")) or 600)
    character = font_character(heading_family)
    return {
        "dark": dark,
        "bg": _hex(bg), "ink": _hex(ink),
        "heading_font": map_font(heading_family),
        "body_font": map_font(raw.get("bodyFont")),
        "arabic_font": ARABIC_FOR[character],
        "character": character,
        "uppercase": str(raw.get("headingTransform") or "").lower() == "uppercase",
        "heading_weight": max(300, min(900, weight)),
        "radius": radius,
        "title": (raw.get("title") or "")[:120],
    }


# The script evaluated inside the reference page (read-only: no clicks, no form input).
READ_STYLE_JS = """() => {
  const cs = (el) => el ? getComputedStyle(el) : null;
  const h = document.querySelector('h1') || document.querySelector('h2');
  const btn = document.querySelector('a[class*=btn], button, a[class*=button], .button');
  const b = cs(document.body), hh = cs(h), bb = cs(btn), ht = cs(document.documentElement);
  return {
    title: document.title,
    bodyBg: b && b.backgroundColor, htmlBg: ht && ht.backgroundColor, bodyColor: b && b.color,
    bodyFont: b && b.fontFamily, headingFont: hh && hh.fontFamily, headingWeight: hh && hh.fontWeight,
    headingTransform: hh && hh.textTransform, radius: bb && bb.borderRadius,
  };
}"""


async def analyze_reference(url: str) -> dict:
    """Open the reference in headless Chromium, read its style, and return the profile plus a
    small JPEG thumbnail (data URL) so the owner can see what they picked."""
    if not re.match(r"^https?://", url or ""):
        raise ValueError("Reference must be an http(s) URL")
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(args=["--no-sandbox"])
        try:
            page = await browser.new_page(viewport={"width": 1440, "height": 900})
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(5000)          # let fonts / hero animations settle
            raw = await page.evaluate(READ_STYLE_JS)
            shot = await page.screenshot(type="jpeg", quality=55)
        finally:
            await browser.close()
    profile = style_from_computed(raw or {})
    profile["url"] = url
    profile["thumbnail"] = "data:image/jpeg;base64," + base64.b64encode(_shrink(shot)).decode()
    return profile


def _shrink(jpeg: bytes, width: int = 480) -> bytes:
    from PIL import Image
    im = Image.open(io.BytesIO(jpeg)).convert("RGB")
    im.thumbnail((width, width))
    out = io.BytesIO()
    im.save(out, "JPEG", quality=60)
    return out.getvalue()


# ── logo → palette ─────────────────────────────────────────────────────────

def normalize_logo(data: bytes, max_side: int = 512) -> bytes:
    """Validate an uploaded/fetched image and re-encode it as a bounded PNG (strips metadata)."""
    from PIL import Image
    im = Image.open(io.BytesIO(data))
    im.load()
    if im.width * im.height > 25_000_000:
        raise ValueError("Image too large")
    im = im.convert("RGBA")
    im.thumbnail((max_side, max_side))
    out = io.BytesIO()
    im.save(out, "PNG", optimize=True)
    return out.getvalue()


def logo_palette(png: bytes, n: int = 5) -> dict:
    """Dominant brand colors of a logo, ignoring transparent pixels and near-white/black/gray
    backgrounds. Returns {colors: [...hex], primary, accent}."""
    from PIL import Image
    im = Image.open(io.BytesIO(png)).convert("RGBA")
    im.thumbnail((160, 160))
    px = [(r, g, b) for (r, g, b, a) in im.getdata() if a > 128]
    if not px:
        return {"colors": [], "primary": None, "accent": None}
    flat = Image.new("RGB", (len(px), 1))
    flat.putdata(px)
    q = flat.quantize(colors=8, method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette()
    counts = sorted(q.getcolors(), reverse=True)            # [(count, index)]
    total = sum(c for c, _ in counts)

    def sat(c):
        mx, mn = max(c), min(c)
        return 0 if mx == 0 else (mx - mn) / mx

    ranked = []
    for count, idx in counts:
        c = tuple(pal[idx * 3: idx * 3 + 3])
        lum = luminance(c)
        if count / total < 0.02:
            continue
        neutral = sat(c) < 0.18 or lum > 0.9 or lum < 0.02
        ranked.append((neutral, -count, c))
    ranked.sort()
    colors = [_hex(c) for _, _, c in ranked][:n]
    brand = [c for neutral, _, c in ranked if not neutral]
    primary = brand[0] if brand else (ranked[0][2] if ranked else None)
    accent = next((c for c in brand[1:] if _distance(c, primary) > 90), None) if primary else None
    return {"colors": colors, "primary": _hex(primary) if primary else None, "accent": _hex(accent) if accent else None}


def _distance(a, b) -> float:
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


def readable_on(bg_hex: str, fg_hex: str, min_ratio: float = 3.0) -> bool:
    a, b = parse_css_color(bg_hex), parse_css_color(fg_hex)
    return bool(a and b and contrast(a, b) >= min_ratio)


def build_theme(style: dict | None, colors: dict | None, fallback: dict) -> dict:
    """Merge the reference style and the logo colors into the builder's theme tokens."""
    style, colors = style or {}, colors or {}
    dark = bool(style.get("dark"))
    bg = style.get("bg") or fallback["bg"]
    ink = style.get("ink") or fallback["ink"]
    if not readable_on(bg, ink, 4.5):
        ink = "#f2f4f7" if dark else "#121826"
    primary = colors.get("primary") or fallback["primary"]
    if not readable_on(bg, primary, 2.2):               # brand color invisible on this background
        primary = fallback["primary"] if readable_on(bg, fallback["primary"], 2.2) else ink
    return {
        "primary": primary,
        "accent": colors.get("accent") or fallback["accent"],
        "bg": bg, "ink": ink, "dark": dark,
        "font": style.get("arabic_font") or fallback["font"],
        "font_en": style.get("body_font") or "Inter",
        "heading_en": style.get("heading_font") or style.get("body_font") or "Inter",
        "uppercase": bool(style.get("uppercase")),
        "heading_weight": int(style.get("heading_weight") or 700),
        "radius": int(style.get("radius") if style.get("radius") is not None else 16),
    }
