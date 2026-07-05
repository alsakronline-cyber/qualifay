"""LinkedIn scraper — Playwright + stealth + Tor proxy"""
import asyncio
import logging
import random
import re
from typing import AsyncGenerator, Optional
from urllib.parse import quote_plus, urljoin

from scrapers.base import BaseScraper, RawLead, BlockedError

logger = logging.getLogger(__name__)

VIEWPORTS = [
    {"width": 1366, "height": 768},
    {"width": 1920, "height": 1080},
    {"width": 1440, "height": 900},
    {"width": 1280, "height": 800},
]

LOGIN_WALL_SIGNALS = [
    "join now", "sign in", "log in to see", "create an account",
    "authwall", "linkedin.com/login", "linkedin.com/signup",
]

BLOCKED_SIGNALS = [
    "please verify", "unusual traffic", "suspicious activity",
    "temporarily blocked", "captcha", "checkpoint",
]


def _normalize_company_size(raw: str) -> Optional[str]:
    """Normalize LinkedIn employee count strings."""
    if not raw:
        return None
    raw = raw.lower().replace(",", "").replace(" employees", "").strip()
    ranges = {
        "1-10": "1-10", "11-50": "11-50", "51-200": "51-200",
        "201-500": "201-500", "501-1000": "501-1000",
        "1001-5000": "1001-5000", "5001-10000": "5001-10000",
        "10001+": "10001+", "10,001+": "10001+",
    }
    for k, v in ranges.items():
        if k in raw:
            return v
    # Try to extract numbers
    nums = re.findall(r"\d+", raw)
    if nums:
        return "-".join(nums[:2]) if len(nums) >= 2 else nums[0] + "+"
    return raw[:50]


