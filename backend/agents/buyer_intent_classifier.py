"""BuyerIntentClassifier — Confirm whether a social/group post is a genuine buying request and extract what."""
from agents.base_agent import BaseAgent


class BuyerIntentClassifier(BaseAgent):
    name = "buyer_intent_classifier"

    async def classify_buyer_intent(self, post_text: str) -> dict:
        """Confirm whether a social/group post is a genuine buying request and extract what
        the person wants. One Groq call. Returns:
        {is_buyer, wants, budget, urgency, score, reason}."""
        system = (
            "You analyze Facebook group posts (Egyptian Arabic or English) to find people "
            "who want to BUY or are ASKING for a product/service. Ignore sellers, ads, "
            "greetings, and spam.\nReturn ONLY valid JSON:\n"
            '{"is_buyer": true/false, "wants": "short desc of what they want", '
            '"budget": "stated budget or null", "urgency": "high|medium|low", '
            '"score": 0-100, "reason": "one short sentence"}'
        )
        result = await self._groq(
            [{"role": "system", "content": system},
             {"role": "user", "content": post_text[:1500]}],
            max_tokens=200,
        )
        return self._parse_json(result, {
            "is_buyer": False, "wants": None, "budget": None,
            "urgency": "low", "score": 0, "reason": "Analysis unavailable",
        })

    run = classify_buyer_intent
