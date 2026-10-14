"""CampaignPlanner — Plan a multi-step outreach campaign using OR reasoning."""
import json
from agents.base_agent import BaseAgent


class CampaignPlanner(BaseAgent):
    name = "campaign_planner"

    async def plan_campaign(self, leads: list, goal: str) -> dict:
        """
        Plan a multi-step outreach campaign using OR reasoning.
        Returns: {sequence: [{day, message, channel}], total_days}
        """
        system = """You are a B2B outreach campaign strategist for Egyptian market.
Design a multi-touch outreach sequence for the given leads and goal.
Return ONLY valid JSON:
{
  "sequence": [
    {"day": 1, "message": "message text", "channel": "whatsapp|email"},
    ...
  ],
  "total_days": number
}
Rules: max 5 touchpoints, vary channels if possible, respect Egyptian business culture (no Friday messages)"""

        lead_summary = [{"company": l.get("company"), "industry": l.get("industry"), "stage": l.get("stage")} for l in leads[:10]]
        prompt = f"Goal: {goal}\nLead sample: {json.dumps(lead_summary, ensure_ascii=False)}"

        result = await self._or_reason(
            [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            max_tokens=800,
        )
        return self._parse_json(result, {
            "sequence": [
                {"day": 1, "message": "Initial outreach message", "channel": "whatsapp"},
                {"day": 4, "message": "Follow-up message", "channel": "whatsapp"},
                {"day": 10, "message": "Final follow-up", "channel": "email"},
            ],
            "total_days": 10,
        })

    run = plan_campaign
