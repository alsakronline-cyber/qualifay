"""Guards on the paths that send real things or serve attacker-supplied bytes.

These are pure-function tests (no DB, no network) covering the pieces where a silent
bug is expensive: phone normalization (wrong recipient), download headers (injection /
inline XSS), mail headers (injection), and the warmup cap schedule (bans).
"""
from app.lib.phone import normalize_egyptian_phone, jid_to_phone
from app.services.warmup_service import get_cap_for_day
from app.services.email_service import _hdr
from app.services.email_inbox_service import _html_to_text
from app.api.conversations import _safe_download_headers


# ── Phone normalization → E.164 ───────────────────────────────────────────────
def test_phone_all_egyptian_forms_normalize_to_e164():
    expected = "+201001234567"
    for raw in ["01001234567", "00201001234567", "+201001234567",
                "201001234567", "0201001234567", "1001234567",
                " 010 0123 4567 ", "010-0123-4567"]:
        assert normalize_egyptian_phone(raw) == expected, raw


def test_phone_invalid_returns_none():
    for raw in ["", "   ", "hello", "12345", "0000000000", None]:
        assert normalize_egyptian_phone(raw) is None, raw


def test_jid_to_phone_strips_whatsapp_suffix():
    assert jid_to_phone("201001234567@s.whatsapp.net") == "+201001234567"
    assert jid_to_phone("201001234567@c.us") == "+201001234567"
    assert jid_to_phone("") is None


# ── Attachment / media download headers (S1, S2, S4 guards) ───────────────────
def test_download_filename_strips_header_injection():
    _, headers = _safe_download_headers('evil"\r\nSet-Cookie: x=1.pdf', "application/pdf")
    cd = headers["Content-Disposition"]
    assert "\r" not in cd and "\n" not in cd
    assert '"' not in cd.split("filename=")[1][1:-1]  # no bare quote inside the value


def test_download_active_types_forced_to_attachment():
    for ct in ["text/html", "image/svg+xml", "application/xml", "text/javascript"]:
        media_type, headers = _safe_download_headers("x", ct)
        assert media_type == "application/octet-stream", ct
        assert headers["Content-Disposition"].startswith("attachment"), ct
        assert headers["X-Content-Type-Options"] == "nosniff"


def test_download_normal_file_served_inline_unchanged():
    media_type, headers = _safe_download_headers("report.pdf", "application/pdf")
    assert media_type == "application/pdf"
    assert headers["Content-Disposition"] == 'inline; filename="report.pdf"'


# ── Mail header sanitization (S3 guard) ───────────────────────────────────────
def test_mail_header_strips_crlf():
    out = _hdr("Hello\r\nBcc: attacker@example.com")
    assert "\r" not in out and "\n" not in out


# ── Warmup cap schedule (ban guard) ───────────────────────────────────────────
def test_warmup_cap_schedule_boundaries():
    assert get_cap_for_day(1) == 10       # week 1
    assert get_cap_for_day(7) == 10
    assert get_cap_for_day(8) == 30       # week 2
    assert get_cap_for_day(15) == 75
    assert get_cap_for_day(22) == 150
    assert get_cap_for_day(31) == 200     # stable
    assert get_cap_for_day(9999) == 200


# ── HTML email → readable text ────────────────────────────────────────────────
def test_html_to_text_preserves_line_breaks_and_strips_tags():
    html = "<p>Hello</p><p>World</p><br>Line3"
    out = _html_to_text(html)
    assert "<" not in out and ">" not in out
    assert "Hello" in out and "World" in out and "Line3" in out
    assert "\n" in out  # block elements became line breaks, not a run-on