class LinkedInScraper(BaseScraper):
    source = "linkedin"
    use_tor = True
    delay_min = 5.0
    delay_max = 15.0
    max_retries = 3
    _has_cookie = False

    async def scrape(self, config: dict, tenant_id: str) -> AsyncGenerator[RawLead, None]:
        """
        config keys:
          query: str          — search keywords e.g. "software Egypt"
          location: str       — "Egypt" (default)
          industry: str       — industry filter (optional)
          max_results: int    — max companies to return (default 20)
        """
        from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

        query = config.get("query", "")
        location = config.get("location", "Egypt")
        industry = config.get("industry", "")
        max_results = int(config.get("max_results", 20))

        if not query:
            raise ValueError("LinkedIn scraper requires 'query' in config")

        # A session cookie (li_at) is what makes LinkedIn return data — otherwise it forces
        # a login/authwall on every public request. Tor exit nodes are heavily blocked by
        # LinkedIn, so when a cookie is provided we go direct instead of Tor.
        from app.core.config import settings
        cookie_str = (config.get("session_cookie") or settings.LINKEDIN_COOKIE or "").strip()
        self._has_cookie = bool(cookie_str)

        proxy = None if self._has_cookie else self.get_proxy()
        proxy_config = {"server": proxy} if proxy else None

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                proxy=proxy_config,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-infobars",
                    "--disable-dev-shm-usage",
                    "--window-size=1920,1080",
                ],
            )

            viewport = random.choice(VIEWPORTS)
            context = await browser.new_context(
                user_agent=self.random_ua(),
                viewport=viewport,
                locale="en-US",
                timezone_id="Africa/Cairo",
                extra_http_headers={
                    "Accept-Language": "en-US,en;q=0.9",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "DNT": "1",
                },
            )

            # Inject the LinkedIn session cookie so requests are authenticated.
            if self._has_cookie:
                try:
                    await context.add_cookies(
                        self.parse_cookie_string(cookie_str, ".linkedin.com", default_name="li_at")
                    )
                except Exception as e:
                    logger.warning(f"LinkedIn cookie injection failed: {e}")

            # Stealth: disable automation indicators
            await context.add_init_script("""
                // Mask webdriver
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                // Fake plugins
                Object.defineProperty(navigator, 'plugins', {
                    get: () => {
                        return [
                            {name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer'},
                            {name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai'},
                            {name: 'Native Client', filename: 'internal-nacl-plugin'},
                        ];
                    }
                });
                // Fake languages
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['en-US', 'en']
                });
                // Chrome runtime
                window.chrome = {
                    runtime: {
                        connect: function() {},
                        sendMessage: function() {},
                    }
                };
                // Fix permissions query
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({state: Notification.permission}) :
                        originalQuery(parameters)
                );
            """)

            try:
                results_count = 0
                start = 0

                while results_count < max_results:
                    # Build search URL
                    search_query = f"{query} {location}".strip()
                    if industry:
                        search_query += f" {industry}"

                    encoded_q = quote_plus(search_query)
                    search_url = (
                        f"https://www.linkedin.com/search/results/companies/"
                        f"?keywords={encoded_q}&origin=GLOBAL_SEARCH_HEADER"
                        f"&start={start}"
                    )

                    page = await context.new_page()
                    try:
                        companies = await self._scrape_search_page(
                            page, search_url, max_results - results_count
                        )
                    finally:
                        await page.close()

                    if not companies:
                        break

                    for company_data in companies:
                        if results_count >= max_results:
                            break
                        yield RawLead(
                            source="linkedin",
                            name=company_data.get("name"),
                            company=company_data.get("name"),
                            industry=company_data.get("industry"),
                            company_size=company_data.get("company_size"),
                            city=company_data.get("city"),
                            governorate=company_data.get("governorate"),
                            website=company_data.get("website"),
                            linkedin_url=company_data.get("linkedin_url"),
                            raw_data={
                                "description": company_data.get("description"),
                                "followers": company_data.get("followers"),
                                "headquarters": company_data.get("headquarters"),
                            },
                        )
                        results_count += 1

                    start += 10  # LinkedIn pagination step
                    await self.delay()

            finally:
                await context.close()
                await browser.close()

    async def _scrape_search_page(self, page, url: str, limit: int) -> list[dict]:
        from playwright.async_api import TimeoutError as PlaywrightTimeout

        companies = []

        for attempt in range(self.max_retries):
            try:
                response = await page.goto(url, wait_until="domcontentloaded", timeout=30000)

                if response is None:
                    raise BlockedError("No response from LinkedIn")

                # Check for blocks and login walls
                current_url = page.url
                page_text = await page.inner_text("body") if await page.query_selector("body") else ""
                page_text_lower = page_text.lower()

                if any(s in current_url for s in ["login", "signup", "authwall"]) or \
                        any(s in page_text_lower for s in LOGIN_WALL_SIGNALS):
                    if not self._has_cookie:
                        raise BlockedError(
                            "LinkedIn requires login. Add your LinkedIn session cookie "
                            "(li_at) via LINKEDIN_COOKIE to enable this source — public "
                            "scraping is blocked by LinkedIn."
                        )
                    raise BlockedError("LinkedIn session cookie rejected or expired — refresh li_at.")

                if any(s in page_text_lower for s in BLOCKED_SIGNALS):
                    raise BlockedError("LinkedIn blocking/captcha detected")

                if self.is_blocked(response.status, page_text):
                    raise BlockedError(f"LinkedIn HTTP {response.status}")

                break
            except BlockedError:
                raise
            except PlaywrightTimeout:
                if attempt == self.max_retries - 1:
                    logger.warning("LinkedIn page load timeout")
                    return []
                await asyncio.sleep(5)

        # Wait for search results to render
        try:
            await page.wait_for_selector(
                ".search-results__list, .reusable-search__entity-result-list, "
                "[data-chameleon-result-urn]",
                timeout=10000
            )
        except Exception:
            logger.debug("LinkedIn search results selector not found, trying to parse anyway")

        # Extract company cards
        html = await page.content()
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")

        # LinkedIn search result cards — selectors vary by version
        result_items = soup.select(
            ".reusable-search__result-container, "
            ".search-result__wrapper, "
            "li.reusable-search__result-container, "
            "[data-chameleon-result-urn]"
        )

        for item in result_items[:limit]:
            company = self._parse_company_card(item)
            if company:
                companies.append(company)

        return companies

    def _parse_company_card(self, item) -> Optional[dict]:
        try:
            # Company name
            name_el = item.select_one(
                ".entity-result__title-text a span[aria-hidden='true'], "
                ".actor-name, "
                ".search-result__result-link span"
            )
            name = name_el.get_text(strip=True) if name_el else None

            # LinkedIn URL
            link_el = item.select_one("a.app-aware-link[href*='/company/']")
            linkedin_url = None
            if link_el:
                href = link_el.get("href", "")
                match = re.search(r"linkedin\.com/company/[a-zA-Z0-9\-_]+", href)
                if match:
                    linkedin_url = "https://www." + match.group(0)

            # Subtitle (usually industry + company size)
            subtitle_el = item.select_one(
                ".entity-result__primary-subtitle, "
                ".search-result__truncate"
            )
            subtitle = subtitle_el.get_text(strip=True) if subtitle_el else ""

            # Secondary info (location, followers)
            secondary_el = item.select_one(
                ".entity-result__secondary-subtitle, "
                ".search-result__info"
            )
            secondary = secondary_el.get_text(strip=True) if secondary_el else ""

            # Parse industry from subtitle
            industry = None
            company_size = None
            if subtitle:
                parts = [p.strip() for p in subtitle.split("·")]
                if parts:
                    industry = parts[0] if parts else None
                    if len(parts) > 1:
                        company_size = _normalize_company_size(parts[1])

            # Parse location from secondary
            city = None
            governorate = None
            if secondary:
                loc_parts = secondary.split("·")
                if loc_parts:
                    location_str = loc_parts[0].strip()
                    loc_split = location_str.split(",")
                    if loc_split:
                        city = loc_split[0].strip()
                        if len(loc_split) > 1:
                            governorate = loc_split[-1].strip()

            # Description snippet
            desc_el = item.select_one(
                ".entity-result__summary, .search-result__snippets"
            )
            description = desc_el.get_text(strip=True) if desc_el else None

            if not name and not linkedin_url:
                return None

            return {
                "name": name,
                "linkedin_url": linkedin_url,
                "industry": industry,
                "company_size": company_size,
                "city": city,
                "governorate": governorate,
                "description": description,
                "website": None,  # Can't get website from search cards
                "headquarters": secondary,
            }
        except Exception as e:
            logger.debug(f"Error parsing LinkedIn company card: {e}")
            return None
