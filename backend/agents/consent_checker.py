"""ConsentChecker — Check GDPR/PDPA consent compliance using OR fast."""
import json
from agents.base_agent import BaseAgent


class ConsentChecker(BaseAgent):
    name = "consent_checker"

    async def check_consent_compliance(self, lead: dict, method: str) -> dict:
        """
        Check GDPR/PDPA consent compliance using OR fast.
        Returns: {compliant: bool, reason: str, action_needed: str}
        """
        system = """You are a data privacy compliance officer specializing in Egyptian and international regulations (PDPA Egypt 151/2020, GDPR principles).
Evaluate if the lead acquisition method and consent data comply with applicable regulations.
Return ONLY valid JSON:
{
  "compliant": true|false,
  "reason": "explanation referencing specific compliance requirements",
  "action_needed": "what must be done before contacting this lead, or 'none' if compliant"
}"""

        prompt = f"Lead data: {json.dumps(lead, ensure_ascii=False)}\nConsent method: {method}"
        result = await self._or_fast(
            [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            max_tokens=250,
        )
        return self._parse_json(result, {
            "compliant": False,
            "reason": "Compliance check failed — defaulting to non-compliant for safety",
            "action_needed": "Manual compliance review required before contacting",
        })

    run = check_consent_compliance
