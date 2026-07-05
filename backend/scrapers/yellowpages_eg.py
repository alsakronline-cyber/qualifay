"""Yellow Pages Egypt scraper (yellowpages.com.eg) — httpx, no browser needed.

The site is server-rendered: the search page lists company names + profile URLs +
addresses, and each profile page exposes the phone number(s) in the HTML. So we scrape
it with plain HTTP (fast, no Playwright, no Tor) and fall back to graceful block handling
if the site starts challenging us.
"""
import asyncio
import logging
import re
from typing import AsyncGenerator, Optional
from urllib.parse import quote

import httpx

from scrapers.base import BaseScraper, RawLead, BlockedError
from app.lib.phone import normalize_egyptian_phone

logger = logging.getLogger(__name__)

BASE = "https://www.yellowpages.com.eg"

# Egyptian phone patterns as they appear on profile pages (e.g. +201026095252, 0223… )
PHONE_RE = re.compile(r"(?:\+?20)?0?1[0125][0-9]{8}|0[23][0-9]{6,8}")
# item-title anchors carry the company name + profile link.
TITLE_RE = re.compile(r'class="item-title"[^>]*?href="([^"]+)"[^>]*>(.*?)</a>', re.S)


class YellowPagesEgyptScraper(BaseScraper):
    source = "yellowpages"
    use_tor = False  # site is reachable directly; Tor SOCKS breaks the TLS handshake here
    delay_min = 1.5
    delay_max = 3.5

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
    }

    async def scrape(self, config: dict, tenant_id: str) -> AsyncGenerator[RawLead, None]:
        query = (config.get("query") or config.get("industry") or "").strip()
        location = (config.get("location") or "").strip()
        max_results = min(int(config.get("max_results", 20)), 100)
        if not query:
            raise ValueError("Yellow Pages scraper requires a query/industry")

        term = f"{query} {location}".strip()
        search_url = f"{BASE}/en/search/{quote(term)}"

        async with httpx.AsyncClient(timeout=30, headers=self.HEADERS, follow_redirects=True) as client:
            try:
                r = await client.get(search_url)
            except httpx.RequestError as e:
                raise BlockedError(f"Yellow Pages unreachable: {e}")

            if self.is_blocked(r.status_code, r.text):
                raise BlockedError(f"Yellow Pages blocked: HTTP {r.status_code}")
            if r.status_code != 200:
                raise BlockedError(f"Yellow Pages HTTP {r.status_code}")

            html = r.text
            # Extract (profile_url, name) pairs, deduped and in order.
            seen_urls = set()
            companies = []
            for href, raw_name in TITLE_RE.findall(html):
                name = re.sub(r"<[^>]+>", "", raw_name)
                name = re.sub(r"\s+", " ", name).strip()
                url = href.strip()
                if url.startswith("//"):
                    url = "https:" + url
                elif url.startswith("/"):
                    url = BASE + url
                if not name or url in seen_urls:
                    continue
                seen_urls.add(url)
                companies.append((url, name))
                if len(companies) >= max_results:
                    break

            if not companies:
                logger.warning("Yellow Pages: no companies parsed (markup change or empty result)")
                return

            for profile_url, name in companies:
                await self.delay()
                phone = None
                website = None
                city = location or None
                try:
                    pr = await client.get(profile_url)
                    if pr.status_code == 200:
                        ph = pr.text
                        m = PHONE_RE.search(ph)
                        if m:
                            phone = normalize_egyptian_phone(m.group(0))
                        # External website (first non-yellowpages http link in the contact area)
                        wm = re.search(
                            r'href="(https?://(?!(?:www\.)?yellowpages\.com\.eg)[^"]+)"',
                            ph,
                        )
                        if wm:
                            website = wm.group(1)
                        # City from address if not provided
                        cm = re.search(r'governorate[^>]*>\s*([^<]+)<', ph, re.I)
                        if cm and not city:
                            city = cm.group(1).strip()
                except httpx.RequestError:
                    pass

                if not phone and not website:
                    continue  # skip un-contactable listings

                yield RawLead(
                    source=self.source,
                    name=name,
                    phone=phone,
                    company=name,
                    industry=query,
                    city=city,
                    website=website,
                    raw_data={"profile_url": profile_url, "directory": "yellowpages.com.eg"},
                )
