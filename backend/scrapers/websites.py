"""Business website scraper using Playwright + schema.org parsing"""
import asyncio
import json
import logging
import re
from typing import AsyncGenerator, Optional
from urllib.parse import urljoin, urlparse

from scrapers.base import BaseScraper, RawLead, BlockedError
from app.lib.phone import normalize_egyptian_phone

logger = logging.getLogger(__name__)

# Regex patterns
EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
PHONE_RE = re.compile(
    r"(?:\+?20[\s\-]?)?(?:01[0-2,5][\s\-]?\d{8}|0?1[0-2,5]\d{8}|\d{3}[\s\-]\d{4}[\s\-]\d{4})"
)
SOCIAL_RE = {
    "linkedin": re.compile(r"linkedin\.com/(?:company|in)/[\w\-]+", re.I),
    "facebook": re.compile(r"facebook\.com/[\w.\-]+", re.I),
    "twitter": re.compile(r"twitter\.com/[\w\-]+", re.I),
    "instagram": re.compile(r"instagram\.com/[\w.\-]+", re.I),
}

CONTACT_PATHS = ["/contact", "/contact-us", "/contactus", "/about", "/about-us",
                 "/reach-us", "/get-in-touch", "/اتصل-بنا", "/من-نحن"]

SCHEMA_ORG_TYPES = [
    "LocalBusiness", "Organization", "Corporation", "Store",
    "Restaurant", "Hotel", "MedicalOrganization", "EducationalOrganization",
    "ProfessionalService", "HomeAndConstructionBusiness",
]


def _extract_emails(text: str) -> list[str]:
    return list({m for m in EMAIL_RE.findall(text)
                 if not m.endswith((".png", ".jpg", ".gif", ".svg"))})


def _extract_phones(text: str) -> list[str]:
    raw_phones = PHONE_RE.findall(text)
    normalized = []
    for raw in raw_phones:
        n = normalize_egyptian_phone(raw)
        if n and n not in normalized:
            normalized.append(n)
    return normalized


def _extract_social_links(html: str) -> dict:
    links = {}
    for platform, pattern in SOCIAL_RE.items():
        match = pattern.search(html)
        if match:
            links[platform] = "https://" + match.group(0)
    return links


def _parse_schema_org(html: str) -> dict:
    """Extract structured data from JSON-LD schema.org markup."""
    data = {}
    ld_pattern = re.compile(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        re.DOTALL | re.I
    )
    for match in ld_pattern.finditer(html):
        try:
            obj = json.loads(match.group(1).strip())
            # Handle @graph arrays
            if isinstance(obj, dict) and "@graph" in obj:
                items = obj["@graph"]
            elif isinstance(obj, list):
                items = obj
            else:
                items = [obj]

            for item in items:
                if not isinstance(item, dict):
                    continue
                item_type = item.get("@type", "")
                if isinstance(item_type, list):
                    is_org = any(t in SCHEMA_ORG_TYPES for t in item_type)
                else:
                    is_org = item_type in SCHEMA_ORG_TYPES

                if is_org:
                    if "name" in item and not data.get("name"):
                        data["name"] = item["name"]
                    if "description" in item and not data.get("description"):
                        data["description"] = item["description"]
                    if "telephone" in item and not data.get("telephone"):
                        data["telephone"] = item["telephone"]
                    if "email" in item and not data.get("email"):
                        data["email"] = item["email"]
                    if "url" in item and not data.get("url"):
                        data["url"] = item["url"]
                    address = item.get("address", {})
                    if isinstance(address, dict):
                        if "addressLocality" in address and not data.get("city"):
                            data["city"] = address["addressLocality"]
                        if "addressRegion" in address and not data.get("region"):
                            data["region"] = address["addressRegion"]
                    if "sameAs" in item:
                        same_as = item["sameAs"]
                        if isinstance(same_as, str):
                            same_as = [same_as]
                        for url in same_as:
                            if "linkedin.com" in url:
                                data["linkedin"] = url
        except (json.JSONDecodeError, TypeError):
            continue
    return data


