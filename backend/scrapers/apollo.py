"""Apollo.io API scraper — official REST API v1"""
import asyncio
import logging
from typing import AsyncGenerator, Optional

import httpx

from scrapers.base import BaseScraper, RawLead, BlockedError
from app.lib.phone import normalize_egyptian_phone

logger = logging.getLogger(__name__)

APOLLO_BASE_URL = "https://api.apollo.io/v1"

# Apollo.io free tier: 50 contacts/day per API key
FREE_TIER_DAILY_LIMIT = 50


class ApolloScraper(BaseScraper):
    source = "apollo"
    delay_min = 1.0
    delay_max = 3.0

    async def scrape(self, config: dict, tenant_id: str) -> AsyncGenerator[RawLead, None]:
        """
        config keys:
          job_titles: list[str]      — e.g. ["CEO", "Founder", "Owner"]
          industries: list[str]      — e.g. ["Technology", "Manufacturing"]
          locations: list[str]       — default ["Egypt"]
          seniority_levels: list[str]— e.g. ["owner", "c_suite", "director"]
          per_page: int              — results per page (max 25 free tier)
          max_pages: int             — max pages to fetch (default 2, ~50 contacts)
          apollo_api_key: str        — tenant-level override API key
        """
        # Resolve API key: tenant config overrides global
        api_key = config.get("apollo_api_key") or await self._get_tenant_api_key(tenant_id)
        if not api_key:
            logger.error(f"No Apollo API key for tenant {tenant_id}")
            raise ValueError("Apollo API key not configured for this tenant")

        job_titles = config.get("job_titles", ["CEO", "Founder", "Owner", "Managing Director"])
        # Accept the generic Growth-schedule config (industry / location / max_results) too,
        # so this works with the autonomous scheduler, not just Apollo-native config.
        industries = config.get("industries") or ([config["industry"]] if config.get("industry") else [])
        locations = config.get("locations") or ([config["location"]] if config.get("location") else ["Egypt"])
        seniority_levels = config.get("seniority_levels", ["owner", "c_suite", "director", "manager"])
        per_page = min(int(config.get("per_page", 25)), 25)  # free tier cap
        max_pages = int(config.get("max_pages") or max(1, int(config.get("max_results", 25)) // 25 + 1))

        headers = {
            "Content-Type": "application/json",
            "Cache-Control": "no-cache",
            "X-Api-Key": api_key,
        }

        async with httpx.AsyncClient(headers=headers, timeout=30) as client:
            for page in range(1, max_pages + 1):
                payload = {
                    "page": page,
                    "per_page": per_page,
                    "person_titles": job_titles,
                    "person_locations": locations,
                    "contact_email_status": ["verified", "guessed", "unavailable",
                                             "bounced", "pending_manual_fulfillment"],
                }
                if industries:
                    payload["organization_industry_tag_ids"] = []
                    payload["q_organization_industries"] = industries
                if seniority_levels:
                    payload["person_seniorities"] = seniority_levels

                for attempt in range(self.max_retries):
                    try:
                        resp = await client.post(
                            f"{APOLLO_BASE_URL}/mixed_people/search",
                            json=payload,
                        )

                        if resp.status_code == 422:
                            logger.error(f"Apollo 422 unprocessable: {resp.text[:500]}")
                            return

                        if resp.status_code == 429:
                            raise BlockedError("Apollo rate limited (429)")

                        if resp.status_code == 401:
                            raise BlockedError("Apollo unauthorized — check API key")

                        if self.is_blocked(resp.status_code, resp.text):
                            raise BlockedError(f"Apollo blocked: HTTP {resp.status_code}")

                        resp.raise_for_status()
                        break
                    except httpx.TransportError as e:
                        if attempt == self.max_retries - 1:
                            raise
                        await asyncio.sleep(5 * (attempt + 1))

                data = resp.json()
                people = data.get("people", []) or data.get("contacts", [])

                if not people:
                    logger.info(f"Apollo returned no results on page {page}")
                    break

                for person in people:
                    lead = self._parse_person(person)
                    if lead:
                        yield lead

                # Check pagination
                pagination = data.get("pagination", {})
                total_pages = pagination.get("total_pages", 1)
                if page >= total_pages:
                    break

                await self.delay()

    def _parse_person(self, person: dict) -> Optional[RawLead]:
        try:
            first_name = person.get("first_name", "")
            last_name = person.get("last_name", "")
            name = f"{first_name} {last_name}".strip() or None

            email = person.get("email")
            if email and not _is_valid_email(email):
                email = None

            # Phone
            raw_phone = (
                person.get("phone_numbers", [{}])[0].get("sanitized_number", "")
                if person.get("phone_numbers")
                else person.get("phone_number", "")
            )
            phone = normalize_egyptian_phone(raw_phone) if raw_phone else None

            linkedin_url = person.get("linkedin_url")

            # Company / organization
            org = person.get("organization") or {}
            company = org.get("name") or person.get("organization_name")
            website = org.get("website_url") or person.get("organization_website_url")
            industry = org.get("industry") or person.get("organization_industry")
            company_size = _map_employee_count(
                org.get("estimated_num_employees")
                or person.get("organization_estimated_num_employees")
            )

            # Location
            city = person.get("city") or org.get("city")
            country = person.get("country") or org.get("country")
            if country and country.lower() not in ("egypt", "eg"):
                return None  # skip non-Egypt contacts

            title = person.get("title", "")

            return RawLead(
                source="apollo",
                name=name,
                email=email,
                phone=phone,
                company=company,
                industry=industry,
                company_size=company_size,
                city=city,
                website=website,
                linkedin_url=linkedin_url,
                raw_data={
                    "apollo_id": person.get("id"),
                    "title": title,
                    "seniority": person.get("seniority"),
                    "departments": person.get("departments", []),
                    "organization_id": org.get("id"),
                },
            )
        except Exception as e:
            logger.debug(f"Error parsing Apollo person: {e}")
            return None

    async def _get_tenant_api_key(self, tenant_id: str) -> Optional[str]:
        """
        Look up tenant-level Apollo API key from DB tenant.settings JSON.
        Falls back to global settings key.
        """
        from app.core.config import settings as app_settings
        try:
            from app.core.database import AsyncSessionLocal
            from app.models.models import Tenant
            from sqlalchemy import select

            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Tenant).where(Tenant.id == tenant_id)
                )
                tenant = result.scalar_one_or_none()
                if tenant:
                    # tenant.settings would be a JSON column if it existed
                    # For now fall back to global key
                    pass
        except Exception as e:
            logger.debug(f"Could not fetch tenant Apollo key: {e}")

        return app_settings.APOLLO_API_KEY or None


def _is_valid_email(email: str) -> bool:
    import re
    return bool(re.match(r"[^@]+@[^@]+\.[^@]+", email))


def _map_employee_count(count: Optional[int]) -> Optional[str]:
    if count is None:
        return None
    if count < 10:
        return "1-10"
    if count < 50:
        return "11-50"
    if count < 200:
        return "51-200"
    if count < 500:
        return "201-500"
    if count < 1000:
        return "501-1000"
    if count < 5000:
        return "1001-5000"
    return "5000+"
