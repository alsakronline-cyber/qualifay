"""WhatsAppResponder — Generate a WhatsApp reply using Groq."""
from typing import Optional
from agents.base_agent import BaseAgent
from agents.base_agent import _lang_instruction


class WhatsAppResponder(BaseAgent):
    name = "whatsapp_responder"

    async def generate_wa_reply(
        self,
        message: str,
        contact_name: str,
        history: list,
        language: str = "auto",
        tenant_context: str = "",
    ) -> Optional[str]:
        """
        Generate a WhatsApp reply using Groq.
        Returns reply string or None if should not reply.
        """
        history_text = "\n".join([
            f"{'Customer' if m.get('direction') == 'inbound' else 'Agent'}: {m.get('content', '')}"
            for m in history[-10:]
        ])

        lang_instruction = "Respond in the same language as the customer." if language == "auto" else _lang_instruction(language)

        brand = f"\nYou represent this business — stay on-brand and specific to it:\n{tenant_context}\n" if tenant_context else ""
        system = f"""You are a professional B2B sales assistant for an Egyptian company.
{brand}{lang_instruction}
Rules:
- Be concise, warm, and professional (max 3 sentences)
- Never claim to be AI unless directly asked
- If booking/demo requested: confirm interest and say a human will follow up shortly
- If complaint: acknowledge, apologize briefly, escalate to human
- Return ONLY the reply text, no labels or quotes"""

        messages = [{"role": "system", "content": system}]
        if history_text:
            messages.append({"role": "user", "content": f"Conversation so far:\n{history_text}"})
            messages.append({"role": "assistant", "content": "Understood."})
        messages.append({"role": "user", "content": f"{contact_name}: {message}"})

        reply = await self._groq(messages, max_tokens=300)
        return reply if reply else None

    run = generate_wa_reply
