"""LinkedIn discovery via Google Programmable Search (Custom Search JSON API).

LinkedIn blocks all unauthenticated scraping, so instead of hitting linkedin.com we query
Google for public LinkedIn profiles (`site:linkedin.com/in ...`) and read the name / title /
company straight out of the search results. No cookie, no blocking, ToS-safe, and free
(100 queries/day on the Custom Search free tier).
"""
import logging
import re
from typing import AsyncGenerator, Optional

import httpx

from scrapers.base import BaseScraper, RawLead, BlockedError

logger = logging.getLogger(__name__)

CSE_URL = "https://www.googleapis.com/customsearch/v1"


def parse_linkedin_title(title: str) -> tuple:
    """Split a LinkedIn search-result title into (name, role, company).

    Titles look like: "Ahmed Ali - Sales Manager - ACME Corp | LinkedIn"
    or "Ahmed Ali - Egypt | LinkedIn" (role/company may be missing).
    """
    if not title:
        return None, None, None
    # Drop the trailing " | LinkedIn" / " - LinkedIn" marker.
    head = re.split(r"\s*[|\-–]\s*LinkedIn\b", title, maxsplit=1)[0].strip()
    parts = [p.strip() for p in re.split(r"\s+[-–]\s+", head) if p.strip()]
    if not parts:
        return None, None, None
    name = parts[0]
    role = parts[1] if len(parts) > 1 else None
    company = parts[2] if len(parts) > 2 else None
    return name, role, company


class LinkedInSearchScraper(BaseScraper):
    source = "linkedin"
    delay_min = 0.5
    delay_max = 1.5

    async def scrape(self, config: dict, tenant_id: str) -> AsyncGenerator[RawLead, None]:
        from app.core.config import settings

        query = (config.get("query") or "").strip()
        location = (config.get("location") or "Egypt").strip()
        max_results = min(int(config.get("max_results", 20)), 50)
        if not query:
            raise ValueError("LinkedIn discovery requires 'query' in config")

        key = config.get("cse_key") or settings.GOOGLE_CSE_API_KEY or settings.GOOGLE_MAPS_API_KEY
        cx = config.get("cse_cx") or settings.GOOGLE_CSE_CX
        if not key or not cx:
            raise BlockedError(
                "LinkedIn discovery needs Google Programmable Search. Add GOOGLE_CSE_API_KEY "
                "and GOOGLE_CSE_CX (free 100 searches/day) to enable this source."
            )

        q = f"site:linkedin.com/in {query} {location}".strip()
        count, start = 0, 1
        seen: set = set()

        async with httpx.AsyncClient(timeout=30) as client:
            # CSE returns 10 results/page and allows start up to 91 (100 results total).
            while count < max_results and start <= 91:
                params = {"key": key, "cx": cx, "q": q, "num": 10, "start": start}
                try:
                    r = await client.get(CSE_URL, params=params)
                except httpx.RequestError as e:
                    raise BlockedError(f"Google CSE unreachable: {e}")

                if r.status_code == 429:
                    raise BlockedError("Google CSE daily quota exceeded (100/day free).")
                if r.status_code != 200:
                    raise BlockedError(f"Google CSE HTTP {r.status_code}: {r.text[:120]}")

                items = r.json().get("items", [])
                if not items:
                    break

                for it in items:
                    if count >= max_results:
                        break
                    link = it.get("link", "")
                    if "/in/" not in link or link in seen:
                        continue
                    seen.add(link)
                    name, role, company = parse_linkedin_title(it.get("title", ""))
                    if not name:
                        continue
                    yield RawLead(
                        source=self.source,
                        name=name,
                        company=company,
                        industry=role or query,
                        city=location,
                        linkedin_url=link.split("?")[0],
                        raw_data={"role": role, "snippet": it.get("snippet"), "via": "google_cse"},
                    )
                    count += 1

                await self.delay()
                start += 10
