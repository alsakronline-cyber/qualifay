"""BaseScraper.parse_cookie_string — session-cookie parsing for LinkedIn/Facebook."""
from scrapers.base import BaseScraper


def test_empty_returns_no_cookies():
    assert BaseScraper.parse_cookie_string("", ".linkedin.com") == []
    assert BaseScraper.parse_cookie_string(None, ".linkedin.com") == []


def test_bare_token_uses_default_name():
    out = BaseScraper.parse_cookie_string("ABC123", ".linkedin.com", default_name="li_at")
    assert len(out) == 1
    assert out[0]["name"] == "li_at"
    assert out[0]["value"] == "ABC123"
    assert out[0]["domain"] == ".linkedin.com"


def test_full_cookie_string_multiple_pairs():
    out = BaseScraper.parse_cookie_string("c_user=100; xs=abc:def", ".facebook.com")
    names = {c["name"]: c["value"] for c in out}
    assert names == {"c_user": "100", "xs": "abc:def"}
    assert all(c["domain"] == ".facebook.com" for c in out)


def test_skips_malformed_pairs():
    out = BaseScraper.parse_cookie_string("li_at=X; ; garbage; =nope; k=", ".linkedin.com")
    assert [c["name"] for c in out] == ["li_at"]


def test_whitespace_trimmed():
    out = BaseScraper.parse_cookie_string("  li_at = X  ", ".linkedin.com")
    assert out[0]["name"] == "li_at" and out[0]["value"] == "X"