class WebsiteScraper(BaseScraper):
    source = "web_scrape"
    delay_min = 2.0
    delay_max = 6.0

    async def scrape(self, config: dict, tenant_id: str) -> AsyncGenerator[RawLead, None]:
        """
        config keys:
          urls: list[str]       — list of website URLs to scrape
          company_names: list   — optional parallel list of company names
        """
        from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

        urls = config.get("urls", [])
        company_names = config.get("company_names", [None] * len(urls))

        if not urls:
            return

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-infobars",
                    "--disable-dev-shm-usage",
                ],
            )

            for idx, url in enumerate(urls):
                company_hint = company_names[idx] if idx < len(company_names) else None

                context = await browser.new_context(
                    user_agent=self.random_ua(),
                    viewport={"width": 1366, "height": 768},
                    locale="en-US",
                    extra_http_headers={
                        "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    },
                )

                # Remove automation indicators
                await context.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                    Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3]});
                    Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
                    window.chrome = {runtime: {}};
                """)

                try:
                    lead = await self._scrape_website(context, url, company_hint)
                    if lead:
                        yield lead
                except BlockedError:
                    logger.warning(f"Blocked while scraping {url}")
                except Exception as e:
                    logger.error(f"Error scraping {url}: {e}")
                finally:
                    await context.close()
                    await self.delay()

            await browser.close()

    async def _scrape_website(self, context, url: str, company_hint: Optional[str]) -> Optional[RawLead]:
        from playwright.async_api import TimeoutError as PlaywrightTimeout

        all_text = ""
        all_html = ""
        schema_data = {}
        emails = []
        phones = []
        social_links = {}

        async def _load_page(page, target_url: str) -> tuple[str, str]:
            """Load page and return (html, text)."""
            try:
                response = await page.goto(
                    target_url, wait_until="domcontentloaded", timeout=20000
                )
                if response and self.is_blocked(response.status, ""):
                    raise BlockedError(f"HTTP {response.status} on {target_url}")
                html = await page.content()
                text = await page.inner_text("body") if await page.query_selector("body") else ""
                return html, text
            except PlaywrightTimeout:
                logger.warning(f"Timeout loading {target_url}")
                return "", ""

        page = await context.new_page()
        try:
            html, text = await _load_page(page, url)
            if html:
                all_html += html
                all_text += " " + text
                schema_data.update(_parse_schema_org(html))

            # Try contact and about pages
            parsed = urlparse(url)
            base_url = f"{parsed.scheme}://{parsed.netloc}"

            for path in CONTACT_PATHS[:4]:  # limit to 4 sub-pages
                sub_url = urljoin(base_url, path)
                if sub_url == url:
                    continue
                sub_html, sub_text = await _load_page(page, sub_url)
                if sub_html:
                    all_html += sub_html
                    all_text += " " + sub_text
                    schema_data.update(_parse_schema_org(sub_html))
                    await asyncio.sleep(1.0)
        finally:
            await page.close()

        # Extract contact info from all collected text/html
        emails = _extract_emails(all_text)
        phones = _extract_phones(all_text)
        social_links = _extract_social_links(all_html)

        # Also check schema.org phone/email
        if schema_data.get("telephone"):
            norm = normalize_egyptian_phone(schema_data["telephone"])
            if norm and norm not in phones:
                phones.insert(0, norm)
        if schema_data.get("email"):
            em = schema_data["email"]
            if em not in emails:
                emails.insert(0, em)

        if not emails and not phones:
            return None  # Nothing found

        name = company_hint or schema_data.get("name")
        city = schema_data.get("city")
        region = schema_data.get("region")

        return RawLead(
            source=self.source,
            name=name,
            company=name,
            phone=phones[0] if phones else None,
            email=emails[0] if emails else None,
            website=url,
            city=city,
            governorate=region,
            linkedin_url=social_links.get("linkedin"),
            raw_data={
                "all_emails": emails,
                "all_phones": phones,
                "social_links": social_links,
                "schema_description": schema_data.get("description"),
            },
        )
