"""QueryExpander — Turn a broad industry + region into concrete search queries a maps/directory scraper."""
from agents.base_agent import BaseAgent


class QueryExpander(BaseAgent):
    name = "query_expander"

    async def expand_search_queries(self, industry: str, cities: str, n: int = 8) -> list:
        """Turn a broad industry + region into concrete search queries a maps/directory scraper
        can actually use. A query like "e-commerce, industrial automation" over "Middle East"
        finds almost nothing; "industrial automation suppliers in Cairo" finds real businesses.
        Each query names ONE narrow niche and ONE specific city. Returns [] on failure."""
        system = (
            "You expand a company's broad B2B target into concrete lead-search queries for "
            "scrapers (Google Maps / business directories) in Egypt and the Middle East. Split a "
            "broad industry into specific sub-niches, and a broad region into specific CITIES. "
            "Every query must name ONE niche and ONE city, e.g. \"restaurants in Cairo\" or "
            "\"industrial automation suppliers in Riyadh\". Prefer Egyptian cities when the region "
            "is Egypt or unspecified. Return ONLY JSON: {\"queries\": [\"...\"]}"
        )
        prompt = f"Industry/offering: {industry}\nRegion/cities: {cities or 'Egypt'}\nProduce {n} queries."
        result = await self._or_fast(
            [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            max_tokens=400,
        )
        data = self._parse_json(result, {"queries": []})
        qs = data.get("queries") if isinstance(data, dict) else None
        return [str(q).strip() for q in (qs or []) if str(q).strip()][:n]

    run = expand_search_queries
