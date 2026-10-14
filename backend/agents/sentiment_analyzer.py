"""SentimentAnalyzer — Analyze sentiment trend from conversation history using OR fast."""
from agents.base_agent import BaseAgent


class SentimentAnalyzer(BaseAgent):
    name = "sentiment_analyzer"

    async def analyze_sentiment(self, history: list) -> dict:
        """
        Analyze sentiment trend from conversation history using OR fast.
        Returns: {sentiment, trend, score}
        """
        system = """You are a conversation sentiment analyst for B2B sales.
Analyze the conversation history and return ONLY valid JSON:
{
  "sentiment": "positive|neutral|negative",
  "trend": "improving|stable|worsening",
  "score": -1.0 to 1.0
}"""

        history_text = "\n".join([
            f"{'Customer' if m.get('direction') == 'inbound' else 'Agent'}: {m.get('content', '')}"
            for m in history[-20:]
        ])
        result = await self._or_fast(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": f"Conversation:\n{history_text}"},
            ],
            max_tokens=150,
        )
        return self._parse_json(result, {"sentiment": "neutral", "trend": "stable", "score": 0.0})

    run = analyze_sentiment
