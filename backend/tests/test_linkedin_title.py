"""LinkedIn discovery — parsing name/role/company out of Google search-result titles."""
import pytest

from scrapers.linkedin_search import parse_linkedin_title


def test_full_title_name_role_company():
    name, role, company = parse_linkedin_title("Ahmed Ali - Sales Manager - ACME Corp | LinkedIn")
    assert name == "Ahmed Ali"
    assert role == "Sales Manager"
    assert company == "ACME Corp"


def test_name_and_role_only():
    name, role, company = parse_linkedin_title("Sara Mohamed - Marketing Lead | LinkedIn")
    assert name == "Sara Mohamed"
    assert role == "Marketing Lead"
    assert company is None


def test_name_only_with_location():
    name, role, company = parse_linkedin_title("Omar Hassan - Egypt | LinkedIn")
    assert name == "Omar Hassan"
    # "Egypt" lands in the role slot; acceptable — no company present.
    assert company is None


def test_en_dash_separator():
    name, role, company = parse_linkedin_title("Nour Adel – CEO – Nile Foods – LinkedIn")
    assert name == "Nour Adel"
    assert role == "CEO"
    assert company == "Nile Foods"


@pytest.mark.parametrize("bad", ["", None, "   "])
def test_empty_returns_none(bad):
    assert parse_linkedin_title(bad) == (None, None, None)
