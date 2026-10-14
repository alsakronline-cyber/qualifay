"""ArabicTranslator — Translate text using OR fast."""
from agents.base_agent import BaseAgent


class ArabicTranslator(BaseAgent):
    name = "arabic_translator"

    async def translate_arabic(self, text: str, direction: str = "en_to_ar") -> str:
        """
        Translate text using OR fast.
        direction: 'en_to_ar' or 'ar_to_en'
        Returns translated string.
        """
        if direction == "en_to_ar":
            system = "Translate the following text to formal Egyptian business Arabic (فصحى مبسطة). Return ONLY the translation."
        else:
            system = "Translate the following Arabic text to professional English. Return ONLY the translation."

        result = await self._or_fast(
            [{"role": "system", "content": system}, {"role": "user", "content": text}],
            max_tokens=500,
        )
        return result or text

    run = translate_arabic
