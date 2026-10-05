"""Render a template body/subject against a lead's fields ({{name}} etc.)."""
import re

_NORM = re.compile(r"[^0-9a-z؀-ۿ]+")
# Words that mark a "name" as really being an organisation, not a person.
_ORG_WORDS = (
    "company", "co.", "group", "factory", "industries", "industrial", "trading", "plast",
    "egypt", "s.a.e", "ltd", "llc", "inc", "corp", "engineering", "systems", "electric",
    "شركة", "مصنع", "مجموعة", "للصناعات", "للتجارة", "مؤسسة", "الهندسية", "مصر",
)


# Titles people already typed into the name field ("م/ أحمد", "Eng. Ahmed"). The greeting
# adds its own title, so leaving these in would render "يا هندسة م أحمد" / "Eng. Eng. Ahmed".
_TITLE = re.compile(
    r"^\s*(?:(?:eng|engr|dr|mr|mrs|ms)\.?\s+|م\s*[/.]\s*|م\s+|مهندس[ةه]?\s+|د\s*[/.]\s*|أ\s*[/.]\s*)",
    re.IGNORECASE)


def _norm(s: str) -> str:
    return _NORM.sub("", (s or "").lower())


def _clean_name(name: str) -> str:
    prev = None
    while prev != name:                      # handles stacked titles like "Eng. م/ أحمد"
        prev, name = name, _TITLE.sub("", name).strip()
    if name and name.isascii() and name == name.lower():
        name = name.title()                  # "mohamed ali" -> "Mohamed Ali"
    return name


def person_name(lead) -> str:
    """The lead's name only if it plausibly belongs to a PERSON.

    Imported sheets often put the company in the Name column, which would render greetings
    like "Dear Eng. Delta Plast". Return "" when the name equals/overlaps the company or
    contains organisation words, so templates can fall back to a neutral greeting.
    """
    name = _clean_name((lead.name or "").strip())
    if not name:
        return ""
    n, c = _norm(name), _norm(lead.company or "")
    if c and (n in c or c in n):
        return ""
    low = name.lower()
    if any(w in low for w in _ORG_WORDS):
        return ""
    return name


def render_for_lead(text: str, lead) -> str:
    pn = person_name(lead)
    data = {
        "name": lead.name or "",
        "company": lead.company or "",
        "industry": lead.industry or "",
        "city": lead.city or "",
        # Greeting helpers that degrade gracefully when there's no real person name:
        #   AR: "يا هندسة{{greet_ar}}،"  -> "يا هندسة أحمد،" / "يا هندسة،"
        #   EN: "Dear {{greet_en}},"     -> "Dear Eng. Ahmed," / "Dear Engineer,"
        "greet_ar": f" {pn}" if pn else "",
        "greet_en": f"Eng. {pn}" if pn else "Engineer",
    }
    return re.sub(r"\{\{(\w+)\}\}", lambda m: data.get(m.group(1), ""), text or "")
