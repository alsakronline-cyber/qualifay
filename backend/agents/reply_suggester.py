"""ReplySuggester — Generate 3 quick reply suggestions using Groq."""
from agents.base_agent import BaseAgent


class ReplySuggester(BaseAgent):
    name = "reply_suggester"

    async def suggest_replies(self, message: str, history: list) -> list:
        """
        Generate 3 quick reply suggestions using Groq.
        Returns list of 3 reply strings.
        """
        history_text = "\n".join([
            f"{'Customer' if m.get('direction') == 'inbound' else 'Agent'}: {m.get('content', '')}"
            for m in history[-5:]
        ])
        system = """You are a B2B sales assistant. Suggest 3 short, natural reply options for the sales agent.
The replies should vary in tone: one professional, one warm, one asking a qualifying question.
Return ONLY a JSON array of exactly 3 strings: ["reply1", "reply2", "reply3"]
Match the language of the customer (Arabic or English)."""

        prompt = f"Recent history:\n{history_text}\n\nCustomer's latest message: {message}"
        result = await self._groq(
            [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            max_tokens=300,
        )
        parsed = self._parse_json(result, [])
        if isinstance(parsed, list) and len(parsed) >= 1:
            return parsed[:3]
        return [
            "شكراً لتواصلك معنا. سنرد عليك في أقرب وقت.",
            "يسعدنا مساعدتك. هل يمكنك إخبارنا بمزيد من التفاصيل؟",
            "ما هو الموعد المناسب لك للحديث مع أحد مستشارينا؟",
        ]


    # ─── AI Setup Consultant ──────────────────────────────────

    run = suggest_replies
