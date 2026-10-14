"""AIDAWriter — Write an AIDA-format outreach message using OR fast, in the tenant's chosen output."""
import logging
import json
from agents.base_agent import BaseAgent
from agents.base_agent import _lang_instruction


logger = logging.getLogger(__name__)


class AIDAWriter(BaseAgent):
    name = "aida_writer"

    async def write_aida_message(self, lead: dict, context: str = "", language: str = "ar") -> str:
        """
        Write an AIDA-format outreach message using OR fast, in the tenant's chosen output
        language (ar = فصحى | en = English | masri = عامية مصرية).
        Returns outreach message string (max 3 sentences).
        """
        system = f"""You are a B2B copywriter specializing in WhatsApp outreach for Egyptian businesses.
Write a short, personalised outreach message using the AIDA framework (Attention, Interest, Desire, Action).
Rules:
- {_lang_instruction(language)}
- Maximum 3 sentences
- No emojis unless the brand context suggests it
- Sound human, not robotic
- Include a soft CTA (e.g., a question, not a hard sell)
- Return ONLY the message text, no labels"""

        prompt = f"""Lead info: {json.dumps(lead, ensure_ascii=False)}
{f'Additional context: {context}' if context else ''}
Write the outreach message:"""

        # Arabic needs far more tokens per word than English; 200 truncated real messages
        # mid-sentence, which then went out to customers looking broken.
        result = await self._or_fast(
            [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            max_tokens=600,
        )
        result = (result or "").strip()
        # Never ship a half-finished sentence: if the model was still cut off, fall back to
        # the safe canned line rather than sending a fragment.
        if result and not result.rstrip().endswith((".", "؟", "!", "?", "،", "。", ":", "»")):
            logger.warning("AIDA output looks truncated; using safe fallback")
            result = ""
        return result or "مرحباً، كنا نود مشاركتك فرصة قد تناسب عملكم. هل لديكم دقيقة للحديث؟"

    run = write_aida_message
