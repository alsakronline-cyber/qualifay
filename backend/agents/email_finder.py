"""EmailFinder — Suggest likely email patterns for a company using OR fast."""
from agents.base_agent import BaseAgent


class EmailFinder(BaseAgent):
    name = "email_finder"

    async def find_email_patterns(self, company: str, domain: str) -> list:
        """
        Suggest likely email patterns for a company using OR fast.
        Returns list of pattern strings.
        """
        system = """You are a B2B email intelligence specialist.
Given a company name and domain, suggest the 3 most likely email address formats used at that company.
Return ONLY a valid JSON array of 3 strings:
["firstname.lastname@domain.com", "f.lastname@domain.com", "firstname@domain.com"]
Base your suggestions on the company's size, region (Egypt), and industry norms."""

        prompt = f"Company: {company}\nDomain: {domain}"
        result = await self._or_fast(
            [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            max_tokens=150,
        )
        parsed = self._parse_json(result, [])
        if isinstance(parsed, list) and parsed:
            return parsed[:3]
        return [
            f"firstname.lastname@{domain}",
            f"f.lastname@{domain}",
            f"info@{domain}",
        ]

    run = find_email_patterns
