"""Tender scraper — RSS feeds + official portals (UNGM, PPO Egypt, DG Market)"""
import asyncio
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator, Optional
from urllib.parse import urljoin, urlencode, quote_plus

import httpx
from bs4 import BeautifulSoup

from scrapers.base import BaseScraper, RawLead, BlockedError

logger = logging.getLogger(__name__)

RFC_DATE_FORMATS = [
    "%a, %d %b %Y %H:%M:%S %z",
    "%a, %d %b %Y %H:%M:%S %Z",
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%d",
]


def _parse_date(date_str: Optional[str]) -> Optional[datetime]:
    if not date_str:
        return None
    date_str = date_str.strip()
    for fmt in RFC_DATE_FORMATS:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None


def _matches_keywords(text: str, keywords: list[str]) -> bool:
    if not keywords:
        return True
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in keywords)


class TendersScraper(BaseScraper):
    source = "tender"
    delay_min = 2.0
    delay_max = 5.0

    async def scrape(self, config: dict, tenant_id: str) -> AsyncGenerator[RawLead, None]:
        """
        config keys:
          keywords: list[str]   — filter tenders by keyword (empty = all)
          country: str          — "EG" (default)
          days_back: int        — how many days back to look (default 30)
          sources: list[str]    — ["ungm", "ppo", "dgmarket"] (default all)
        """
        keywords = config.get("keywords", [])
        days_back = int(config.get("days_back", 30))
        sources = config.get("sources", ["ungm", "ppo", "dgmarket"])
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)

        if "ungm" in sources:
            async for lead in self._scrape_ungm(keywords, cutoff):
                yield lead
            await self.delay()

        if "ppo" in sources:
            async for lead in self._scrape_ppo(keywords, cutoff):
                yield lead
            await self.delay()

        if "dgmarket" in sources:
            async for lead in self._scrape_dgmarket(keywords, cutoff):
                yield lead

    # ──────────────────────────────────────────────
    # UNGM — RSS feed
    # ──────────────────────────────────────────────
    async def _scrape_ungm(
        self, keywords: list[str], cutoff: datetime
    ) -> AsyncGenerator[RawLead, None]:
        rss_url = "https://www.ungm.org/Public/Notice/SearchNotices?country=EG&status=1&format=rss"
        headers = {
            "User-Agent": self.random_ua(),
            "Accept": "application/rss+xml,application/xml,text/xml,*/*",
        }

        async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=30) as client:
            for attempt in range(self.max_retries):
                try:
                    resp = await client.get(rss_url)
                    if self.is_blocked(resp.status_code, resp.text):
                        raise BlockedError(f"UNGM blocked: HTTP {resp.status_code}")
                    break
                except httpx.TransportError as e:
                    if attempt == self.max_retries - 1:
                        raise
                    await asyncio.sleep(5)

            try:
                root = ET.fromstring(resp.text)
            except ET.ParseError as e:
                logger.error(f"UNGM RSS parse error: {e}")
                return

            ns = {"atom": "http://www.w3.org/2005/Atom"}
            channel = root.find("channel")
            items = channel.findall("item") if channel is not None else root.findall(".//item")

            for item in items:
                title = (item.findtext("title") or "").strip()
                description = (item.findtext("description") or "").strip()
                link = (item.findtext("link") or "").strip()
                pub_date_str = item.findtext("pubDate")
                pub_date = _parse_date(pub_date_str)

                if pub_date and pub_date.tzinfo and pub_date < cutoff:
                    continue

                full_text = f"{title} {description}"
                if not _matches_keywords(full_text, keywords):
                    continue

                # Extract deadline from description if present
                deadline = None
                deadline_match = re.search(
                    r"deadline[:\s]+([A-Z][a-z]+ \d+,? \d{4}|\d{4}-\d{2}-\d{2})",
                    description, re.I
                )
                if deadline_match:
                    deadline = deadline_match.group(1)

                # Extract organization from description
                org_match = re.search(r"Organization[:\s]+([^\n<]+)", description, re.I)
                organization = org_match.group(1).strip() if org_match else "UN Agency"

                yield RawLead(
                    source="tender",
                    name=title[:200],
                    company=organization,
                    raw_data={
                        "tender_source": "ungm",
                        "title": title,
                        "description": description[:1000],
                        "url": link,
                        "published_at": pub_date_str,
                        "deadline": deadline,
                        "country": "EG",
                    },
                )

    # ──────────────────────────────────────────────
    # PPO Egypt — tenders.gov.eg
    # ──────────────────────────────────────────────
    async def _scrape_ppo(
        self, keywords: list[str], cutoff: datetime
    ) -> AsyncGenerator[RawLead, None]:
        base_url = "https://www.tenders.gov.eg"
        search_url = f"{base_url}/en/Tender/TenderSearch"
        headers = {
            "User-Agent": self.random_ua(),
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer": base_url,
        }

        params = {
            "TenderTypeID": "",
            "EntityID": "",
            "TenderStatusID": "1",  # 1 = open
            "pageIndex": 1,
            "pageSize": 20,
        }
        if keywords:
            params["TenderSubject"] = keywords[0]

        async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=30) as client:
            page = 1
            while True:
                params["pageIndex"] = page
                for attempt in range(self.max_retries):
                    try:
                        resp = await client.get(search_url, params=params)
                        if self.is_blocked(resp.status_code, resp.text):
                            raise BlockedError(f"PPO Egypt blocked: HTTP {resp.status_code}")
                        break
                    except httpx.TransportError:
                        if attempt == self.max_retries - 1:
                            raise
                        await asyncio.sleep(5)

                soup = BeautifulSoup(resp.text, "html.parser")
                rows = soup.select("table.table tbody tr, .tender-row, .result-row")

                if not rows:
                    break

                found_any = False
                for row in rows:
                    cells = row.select("td")
                    if len(cells) < 3:
                        continue

                    title = _clean_text(cells[0].get_text())
                    organization = _clean_text(cells[1].get_text()) if len(cells) > 1 else None
                    deadline_str = _clean_text(cells[2].get_text()) if len(cells) > 2 else None
                    tender_type = _clean_text(cells[3].get_text()) if len(cells) > 3 else None

                    link_el = row.select_one("a[href]")
                    detail_url = urljoin(base_url, link_el["href"]) if link_el else None

                    pub_date = _parse_date(deadline_str)
                    if pub_date and pub_date.tzinfo:
                        if pub_date < cutoff:
                            continue

                    full_text = f"{title or ''} {organization or ''}"
                    if not _matches_keywords(full_text, keywords):
                        continue

                    found_any = True
                    yield RawLead(
                        source="tender",
                        name=(title or "")[:200],
                        company=organization,
                        raw_data={
                            "tender_source": "ppo_egypt",
                            "title": title,
                            "organization": organization,
                            "deadline": deadline_str,
                            "tender_type": tender_type,
                            "url": detail_url,
                            "country": "EG",
                        },
                    )

                if not found_any:
                    break

                page += 1
                await self.delay()

    # ──────────────────────────────────────────────
    # DG Market — RSS feed
    # ──────────────────────────────────────────────
    async def _scrape_dgmarket(
        self, keywords: list[str], cutoff: datetime
    ) -> AsyncGenerator[RawLead, None]:
        keyword_str = quote_plus(" ".join(keywords)) if keywords else "egypt"
        rss_url = (
            f"https://www.dgmarket.com/tenders/searchTenders.do?format=rss"
            f"&countryCode=EG&keyword={keyword_str}"
        )
        headers = {
            "User-Agent": self.random_ua(),
            "Accept": "application/rss+xml,application/xml,text/xml,*/*",
        }

        async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=30) as client:
            for attempt in range(self.max_retries):
                try:
                    resp = await client.get(rss_url)
                    if self.is_blocked(resp.status_code, resp.text):
                        raise BlockedError(f"DG Market blocked: HTTP {resp.status_code}")
                    break
                except httpx.TransportError:
                    if attempt == self.max_retries - 1:
                        raise
                    await asyncio.sleep(5)

            try:
                root = ET.fromstring(resp.text)
            except ET.ParseError as e:
                logger.error(f"DG Market RSS parse error: {e}")
                return

            channel = root.find("channel")
            items = channel.findall("item") if channel is not None else root.findall(".//item")

            for item in items:
                title = (item.findtext("title") or "").strip()
                description = (item.findtext("description") or "").strip()
                link = (item.findtext("link") or "").strip()
                pub_date_str = item.findtext("pubDate")
                pub_date = _parse_date(pub_date_str)

                if pub_date and pub_date.tzinfo and pub_date < cutoff:
                    continue

                full_text = f"{title} {description}"
                if not _matches_keywords(full_text, keywords):
                    continue

                # Extract budget estimate from description
                budget_match = re.search(
                    r"(?:budget|value|amount)[:\s]+([A-Z]{2,3}[\s\d,\.]+)",
                    description, re.I
                )
                budget = budget_match.group(1).strip() if budget_match else None

                # Extract organization
                org_match = re.search(r"(?:agency|organization|authority)[:\s]+([^\n<,]+)", description, re.I)
                organization = org_match.group(1).strip() if org_match else None

                yield RawLead(
                    source="tender",
                    name=title[:200],
                    company=organization,
                    raw_data={
                        "tender_source": "dgmarket",
                        "title": title,
                        "description": description[:1000],
                        "url": link,
                        "published_at": pub_date_str,
                        "estimated_budget": budget,
                        "country": "EG",
                    },
                )


def _clean_text(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    return re.sub(r"\s+", " ", text).strip() or None
