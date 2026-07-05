"""Egyptian business directory scrapers — Kompass Egypt + 365EG"""
import asyncio
import logging
import re
from typing import AsyncGenerator, Optional
from urllib.parse import urljoin, urlencode, quote_plus

import httpx
from bs4 import BeautifulSoup

from scrapers.base import BaseScraper, RawLead, BlockedError
from app.lib.phone import normalize_egyptian_phone

logger = logging.getLogger(__name__)


def _clean(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    return re.sub(r"\s+", " ", text).strip() or None


class DirectoriesScraper(BaseScraper):
    source = "web_scrape"
    delay_min = 3.0
    delay_max = 7.0

    async def scrape(self, config: dict, tenant_id: str) -> AsyncGenerator[RawLead, None]:
        """
        config keys:
          source: "kompass" | "365eg"
          category: str      — business category / keyword
          city: str          — city filter (optional)
          page: int          — starting page (default 1)
          max_pages: int     — max pages to scrape (default 5)
        """
        source_name = config.get("source", "kompass").lower()
        category = config.get("category", "")
        city = config.get("city", "")
        start_page = int(config.get("page", 1))
        max_pages = int(config.get("max_pages", 5))

        if source_name == "kompass":
            async for lead in self._scrape_kompass(category, city, start_page, max_pages):
                yield lead
        elif source_name == "365eg":
            async for lead in self._scrape_365eg(category, city, start_page, max_pages):
                yield lead
        else:
            raise ValueError(f"Unknown directory source: {source_name}")

    # ──────────────────────────────────────────────
    # Kompass Egypt
    # ──────────────────────────────────────────────
    async def _scrape_kompass(
        self, category: str, city: str, start_page: int, max_pages: int
    ) -> AsyncGenerator[RawLead, None]:
        base_url = "https://eg.kompass.com"
        headers = {
            "User-Agent": self.random_ua(),
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer": base_url,
        }

        async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=30) as client:
            for page_num in range(start_page, start_page + max_pages):
                params = {
                    "text": category,
                    "page": page_num,
                }
                if city:
                    params["city"] = city

                url = f"{base_url}/searchCompanies?" + urlencode(params)
                logger.info(f"Kompass page {page_num}: {url}")

                for attempt in range(self.max_retries):
                    try:
                        resp = await client.get(url)
                        if self.is_blocked(resp.status_code, resp.text):
                            raise BlockedError(
                                f"Kompass blocked: HTTP {resp.status_code}"
                            )
                        break
                    except httpx.TransportError as e:
                        if attempt == self.max_retries - 1:
                            raise
                        await asyncio.sleep(5 * (attempt + 1))

                soup = BeautifulSoup(resp.text, "html.parser")
                company_cards = soup.select(".k-card-company, .company-card, article.company")

                if not company_cards:
                    # Try alternate selectors
                    company_cards = soup.select("[class*='company']")

                if not company_cards:
                    logger.info(f"No more Kompass results at page {page_num}")
                    break

                for card in company_cards:
                    lead = self._parse_kompass_card(card, base_url)
                    if lead:
                        yield lead

                await self.delay()

    def _parse_kompass_card(self, card: BeautifulSoup, base_url: str) -> Optional[RawLead]:
        try:
            name_el = card.select_one("h2, h3, .company-name, [class*='name']")
            name = _clean(name_el.get_text()) if name_el else None

            link_el = card.select_one("a[href]")
            detail_url = urljoin(base_url, link_el["href"]) if link_el else None

            phone_el = card.select_one("[class*='phone'], [itemprop='telephone']")
            raw_phone = _clean(phone_el.get_text()) if phone_el else None
            phone = normalize_egyptian_phone(raw_phone) if raw_phone else None

            address_el = card.select_one("[class*='address'], [itemprop='address']")
            address_text = _clean(address_el.get_text()) if address_el else ""

            city = None
            governorate = None
            if address_text:
                parts = [p.strip() for p in address_text.split(",")]
                if parts:
                    city = parts[-1] if len(parts) == 1 else parts[-2]
                    governorate = parts[-1] if len(parts) > 1 else None

            category_el = card.select_one("[class*='category'], [class*='activity']")
            industry = _clean(category_el.get_text()) if category_el else None

            website_el = card.select_one("a[href*='http']:not([href*='kompass'])")
            website = website_el["href"] if website_el else None

            if not name:
                return None

            return RawLead(
                source="web_scrape",
                name=name,
                company=name,
                phone=phone,
                industry=industry,
                city=city,
                governorate=governorate,
                website=website,
                raw_data={
                    "kompass_url": detail_url,
                    "address": address_text,
                },
            )
        except Exception as e:
            logger.debug(f"Error parsing Kompass card: {e}")
            return None

    # ──────────────────────────────────────────────
    # 365EG (365masr.com)
    # ──────────────────────────────────────────────
    async def _scrape_365eg(
        self, category: str, city: str, start_page: int, max_pages: int
    ) -> AsyncGenerator[RawLead, None]:
        base_url = "https://www.365masr.com"
        headers = {
            "User-Agent": self.random_ua(),
            "Accept-Language": "ar,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer": base_url,
        }

        async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=30) as client:
            for page_num in range(start_page, start_page + max_pages):
                # 365masr uses path-based pagination
                cat_slug = quote_plus(category.replace(" ", "-"))
                if city:
                    city_slug = quote_plus(city.replace(" ", "-"))
                    url = f"{base_url}/{city_slug}/{cat_slug}/page/{page_num}/"
                else:
                    url = f"{base_url}/search/?q={quote_plus(category)}&page={page_num}"

                logger.info(f"365EG page {page_num}: {url}")

                for attempt in range(self.max_retries):
                    try:
                        resp = await client.get(url)
                        if self.is_blocked(resp.status_code, resp.text):
                            raise BlockedError(
                                f"365EG blocked: HTTP {resp.status_code}"
                            )
                        break
                    except httpx.TransportError as e:
                        if attempt == self.max_retries - 1:
                            raise
                        await asyncio.sleep(5 * (attempt + 1))

                soup = BeautifulSoup(resp.text, "html.parser")

                # 365masr listing selectors
                listings = soup.select(
                    ".listing-item, .business-item, .company-listing, "
                    ".result-item, article, [class*='listing']"
                )

                if not listings:
                    logger.info(f"No more 365EG results at page {page_num}")
                    break

                for item in listings:
                    lead = self._parse_365eg_item(item, base_url)
                    if lead:
                        yield lead

                await self.delay()

    def _parse_365eg_item(self, item: BeautifulSoup, base_url: str) -> Optional[RawLead]:
        try:
            name_el = item.select_one("h2, h3, .title, .name, [class*='title']")
            name = _clean(name_el.get_text()) if name_el else None

            link_el = item.select_one("a[href]")
            detail_url = urljoin(base_url, link_el["href"]) if link_el else None

            # Phone — 365masr often shows it inline
            phone_el = item.select_one(
                "[class*='phone'], [class*='tel'], span[dir='ltr']"
            )
            raw_phone = _clean(phone_el.get_text()) if phone_el else None
            phone = normalize_egyptian_phone(raw_phone) if raw_phone else None

            # Address
            addr_el = item.select_one("[class*='address'], [class*='location']")
            address_text = _clean(addr_el.get_text()) if addr_el else ""

            city = None
            governorate = None
            if address_text:
                parts = [p.strip() for p in address_text.split(",")]
                if parts:
                    city = parts[0] if parts else None
                    governorate = parts[-1] if len(parts) > 1 else None

            cat_el = item.select_one("[class*='category'], [class*='tag']")
            industry = _clean(cat_el.get_text()) if cat_el else None

            website_el = item.select_one("a[href*='http']:not([href*='365masr'])")
            website = website_el["href"] if website_el else None

            if not name:
                return None

            return RawLead(
                source="web_scrape",
                name=name,
                company=name,
                phone=phone,
                industry=industry,
                city=city,
                governorate=governorate,
                website=website,
                raw_data={
                    "365eg_url": detail_url,
                    "address": address_text,
                },
            )
        except Exception as e:
            logger.debug(f"Error parsing 365EG item: {e}")
            return None
