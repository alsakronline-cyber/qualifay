"""Render a template body/subject against a lead's fields ({{name}} etc.)."""
import re


def render_for_lead(text: str, lead) -> str:
    data = {
        "name": lead.name or "",
        "company": lead.company or "",
        "industry": lead.industry or "",
        "city": lead.city or "",
    }
    return re.sub(r"\{\{(\w+)\}\}", lambda m: data.get(m.group(1), ""), text or "")
