"""Lead enrichment — Hunter.io + Clearbit Autocomplete + phone validation"""
import asyncio
import logging
import re
from typing import AsyncGenerator, Optional
from urllib.parse import quote_plus

import httpx

from scrapers.base import BaseScraper, RawLead, BlockedError
from app.core.config import settings
from app.lib.phone import normalize_egyptian_phone

logger = logging.getLogger(__name__)

HUNTER_BASE = "https://api.hunter.io/v2"
CLEARBIT_AUTOCOMPLETE = "https://autocomplete.clearbit.com/v1/companies/suggest"
CLEARBIT_ENRICH = "https://company.clearbit.com/v2/companies/find"


class EnrichmentScraper(BaseScraper):
    source = "web_scrape"
    delay_min = 1.0
    delay_max = 3.0

    async def scrape(self, config: dict, tenant_id: str) -> AsyncGenerator[RawLead, None]:
        """
        config keys:
          company: str       — company name
          domain: str        — company domain (e.g. "acmecorp.com")
          first_name: str    — contact first name (for email finder)
          last_name: str     — contact last name (for email finder)
          phones: list[str]  — phones to validate and normalize
          enrich_sources: list — ["hunter", "clearbit"] (default both)
        """
        company = config.get("company", "")
        domain = config.get("domain", "")
        first_name = config.get("first_name", "")
        last_name = config.get("last_name", "")
        phones = config.get("phones", [])
        sources = config.get("enrich_sources", ["hunter", "clearbit"])

        enriched = RawLead(
            source="web_scrape",
            name=f"{first_name} {last_name}".strip() or None,
            company=company or None,
            website=f"https://{domain}" if domain else None,
        )

        # Normalize provided phones
        valid_phones = []
        for raw_phone in phones:
            norm = normalize_egyptian_phone(str(raw_phone))
            if norm:
                valid_phones.append(norm)
        if valid_phones:
            enriched.phone = valid_phones[0]
            enriched.raw_data["all_phones"] = valid_phones

        # Hunter.io email finder
        if "hunter" in sources and settings.HUNTER_API_KEY:
            hunter_data = await self._hunter_find_email(
                domain, first_name, last_name
            )
            if hunter_data:
                if not enriched.email:
                    enriched.email = hunter_data.get("email")
                enriched.raw_data["hunter"] = hunter_data

        # Clearbit company autocomplete (free, no key needed)
        if "clearbit" in sources and (company or domain):
            clearbit_data = await self._clearbit_company(company, domain)
            if clearbit_data:
                if not enriched.industry:
                    enriched.industry = clearbit_data.get("industry")
                if not enriched.city:
                    enriched.city = clearbit_data.get("city")
                if not enriched.company_size:
                    enriched.company_size = clearbit_data.get("employees_range")
                enriched.raw_data["clearbit"] = clearbit_data

        # Only yield if we found something meaningful
        if enriched.email or enriched.phone or enriched.industry:
            yield enriched

    async def _hunter_find_email(
        self, domain: str, first_name: str, last_name: str
    ) -> Optional[dict]:
        """
        Hunter.io Email Finder — finds the most likely email for a person at a company.
        POST https://api.hunter.io/v2/email-finder
        """
        if not domain:
            return None

        params = {
            "domain": domain,
            "api_key": settings.HUNTER_API_KEY,
        }
        if first_name:
            params["first_name"] = first_name
        if last_name:
            params["last_name"] = last_name

        headers = {"User-Agent": self.random_ua()}

        async with httpx.AsyncClient(headers=headers, timeout=15) as client:
            for attempt in range(self.max_retries):
                try:
                    resp = await client.get(f"{HUNTER_BASE}/email-finder", params=params)

                    if resp.status_code == 429:
                        raise BlockedError("Hunter.io rate limited")
                    if resp.status_code == 401:
                        logger.error("Hunter.io unauthorized — check HUNTER_API_KEY")
                        return None
                    if resp.status_code == 404:
                        return None  # No email found, not an error

                    resp.raise_for_status()
                    data = resp.json()
                    hunter_result = data.get("data", {})

                    if not hunter_result.get("email"):
                        return None

                    return {
                        "email": hunter_result.get("email"),
                        "score": hunter_result.get("score"),
                        "first_name": hunter_result.get("first_name"),
                        "last_name": hunter_result.get("last_name"),
                        "position": hunter_result.get("position"),
                        "company": hunter_result.get("company"),
                        "sources_count": len(hunter_result.get("sources", [])),
                    }
                except (httpx.TransportError, httpx.TimeoutException) as e:
                    if attempt == self.max_retries - 1:
                        logger.warning(f"Hunter.io request failed: {e}")
                        return None
                    await asyncio.sleep(3)

        return None

    async def _hunter_domain_search(self, domain: str) -> list[dict]:
        """
        Hunter.io Domain Search — find all emails at a domain.
        GET https://api.hunter.io/v2/domain-search
        """
        if not domain or not settings.HUNTER_API_KEY:
            return []

        params = {
            "domain": domain,
            "api_key": settings.HUNTER_API_KEY,
            "limit": 10,
            "type": "personal",
        }

        async with httpx.AsyncClient(timeout=15) as client:
            try:
                resp = await client.get(f"{HUNTER_BASE}/domain-search", params=params)
                if resp.status_code == 429:
                    raise BlockedError("Hunter.io rate limited")
                resp.raise_for_status()
                data = resp.json()
                emails_data = data.get("data", {}).get("emails", [])
                return [
                    {
                        "email": e.get("value"),
                        "first_name": e.get("first_name"),
                        "last_name": e.get("last_name"),
                        "position": e.get("position"),
                        "seniority": e.get("seniority"),
                        "confidence": e.get("confidence"),
                    }
                    for e in emails_data if e.get("value")
                ]
            except Exception as e:
                logger.debug(f"Hunter domain search failed: {e}")
                return []

    async def _clearbit_company(
        self, company_name: str, domain: str
    ) -> Optional[dict]:
        """
        Clearbit Autocomplete — free endpoint, no API key required.
        GET https://autocomplete.clearbit.com/v1/companies/suggest?query=
        """
        query = domain or company_name
        if not query:
            return None

        params = {"query": query}
        headers = {"User-Agent": self.random_ua()}

        async with httpx.AsyncClient(headers=headers, timeout=10) as client:
            for attempt in range(self.max_retries):
                try:
                    resp = await client.get(CLEARBIT_AUTOCOMPLETE, params=params)
                    if resp.status_code == 429:
                        raise BlockedError("Clearbit rate limited")
                    resp.raise_for_status()

                    results = resp.json()
                    if not results:
                        return None

                    # Pick the best match
                    match = None
                    if domain:
                        for r in results:
                            if domain.lower() in (r.get("domain", "")).lower():
                                match = r
                                break
                    if not match and company_name:
                        for r in results:
                            if company_name.lower() in (r.get("name", "")).lower():
                                match = r
                                break
                    if not match:
                        match = results[0]

                    if not match:
                        return None

                    return {
                        "name": match.get("name"),
                        "domain": match.get("domain"),
                        "logo": match.get("logo"),
                        "industry": None,  # Autocomplete doesn't return industry
                        "city": None,
                        "employees_range": None,
                    }

                except (httpx.TransportError, httpx.TimeoutException) as e:
                    if attempt == self.max_retries - 1:
                        logger.debug(f"Clearbit request failed: {e}")
                        return None
                    await asyncio.sleep(2)

        return None


async def enrich_lead(
    company: str = "",
    domain: str = "",
    first_name: str = "",
    last_name: str = "",
    phones: Optional[list] = None,
) -> dict:
    """
    Standalone enrichment helper for direct use in Celery tasks.
    Returns a dict of enriched fields.
    """
    scraper = EnrichmentScraper()
    config = {
        "company": company,
        "domain": domain,
        "first_name": first_name,
        "last_name": last_name,
        "phones": phones or [],
    }

    result = {}
    async for lead in scraper.scrape(config, ""):
        result = {
            "email": lead.email,
            "phone": lead.phone,
            "industry": lead.industry,
            "city": lead.city,
            "company_size": lead.company_size,
            "hunter_data": lead.raw_data.get("hunter"),
            "clearbit_data": lead.raw_data.get("clearbit"),
        }
        break  # Only one result expected

    return result
