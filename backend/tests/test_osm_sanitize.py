"""OSM scraper — Overpass keyword sanitization (injection / ReDoS guard)."""
import pytest

from scrapers.osm import _sanitize_overpass_kw


def test_strips_quotes_and_brackets():
    out = _sanitize_overpass_kw('hospital"[out:json]')
    assert '"' not in out
    assert '[' not in out and ']' not in out
    assert 'hospital' in out


def test_strips_backslash_and_regex_meta():
    out = _sanitize_overpass_kw(r'a\b.*c|d')
    assert '\\' not in out
    assert '|' not in out
    assert '*' not in out


def test_keeps_arabic_alnum_and_spaces():
    assert _sanitize_overpass_kw('صيدلية pharmacy 24') == 'صيدلية pharmacy 24'


def test_keeps_hyphen():
    assert _sanitize_overpass_kw('e-commerce') == 'e-commerce'


def test_caps_length_at_60():
    assert len(_sanitize_overpass_kw('x' * 200)) <= 60


@pytest.mark.parametrize("bad", ['', '"""', '[]{}', '\\\\'])
def test_empty_or_all_stripped_defaults_to_company(bad):
    assert _sanitize_overpass_kw(bad) == 'company'


def test_none_input_defaults_to_company():
    assert _sanitize_overpass_kw(None) == 'company'
