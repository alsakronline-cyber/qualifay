"""Competitor ad scraper — Facebook Ad Library API + Google Ads Transparency"""
import asyncio
import logging
import random
import re
from typing import AsyncGenerator, Optional
from urllib.parse import urlencode, quote_plus

import httpx

from scrapers.base import BaseScraper, RawLead, BlockedError

logger = logging.getLogger(__name__)

FB_GRAPH_BASE = "https://graph.facebook.com/v19.0"
GOOGLE_ADS_TRANSPARENCY_URL = "https://adstransparency.google.com"


class CompetitorAdsScraper(BaseScraper):
    source = "facebook"
    delay_min = 2.0
    delay_max = 6.0

    async def scrape(self, config: dict, tenant_id: str) -> AsyncGenerator[RawLead, None]:
        """
        config keys:
          search_terms: list[str]       — keywords to search in ad library
          ad_reached_countries: list    — ["EG"] (default)
          ad_type: str                  — "ALL" | "POLITICAL_AND_ISSUE_ADS" (default "ALL")
          limit: int                    — results per page (max 50, default 25)
          fb_access_token: str          — tenant-level Facebook access token
          include_google: bool          — also scrape Google Ads Transparency (default False)
          google_advertiser_query: str  — search term for Google Ads Transparency
        """
        search_terms = config.get("search_terms", [])
        countries = config.get("ad_reached_countries", ["EG"])
        ad_type = config.get("ad_type", "ALL")
        limit = min(int(config.get("limit", 25)), 50)
        include_google = config.get("include_google", False)
        google_query = config.get("google_advertiser_query", "")

        # Resolve Facebook access token
        fb_token = config.get("fb_access_token") or await self._get_tenant_fb_token(tenant_id)

        # Facebook Ad Library API
        if fb_token and search_terms:
            for term in search_terms:
                async for lead in self._scrape_fb_ad_library_api(
                    fb_token, term, countries, ad_type, limit
                ):
                    yield lead
                await self.delay()
        elif search_terms:
            logger.warning(
                "No Facebook access token — skipping FB Ad Library API. "
                "Set fb_access_token in config or tenant settings."
            )

        # Google Ads Transparency (Playwright scrape)
        if include_google and google_query:
            async for lead in self._scrape_google_transparency(google_query):
                yield lead

    # ──────────────────────────────────────────────
    # Facebook Ad Library — official Graph API
    # ──────────────────────────────────────────────
    async def _scrape_fb_ad_library_api(
        self,
        access_token: str,
        search_term: str,
        countries: list[str],
        ad_type: str,
        limit: int,
    ) -> AsyncGenerator[RawLead, None]:
        endpoint = f"{FB_GRAPH_BASE}/ads_archive"
        params = {
            "access_token": access_token,
            "search_terms": search_term,
            "ad_reached_countries": ",".join(countries),
            "ad_type": ad_type,
            "limit": limit,
            "fields": (
                "id,page_name,page_id,ad_creative_body,ad_creative_link_url,"
                "ad_snapshot_url,ad_delivery_start_time,ad_delivery_stop_time,"
                "impressions,spend,currency,ad_creative_link_caption,"
                "ad_creative_link_description,ad_creative_link_title,"
                "bylines,publisher_platforms"
            ),
        }

        headers = {"User-Agent": self.random_ua()}

        async with httpx.AsyncClient(headers=headers, timeout=30) as client:
            after_cursor = None

            while True:
                if after_cursor:
                    params["after"] = after_cursor

                for attempt in range(self.max_retries):
                    try:
                        resp = await client.get(endpoint, params=params)

                        if resp.status_code == 400:
                            error_data = resp.json().get("error", {})
                            error_msg = error_data.get("message", resp.text[:200])
                            logger.error(f"Facebook API 400: {error_msg}")
                            return

                        if resp.status_code == 401:
                            raise BlockedError("Facebook access token invalid/expired (401)")

                        if resp.status_code == 429 or "rate limit" in resp.text.lower():
                            raise BlockedError("Facebook API rate limited (429)")

                        if self.is_blocked(resp.status_code, resp.text):
                            raise BlockedError(f"Facebook API blocked: HTTP {resp.status_code}")

                        resp.raise_for_status()
                        break
                    except BlockedError:
                        raise
                    except httpx.TransportError as e:
                        if attempt == self.max_retries - 1:
                            raise
                        await asyncio.sleep(5 * (attempt + 1))

                data = resp.json()
                ads = data.get("data", [])

                if not ads:
                    break

                for ad in ads:
                    lead = self._fb_ad_to_lead(ad, search_term)
                    if lead:
                        yield lead

                # Pagination
                paging = data.get("paging", {})
                cursors = paging.get("cursors", {})
                after_cursor = cursors.get("after")
                if not after_cursor or not paging.get("next"):
                    break

                await self.delay()

    def _fb_ad_to_lead(self, ad: dict, search_term: str) -> Optional[RawLead]:
        try:
            page_name = ad.get("page_name")
            page_id = ad.get("page_id")
            ad_body = ad.get("ad_creative_body", "")
            link_url = ad.get("ad_creative_link_url")
            snapshot_url = ad.get("ad_snapshot_url")
            spend = ad.get("spend", {})
            impressions = ad.get("impressions", {})

            if not page_name:
                return None

            # Try to extract phone from ad text
            phone = None
            phone_match = re.search(
                r"(?:\+?20[\s\-]?)?(?:01[0-2,5][\s\-]?\d{8}|0?1[0-2,5]\d{8})",
                ad_body or ""
            )
            if phone_match:
                from app.lib.phone import normalize_egyptian_phone
                phone = normalize_egyptian_phone(phone_match.group(0))

            # Extract email from ad body
            email = None
            email_match = re.search(
                r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
                ad_body or ""
            )
            if email_match:
                email = email_match.group(0)

            return RawLead(
                source="facebook",
                name=page_name,
                company=page_name,
                phone=phone,
                email=email,
                website=link_url,
                raw_data={
                    "fb_page_id": page_id,
                    "fb_page_name": page_name,
                    "ad_id": ad.get("id"),
                    "ad_creative_body": ad_body[:500] if ad_body else None,
                    "ad_creative_link_title": ad.get("ad_creative_link_title"),
                    "ad_creative_link_description": ad.get("ad_creative_link_description"),
                    "ad_snapshot_url": snapshot_url,
                    "spend_lower": spend.get("lower_bound"),
                    "spend_upper": spend.get("upper_bound"),
                    "impressions_lower": impressions.get("lower_bound"),
                    "impressions_upper": impressions.get("upper_bound"),
                    "currency": ad.get("currency"),
                    "delivery_start": ad.get("ad_delivery_start_time"),
                    "delivery_stop": ad.get("ad_delivery_stop_time"),
                    "publisher_platforms": ad.get("publisher_platforms", []),
                    "search_term": search_term,
                    "bylines": ad.get("bylines"),
                },
            )
        except Exception as e:
            logger.debug(f"Error parsing FB ad: {e}")
            return None

    # ──────────────────────────────────────────────
    # Google Ads Transparency — Playwright scrape
    # ──────────────────────────────────────────────
    async def _scrape_google_transparency(
        self, query: str
    ) -> AsyncGenerator[RawLead, None]:
        from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

        search_url = (
            f"{GOOGLE_ADS_TRANSPARENCY_URL}/?region=EG"
            f"&advertiser_name={quote_plus(query)}"
        )

        logger.info(f"Scraping Google Ads Transparency: {search_url}")

        viewports = [
            {"width": 1366, "height": 768},
            {"width": 1920, "height": 1080},
        ]

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-blink-features=AutomationControlled",
                ],
            )

            viewport = random.choice(viewports)
            context = await browser.new_context(
                user_agent=self.random_ua(),
                viewport=viewport,
                locale="en-US",
            )

            await context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
            )

            page = await context.new_page()
            try:
                for attempt in range(self.max_retries):
                    try:
                        response = await page.goto(
                            search_url, wait_until="domcontentloaded", timeout=30000
                        )
                        if response and self.is_blocked(response.status, ""):
                            raise BlockedError(f"Google Transparency HTTP {response.status}")
                        break
                    except BlockedError:
                        raise
                    except PlaywrightTimeout:
                        if attempt == self.max_retries - 1:
                            return
                        await asyncio.sleep(5)

                # Wait for results
                try:
                    await page.wait_for_selector(
                        ".advertiser-name, [class*='advertiser'], "
                        "mat-card, .creative-card",
                        timeout=10000
                    )
                except PlaywrightTimeout:
                    logger.debug("Google Transparency: results selector timed out")

                html = await page.content()
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(html, "html.parser")

                # Parse advertiser cards
                advertiser_cards = soup.select(
                    "mat-card, .creative-card, [class*='advertiser-card'], "
                    "[class*='ad-card']"
                )

                for card in advertiser_cards:
                    lead = self._parse_google_transparency_card(card, query)
                    if lead:
                        yield lead

            finally:
                await page.close()
                await context.close()
                await browser.close()

    def _parse_google_transparency_card(self, card, search_term: str) -> Optional[RawLead]:
        try:
            name_el = card.select_one(
                ".advertiser-name, h3, h4, [class*='name'], strong"
            )
            name = name_el.get_text(strip=True) if name_el else None

            ad_text_parts = []
            for el in card.select("p, span"):
                t = el.get_text(strip=True)
                if t and len(t) > 15:
                    ad_text_parts.append(t)
            ad_text = " ".join(ad_text_parts[:2])[:300]

            link_el = card.select_one("a[href*='http']")
            website = link_el.get("href") if link_el else None

            if not name:
                return None

            return RawLead(
                source="facebook",  # using facebook enum for ads category
                name=name,
                company=name,
                website=website,
                raw_data={
                    "ad_source": "google_ads_transparency",
                    "ad_text": ad_text,
                    "search_term": search_term,
                    "region": "EG",
                },
            )
        except Exception as e:
            logger.debug(f"Error parsing Google Transparency card: {e}")
            return None

    async def _get_tenant_fb_token(self, tenant_id: str) -> Optional[str]:
        """Look up tenant-level Facebook access token from tenant settings."""
        try:
            from app.core.database import AsyncSessionLocal
            from app.models.models import Tenant
            from sqlalchemy import select

            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Tenant).where(Tenant.id == tenant_id)
                )
                tenant = result.scalar_one_or_none()
                # tenant.settings JSON would contain fb_access_token if configured
                # For now return None — must be set in config per job
                _ = tenant
        except Exception as e:
            logger.debug(f"Could not fetch tenant FB token: {e}")

        return None
