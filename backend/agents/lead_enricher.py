"""LeadEnricher — Enrich/normalize lead data using OR fast."""
import json
from agents.base_agent import BaseAgent


class LeadEnricher(BaseAgent):
    name = "lead_enricher"

    async def enrich_lead(self, raw_data: dict) -> dict:
        """
        Enrich/normalize lead data using OR fast.
        Returns: {company, industry, company_size, city, website, email_pattern, language}
        """
        system = """You are a B2B data enrichment specialist for the Egyptian market.
Given raw lead data, extract and normalize structured fields.
Return ONLY valid JSON:
{
  "company": "cleaned company name or null",
  "industry": "one of: tech|retail|manufacturing|construction|healthcare|education|finance|hospitality|logistics|real_estate|other",
  "company_size": "one of: 1-10|11-50|51-200|201-1000|1000+|unknown",
  "city": "Egyptian city name in English or null",
  "governorate": "Egyptian governorate in English or null",
  "website": "clean URL or null",
  "email_pattern": "e.g. firstname.lastname@company.com or null",
  "language": "ar|en|mixed"
}
If a field cannot be determined, use null. Do NOT invent data."""

        prompt = f"Raw lead data:\n{json.dumps(raw_data, ensure_ascii=False, indent=2)}"
        result = await self._or_fast(
            [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            max_tokens=300,
        )
        return self._parse_json(result, {
            "company": raw_data.get("company"),
            "industry": "other",
            "company_size": "unknown",
            "city": None,
            "governorate": None,
            "website": None,
            "email_pattern": None,
            "language": "ar",
        })

    run = enrich_lead
