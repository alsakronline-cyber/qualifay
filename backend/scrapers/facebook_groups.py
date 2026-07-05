"""Facebook Ad Library scraper — official Meta Ad Library API (free, never blocked).

Instead of driving a browser against facebook.com (which returns 403 to bots/Tor), this
uses Meta's official Ad Library Graph API. It returns advertisers (page name + id) and their
ad copy for a search term in a country — a solid free source of companies actively spending
on ads. Needs a free access token from a Meta developer account (FACEBOOK_ADLIB_TOKEN).
"""
import logging
from typing import AsyncGenerator

import httpx

from scrapers.base import BaseScraper, RawLead, BlockedError

logger = logging.getLogger(__name__)

ADS_ARCHIVE_URL = "https://graph.facebook.com/v20.0/ads_archive"
AD_FIELDS = "page_name,page_id,ad_creative_bodies,ad_snapshot_url,ad_delivery_start_time"


class FacebookGroupsScraper(BaseScraper):
    source = "facebook"

    async def scrape(self, config: dict, tenant_id: str) -> AsyncGenerator[RawLead, None]:
        from app.core.config import settings

        query = (config.get("query") or "").strip()
        country = (config.get("country") or "EG").upper()
        max_results = min(int(config.get("max_results", 30)), 100)
        if not query:
            raise ValueError("Facebook Ad Library scraper requires 'query' in config")

        token = (config.get("adlib_token") or settings.FACEBOOK_ADLIB_TOKEN or "").strip()
        if not token:
            raise BlockedError(
                "Facebook Ad Library needs an access token. Add FACEBOOK_ADLIB_TOKEN "
                "(free from a Meta developer account) to enable this source."
            )

        params = {
            "access_token": token,
            "search_terms": query,
            "ad_reached_countries": f'["{country}"]',
            "ad_type": "ALL",
            "fields": AD_FIELDS,
            "limit": min(max_results, 100),
        }

        count = 0
        seen_pages: set = set()
        next_url = ADS_ARCHIVE_URL

        async with httpx.AsyncClient(timeout=30) as client:
            while next_url and count < max_results:
                try:
                    # First call uses params; pagination `next` is a full URL with params baked in.
                    if next_url == ADS_ARCHIVE_URL:
                        resp = await client.get(next_url, params=params)
                    else:
                        resp = await client.get(next_url)
                except httpx.RequestError as e:
                    raise BlockedError(f"Facebook Ad Library API unreachable: {e}")

                if resp.status_code != 200:
                    # Surface Meta's own error message (invalid token, permissions, country limits…).
                    try:
                        msg = resp.json().get("error", {}).get("message", resp.text[:150])
                    except Exception:
                        msg = resp.text[:150]
                    raise BlockedError(f"Facebook Ad Library API error: {msg}")

                payload = resp.json()
                ads = payload.get("data", [])
                if not ads:
                    break

                for ad in ads:
                    if count >= max_results:
                        break
                    page_id = ad.get("page_id")
                    page_name = ad.get("page_name")
                    if not page_name or page_id in seen_pages:
                        continue
                    seen_pages.add(page_id)

                    bodies = ad.get("ad_creative_bodies") or []
                    ad_copy = bodies[0] if bodies else None

                    yield RawLead(
                        source=self.source,
                        name=page_name,
                        company=page_name,
                        industry=query,
                        website=f"https://facebook.com/{page_id}" if page_id else None,
                        raw_data={
                            "page_id": page_id,
                            "ad_copy": ad_copy,
                            "ad_snapshot_url": ad.get("ad_snapshot_url"),
                            "source": "fb_ad_library_api",
                        },
                    )
                    count += 1

                next_url = (payload.get("paging") or {}).get("next")
