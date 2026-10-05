from types import SimpleNamespace as L

from app.services.template_render import person_name, render_for_lead

AR = "السلام عليكم يا هندسة{{greet_ar}}،"
EN = "Dear {{greet_en}},"


def lead(name, company=None):
    return L(name=name, company=company, industry=None, city=None)


def test_person_name_greeting_ar_and_en():
    l = lead("محمد حامد", "شركة النور")
    assert render_for_lead(AR, l) == "السلام عليكم يا هندسة محمد حامد،"
    assert render_for_lead(EN, lead("Ahmed Hosny", "ABB")) == "Dear Eng. Ahmed Hosny,"


def test_company_in_name_column_gets_neutral_greeting():
    # The sheet often stores the company in the Name column.
    assert render_for_lead(AR, lead("Delta Plast", "Delta Plast")) == "السلام عليكم يا هندسة،"
    assert render_for_lead(EN, lead("Delta Plast", "Delta Plast Co")) == "Dear Engineer,"
    assert person_name(lead("شركة الأمل للتجارة", None)) == ""


def test_existing_titles_are_not_doubled():
    assert person_name(lead("م فاطمة زايد", "X")) == "فاطمة زايد"
    assert person_name(lead("م/ أحمد علي", "X")) == "أحمد علي"
    assert person_name(lead("Eng. Ahmed Ali", "X")) == "Ahmed Ali"
    assert render_for_lead(EN, lead("eng mohamed salah", "X")) == "Dear Eng. Mohamed Salah,"


def test_missing_name_degrades_cleanly():
    assert render_for_lead(AR, lead(None)) == "السلام عليكم يا هندسة،"
    assert render_for_lead(EN, lead("")) == "Dear Engineer,"


def test_legacy_placeholders_unchanged():
    assert render_for_lead("{{name}} @ {{company}}", lead("Ali", "ABB")) == "Ali @ ABB"
