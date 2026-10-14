"""QualityGate — Quality gate using OR fast model. Filters out junk/spam leads."""
import json
from agents.base_agent import BaseAgent


class QualityGate(BaseAgent):
    name = "quality_gate"

    async def quality_gate(self, lead_data: dict, seller: str = "") -> dict:
        """
        Quality gate using OR fast model. Filters out junk/spam leads.
        Returns: {keep: bool, reason: str, quality_score: int}
        `seller` (the tenant's brief) sets the relevant markets; without it, Egypt is assumed.
        """
        system = """You are a B2B lead quality gate for a sales CRM.
Evaluate if this lead is worth processing (real business, reachable, relevant).
Return ONLY valid JSON:
{
  "keep": true|false,
  "reason": "short explanation",
  "quality_score": 0-100
}
Reject if: no company name AND no phone or email, obviously fake data, personal (not business), competitor, or duplicate signals."""
        if seller:
            system += ("\nJudge relevance against THIS seller's markets and customers (do not assume Egypt;"
                       " a lead in the seller's target regions is relevant):\n" + seller)

        prompt = f"Lead data:\n{json.dumps(lead_data, ensure_ascii=False, indent=2)}"
        result = await self._or_fast(
            [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            max_tokens=200,
        )
        return self._parse_json(result, {"keep": True, "reason": "Quality gate error — defaulting to keep", "quality_score": 50})

    run = quality_gate
