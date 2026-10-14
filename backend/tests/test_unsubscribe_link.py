"""Unsubscribe links: signed per lead + tenant, carried in the email footer and in the
RFC 8058 one-click List-Unsubscribe headers."""
from types import SimpleNamespace

from app.services.email_service import build_message
from app.services.unsubscribe import make_token, read_token, unsubscribe_url, with_unsubscribe


def _lead(lang="ar"):
    return SimpleNamespace(id="lead-1", tenant_id="ten-1", language=lang)


def test_token_round_trip_and_purpose_required():
    claims = read_token(make_token("lead-1", "ten-1"))
    assert claims["lead_id"] == "lead-1" and claims["tenant_id"] == "ten-1"
    import jwt
    from app.core.config import settings
    other = jwt.encode({"lead_id": "lead-1"}, settings.SECRET_KEY, algorithm="HS256")
    assert read_token(other) is None
    assert read_token("garbage") is None


def test_footer_is_in_the_leads_language():
    body, url = with_unsubscribe("Hello", _lead("en"))
    assert body.startswith("Hello") and url in body and "Unsubscribe" in body
    body_ar, _ = with_unsubscribe("مرحبا", _lead("ar"))
    assert "إلغاء الاشتراك" in body_ar
    assert "/api/v1/webhook/unsubscribe?token=" in unsubscribe_url(_lead())


def test_one_click_headers_only_when_a_link_is_given():
    url = unsubscribe_url(_lead())
    msg = build_message("Acme", "sales@acme.test", "x@y.test", "Hi", "body", url)
    assert msg["List-Unsubscribe"].startswith(f"<{url}>")
    assert "mailto:sales@acme.test" in msg["List-Unsubscribe"]
    assert msg["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    plain = build_message("Acme", "sales@acme.test", "x@y.test", "Hi", "body")
    assert plain["List-Unsubscribe-Post"] is None
