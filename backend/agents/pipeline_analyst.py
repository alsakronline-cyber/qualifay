"""PipelineAnalyst — Read a WhatsApp conversation and decide whether it's a real sales lead and, if."""
from agents.base_agent import BaseAgent


class PipelineAnalyst(BaseAgent):
    name = "pipeline_analyst"

    async def analyze_conversation_for_pipeline(self, messages: list, contact_name: str = "") -> dict:
        """Read a WhatsApp conversation and decide whether it's a real sales lead and, if
        so, which CRM pipeline stage it belongs in. One Groq call (fast, reliable).
        Returns: {is_lead, intent, score, stage, reason}."""
        convo = "\n".join(
            f"{'Customer' if m.get('direction') == 'inbound' else 'Us'}: {m.get('content','')}"
            for m in messages[-20:] if m.get('content')
        )
        system = (
            "You analyze a WhatsApp sales conversation for an Egyptian B2B company. "
            "Decide if the OTHER party is a genuine sales lead (interest, product/pricing "
            "questions, availability, booking) vs spam/wrong-number/no-intent chatter.\n"
            "Return ONLY valid JSON:\n"
            '{"is_lead": true/false, "intent": "pricing|product_info|booking|complaint|greeting|spam|other", '
            '"score": 0-100, "stage": "replied|qualifying|meeting|proposal|negotiation|won|lost", '
            '"reason": "one short sentence"}\n'
            "Stage guidance: general reply/interest=replied; qualifying questions=qualifying; "
            "asked for/agreed a meeting=meeting; asked for a formal offer=proposal; "
            "haggling on price/terms=negotiation; confirmed purchase=won; explicitly declined=lost."
        )
        prompt = f"Contact: {contact_name}\nConversation:\n{convo}"
        result = await self._groq(
            [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            max_tokens=300,
        )
        return self._parse_json(result, {
            "is_lead": False, "intent": "other", "score": 0,
            "stage": "replied", "reason": "Analysis unavailable",
        })

    run = analyze_conversation_for_pipeline
