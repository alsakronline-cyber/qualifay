"""MessageSupervisor — Critic gate before an autonomous send: check a drafted message against brand +."""
from agents.base_agent import BaseAgent


class MessageSupervisor(BaseAgent):
    name = "message_supervisor"

    async def supervise_message(self, text: str, tenant_context: str = "", first_contact: bool = False) -> dict:
        """Critic gate before an autonomous send: check a drafted message against brand +
        compliance + anti-ban rules. Returns {ok, reason, revised}. `revised` is a safe
        rewrite when the issue is fixable, else None. Keeps full-autopilot sends safe."""
        rules = (
            "- No links/URLs in a first-contact message (anti-ban).\n"
            "- No price or hard sell in a first message.\n"
            "- On-brand, professional tone; matches the business.\n"
            "- No invented facts, guarantees, or claims the business didn't state.\n"
            "- Not spammy, not more than a few sentences."
        )
        system = f"""You are a compliance + brand supervisor for outbound B2B WhatsApp/email in Egypt.
Business context:
{tenant_context or '(none provided)'}

Check the DRAFT message against these rules{' (this is a FIRST-contact message)' if first_contact else ''}:
{rules}
Return ONLY valid JSON:
{{"ok": true|false, "reason": "short reason", "revised": "a corrected safe version, or null if already fine or unfixable"}}"""
        result = await self._groq(
            [{"role": "system", "content": system}, {"role": "user", "content": f"DRAFT:\n{text}"}],
            max_tokens=400,
        )
        out = self._parse_json(result, {"ok": True, "reason": "", "revised": None})
        # Fail OPEN on a broken critic response (don't block real sends over a parse blip),
        # but honour an explicit block.
        if not isinstance(out, dict) or "ok" not in out:
            return {"ok": True, "reason": "supervisor-unavailable", "revised": None}
        return out

    run = supervise_message
