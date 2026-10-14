"""CompetitorAnalyst — Analyze a competitor ad using OR reasoning."""
import json
from agents.base_agent import BaseAgent


class CompetitorAnalyst(BaseAgent):
    name = "competitor_analyst"

    async def analyze_competitor_ad(self, ad_data: dict) -> dict:
        """
        Analyze a competitor ad using OR reasoning.
        Returns: {insights, counter_strategy, opportunity}
        """
        system = """You are a competitive intelligence analyst specializing in the Egyptian B2B market.
Analyze the competitor ad/content and provide strategic insights.
Return ONLY valid JSON:
{
  "insights": "key observations about their positioning and messaging",
  "counter_strategy": "how to differentiate and counter their approach",
  "opportunity": "market gap or weakness we can exploit"
}"""

        prompt = f"Competitor ad data:\n{json.dumps(ad_data, ensure_ascii=False, indent=2)}"
        result = await self._or_reason(
            [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            max_tokens=600,
        )
        return self._parse_json(result, {
            "insights": "Analysis failed",
            "counter_strategy": "Manual review required",
            "opportunity": "Unknown",
        })

    run = analyze_competitor_ad
