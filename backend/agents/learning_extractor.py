"""LearningExtractor — From a won/lost lead + its conversation, distill ONE concise, reusable lesson."""
import json
from agents.base_agent import BaseAgent


class LearningExtractor(BaseAgent):
    name = "learning_extractor"

    async def extract_learning(self, lead: dict, outcome: str, history: list) -> dict:
        """From a won/lost lead + its conversation, distill ONE concise, reusable lesson
        the agents can apply to future leads. Returns {kind, content} or {} if nothing useful."""
        convo = "\n".join([
            f"{'Customer' if m.get('direction') == 'inbound' else 'Us'}: {m.get('content','')}"
            for m in history[-15:]
        ])
        system = """You distill sales lessons for an Egyptian B2B business. From one closed
lead and its WhatsApp conversation, extract ONE short, reusable lesson for future outreach.
Return ONLY valid JSON:
{"kind": "win_reason|loss_reason|objection|insight", "content": "one concise actionable sentence in Arabic"}
If there is no useful lesson, return {"kind":"none","content":""}."""
        prompt = f"Outcome: {outcome}\nLead: {json.dumps(lead, ensure_ascii=False)}\nConversation:\n{convo or '(none)'}"
        result = await self._or_fast(
            [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            max_tokens=200,
        )
        out = self._parse_json(result, {})
        if not isinstance(out, dict) or out.get("kind") in (None, "none", "") or not out.get("content"):
            return {}
        return out

    run = extract_learning
