"""The output-language selector: each choice must produce a distinct, correct instruction
so the AI writes in فصحى / English / عامية as the tenant chose."""
from app.services.ai_service import _lang_instruction


def test_english():
    assert "English" in _lang_instruction("en")


def test_masri_is_colloquial_not_fusha():
    ins = _lang_instruction("masri")
    assert "العامية المصرية" in ins
    assert "وليس بالفصحى" in ins


def test_arabic_default_is_fusha():
    ins = _lang_instruction("ar")
    assert "الفصحى" in ins


def test_unknown_falls_back_to_arabic():
    # An unexpected value must not yield an empty/None instruction.
    assert _lang_instruction("") == _lang_instruction("ar")
    assert _lang_instruction("zz") == _lang_instruction("ar")
