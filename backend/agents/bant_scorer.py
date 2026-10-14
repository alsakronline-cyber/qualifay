"""BANTScorer — BANT scoring using OR reasoning model."""
import json
from agents.base_agent import BaseAgent


class BANTScorer(BaseAgent):
    name = "bant_scorer"

    async def score_bant(self, lead_data: dict, messages: list = [], seller: str = "") -> dict:
        """
        BANT scoring using OR reasoning model.
        Returns: {score, budget, authority, need, timeline, reason}
        `seller` is the tenant's business brief: when given, the score measures fit with
        what THIS seller sells and who they sell to, not generic lead quality.
        """
        system = """You are a B2B BANT (Budget, Authority, Need, Timeline) scoring expert for the Egyptian market.
Analyze the lead data and any conversation messages to produce a BANT score.
Return ONLY valid JSON:
{
  "score": 0-100,
  "budget": "confirmed|likely|unclear|unlikely",
  "authority": "decision_maker|influencer|end_user|unknown",
  "need": "urgent|moderate|low|none",
  "timeline": "immediate|1_3_months|3_6_months|6_plus_months|unknown",
  "reason": "2-3 sentence explanation of score"
}
Scoring guide: budget(25pts) + authority(25pts) + need(30pts) + timeline(20pts) = 100"""
        if seller:
            system += (
                "\n\nScore FIT with this seller, not generic quality. NEED means how much this lead"
                " plausibly needs what the seller sells. A lead outside the seller's ideal customer"
                " must score below 40 however big it is. For a cold prospect with no conversation yet,"
                " budget, decision-maker and timing are normally unknown — do NOT penalise that; score"
                " mainly on fit: strong fit 65-90, partial fit 45-64, poor fit under 40. In `reason`,"
                f" say in one sentence why it does or does not fit.\n\nSELLER:\n{seller}"
            )

        history_text = "\n".join([
            f"{'Customer' if m.get('direction') == 'inbound' else 'Agent'}: {m.get('content', '')}"
            for m in messages[-15:]
        ])
        prompt = f"Lead:\n{json.dumps(lead_data, ensure_ascii=False)}"
        if history_text:
            prompt += f"\n\nConversation:\n{history_text}"

        result = await self._or_reason(
            [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            max_tokens=512,
        )
        return self._parse_json(result, {
            "score": 0,
            "budget": "unknown",
            "authority": "unknown",
            "need": "none",
            "timeline": "unknown",
            "reason": "Scoring failed — manual review required",
            "scoring_failed": True,
        })

    run = score_bant
