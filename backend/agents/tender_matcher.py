"""TenderMatcher — Assess tender match using OR reasoning."""
import json
from agents.base_agent import BaseAgent


class TenderMatcher(BaseAgent):
    name = "tender_matcher"

    async def match_tender(self, tender: dict, tenant_profile: dict) -> dict:
        """
        Assess tender match using OR reasoning.
        Returns: {match_score, bid_notes, requirements_gap}
        """
        system = """You are a tender evaluation expert for Egyptian government and private tenders.
Assess how well the company profile matches the tender requirements.
Return ONLY valid JSON:
{
  "match_score": 0-100,
  "bid_notes": "key points to address in the bid",
  "requirements_gap": "what the company is missing or needs to clarify"
}"""

        prompt = f"Tender:\n{json.dumps(tender, ensure_ascii=False)}\n\nCompany Profile:\n{json.dumps(tenant_profile, ensure_ascii=False)}"
        result = await self._or_reason(
            [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            max_tokens=600,
        )
        return self._parse_json(result, {
            "match_score": 0,
            "bid_notes": "Unable to evaluate — manual review required",
            "requirements_gap": "Unknown",
        })

    run = match_tender
