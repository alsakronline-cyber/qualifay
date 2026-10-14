"""FollowUpScheduler — Suggest optimal follow-up timing using OR fast."""
import json
from agents.base_agent import BaseAgent


class FollowUpScheduler(BaseAgent):
    name = "followup_scheduler"

    async def schedule_followup(self, lead: dict, history: list) -> dict:
        """
        Suggest optimal follow-up timing using OR fast.
        Returns: {days_wait, message, reason}
        """
        system = """You are a B2B sales timing expert for the Egyptian market.
Based on the lead profile and conversation history, suggest the optimal follow-up.
Return ONLY valid JSON:
{
  "days_wait": 1-30,
  "message": "suggested follow-up message (max 2 sentences)",
  "reason": "why this timing"
}"""

        history_text = "\n".join([m.get("content", "") for m in history[-10:]])
        prompt = f"Lead: {json.dumps(lead, ensure_ascii=False)}\nRecent messages: {history_text}"

        result = await self._or_fast(
            [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            max_tokens=250,
        )
        return self._parse_json(result, {
            "days_wait": 3,
            "message": "متابعة بخصوص حديثنا السابق، هل يمكننا تحديد موعد مناسب؟",
            "reason": "Standard follow-up interval",
        })

    run = schedule_followup
