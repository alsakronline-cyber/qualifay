"""ProposalWriter — Write a full business proposal in Markdown using OR reasoning (DeepSeek-R1)."""
import json
from agents.base_agent import BaseAgent


class ProposalWriter(BaseAgent):
    name = "proposal_writer"

    async def write_proposal(self, lead: dict, tenant_context: str = "") -> str:
        """
        Write a full business proposal in Markdown using OR reasoning (DeepSeek-R1).
        Returns full proposal string.
        """
        system = """You are an expert B2B proposal writer for Egyptian businesses.
Write a professional business proposal in Markdown format.
Structure: Executive Summary → Problem Statement → Our Solution → Value Proposition → Pricing Options → Next Steps → About Us
Use Arabic where appropriate for an Egyptian audience. Be specific, not generic."""

        prompt = f"""Lead/Client info: {json.dumps(lead, ensure_ascii=False, indent=2)}
{f'Our company context: {tenant_context}' if tenant_context else ''}
Write the full proposal:"""

        result = await self._or_reason(
            [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            max_tokens=2000,
        )
        return result or "# Proposal\n\nError generating proposal. Please try again."

    run = write_proposal
