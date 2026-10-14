"""IntentClassifier — Fast intent classification using Groq."""
from agents.base_agent import BaseAgent


class IntentClassifier(BaseAgent):
    name = "intent_classifier"

    async def classify_intent(self, message: str, contact_name: str = "") -> dict:
        """
        Fast intent classification using Groq.
        Returns: {intent, confidence, language, sentiment, requires_human, summary}
        """
        system = """You are a WhatsApp B2B lead intent classifier for an Egyptian sales CRM.
Analyze the message and return ONLY valid JSON with these exact fields:
{
  "intent": "greeting|question|purchase_intent|complaint|followup|booking|objection|unsubscribe|spam|farewell|other",
  "confidence": 0.0-1.0,
  "language": "ar|en|fr|auto",
  "sentiment": "positive|neutral|negative",
  "requires_human": true|false,
  "summary": "one sentence summary in English"
}
Rules:
- requires_human = true if: complaint, complex technical question, angry, or booking with specific dates
- Arabic messages with Arabic intent should still return fields in English
- Return ONLY the JSON object, no explanation"""

        prompt = f"Contact: {contact_name or 'Unknown'}\nMessage: {message}"
        result = await self._groq(
            [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            max_tokens=256,
        )
        return self._parse_json(result, {
            "intent": "other",
            "confidence": 0.5,
            "language": "auto",
            "sentiment": "neutral",
            "requires_human": True,
            "summary": message[:100],
        })

    run = classify_intent
