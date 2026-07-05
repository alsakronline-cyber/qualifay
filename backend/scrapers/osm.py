"""OpenStreetMap business scraper — free, no API key.

Uses Nominatim to geocode the requested location into an OSM area, then queries the
Overpass API for businesses (shops, offices, crafts, companies) in that area that carry
a name and at least one contact detail (phone or website). This is a solid free
replacement for paid B2B databases like Apollo — the data is real, public, and
Egypt-friendly.
"""
import asyncio
import logging
import re
from typing import AsyncGenerator, Optional

import httpx

from scrapers.base import BaseScraper, RawLead, BlockedError
from app.lib.phone import normalize_egyptian_phone

logger = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
# Public Overpass endpoints — fall back across them if one is rate-limited.
OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

# Map common Arabic/English industry keywords to OSM tags so a plain query still
# targets the right kind of business. If nothing matches we fall back to a broad
# "has a name + contact" search filtered by the keyword.
INDUSTRY_TAGS = {
    "pharmacy": '["amenity"="pharmacy"]', "صيدلية": '["amenity"="pharmacy"]', "أدوية": '["amenity"="pharmacy"]',
    "restaurant": '["amenity"="restaurant"]', "مطعم": '["amenity"="restaurant"]', "مطاعم": '["amenity"="restaurant"]',
    "cafe": '["amenity"="cafe"]', "كافيه": '["amenity"="cafe"]',
    "hospital": '["amenity"="hospital"]', "مستشفى": '["amenity"="hospital"]',
    "clinic": '["amenity"="clinic"]', "عيادة": '["amenity"="clinic"]',
    "hotel": '["tourism"="hotel"]', "فندق": '["tourism"="hotel"]', "فنادق": '["tourism"="hotel"]',
    "supermarket": '["shop"="supermarket"]', "سوبر ماركت": '["shop"="supermarket"]',
    "factory": '["man_made"="works"]', "مصنع": '["man_made"="works"]', "مصانع": '["man_made"="works"]',
    "car": '["shop"="car"]', "سيارات": '["shop"="car"]',
    "furniture": '["shop"="furniture"]', "أثاث": '["shop"="furniture"]',
    "clothes": '["shop"="clothes"]', "ملابس": '["shop"="clothes"]',
    "electronics": '["shop"="electronics"]', "إلكترونيات": '["shop"="electronics"]',
    "hardware": '["shop"="hardware"]', "أدوات": '["shop"="hardware"]',
    "construction": '["office"="company"]["company"="construction"]', "مقاولات": '["craft"="builder"]',
    "office": '["office"]', "شركة": '["office"="company"]', "شركات": '["office"="company"]',
    "gym": '["leisure"="fitness_centre"]', "جيم": '["leisure"="fitness_centre"]',
    "school": '["amenity"="school"]', "مدرسة": '["amenity"="school"]',
    "dentist": '["amenity"="dentist"]', "أسنان": '["amenity"="dentist"]',
}

GOVERNORATE_MAP = {
    "cairo": "Cairo", "القاهرة": "Cairo", "giza": "Giza", "الجيزة": "Giza",
    "alexandria": "Alexandria", "الإسكندرية": "Alexandria",
}


def _sanitize_overpass_kw(kw: str) -> str:
    """Strip characters that would break an Overpass regex literal or enable ReDoS.
    Keeps letters (incl. Arabic), digits, spaces and hyphen; caps length."""
    kw = re.sub(r"[^\w\s؀-ۿ-]", "", kw or "")
    return kw.strip()[:60] or "company"


class OSMScraper(BaseScraper):
    """Business database via OpenStreetMap Overpass API."""
    source = "apollo"  # reuse the existing source slot (was Apollo) — no enum migration
    delay_min = 1.0
    delay_max = 2.0

    async def _geocode_bbox(self, client: httpx.AsyncClient, location: str) -> Optional[tuple]:
        """Return an Overpass bounding box (south, west, north, east) for the location.

        Bounding boxes are far more reliable than Overpass area IDs (which require the
        area to be pre-built and often return empty).
        """
        try:
            r = await client.get(
                NOMINATIM_URL,
                params={"q": location, "format": "json", "limit": 1, "countrycodes": "eg"},
                headers={"User-Agent": "Qualifay/1.0 (leadgen; contact@qualifay.io)"},
            )
            if r.status_code != 200:
                return None
            data = r.json()
            if not data:
                return None
            # Nominatim boundingbox = [south, north, west, east]
            bb = data[0].get("boundingbox")
            if not bb:
                return None
            south, north, west, east = (float(x) for x in bb)
            return (south, west, north, east)  # Overpass bbox order
        except Exception as e:
            logger.warning(f"OSM geocode failed for '{location}': {e}")
        return None

    def _resolve_tags(self, query: str, industry: str) -> str:
        text = f"{query} {industry}".lower()
        for kw, tag in INDUSTRY_TAGS.items():
            if kw.lower() in text:
                return tag
        # Broad fallback: any office/shop/craft with a name
        return '["name"]'

    async def scrape(self, config: dict, tenant_id: str) -> AsyncGenerator[RawLead, None]:
        query = (config.get("query") or "").strip()
        industry = (config.get("industry") or "").strip()
        location = (config.get("location") or "Cairo").strip()
        max_results = min(int(config.get("max_results", 25)), 200)

        tag_filter = self._resolve_tags(query, industry)
        ua = {"User-Agent": "Qualifay/1.0 (leadgen; contact@qualifay.io)"}

        async with httpx.AsyncClient(timeout=90, headers=ua) as client:
            bbox = await self._geocode_bbox(client, location)
            await asyncio.sleep(1.0)  # respect Nominatim 1 req/s

            if bbox:
                s, w, n, e = bbox
                box = f"({s},{w},{n},{e})"
                # node+way (points and building outlines); relations are heavy/slow.
                overpass_ql = (
                    f"[out:json][timeout:40];"
                    f"(node{tag_filter}{box};way{tag_filter}{box};);"
                    f"out center tags {max_results * 5};"
                )
            else:
                # Fallback: name text search across Egypt.
                # Sanitize the keyword before interpolating it into the Overpass regex:
                # strip quotes/backslashes/regex metachars so a user query can't break the
                # query or cause ReDoS on the Overpass endpoint.
                kw = _sanitize_overpass_kw(query or industry or "company")
                overpass_ql = (
                    f'[out:json][timeout:40];'
                    f'area["ISO3166-1"="EG"]->.eg;'
                    f'(node["name"~"{kw}",i](area.eg);way["name"~"{kw}",i](area.eg););'
                    f"out center tags {max_results * 5};"
                )

            elements = []
            last_err = None
            for endpoint in OVERPASS_ENDPOINTS:
                try:
                    resp = await client.post(endpoint, data={"data": overpass_ql})
                    if resp.status_code != 200:
                        last_err = f"HTTP {resp.status_code}"
                        continue
                    elements = resp.json().get("elements", [])
                    break
                except (httpx.RequestError, ValueError) as ex:
                    last_err = str(ex)[:80]
                    continue

            if not elements and last_err:
                raise BlockedError(f"Overpass unavailable: {last_err}")

            count = 0
            seen = set()
            for el in elements:
                if count >= max_results:
                    break
                tags = el.get("tags", {})
                name = tags.get("name:en") or tags.get("name")
                if not name:
                    continue

                # Require at least one contact channel to be a usable lead.
                raw_phone = (
                    tags.get("phone") or tags.get("contact:phone")
                    or tags.get("mobile") or tags.get("contact:mobile")
                )
                website = (
                    tags.get("website") or tags.get("contact:website")
                    or tags.get("url")
                )
                if not raw_phone and not website:
                    continue

                # Optional keyword relevance filter when a query was given.
                if query and query.lower() not in f"{name} {tags.get('name','')}".lower():
                    # keep it if the tag_filter already targeted the industry
                    if tag_filter == '["name"]':
                        continue

                dedup_key = (name.lower().strip(), raw_phone or website)
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)

                phone = normalize_egyptian_phone(str(raw_phone)) if raw_phone else None
                city = tags.get("addr:city")
                loc_key = (city or location or "").lower()
                gov = GOVERNORATE_MAP.get(loc_key, city or (location or "").title() or None)
                biz_type = (
                    tags.get("shop") or tags.get("office") or tags.get("amenity")
                    or tags.get("craft") or tags.get("tourism") or "business"
                )

                yield RawLead(
                    source=self.source,
                    name=name,
                    phone=phone,
                    email=tags.get("email") or tags.get("contact:email"),
                    company=name,
                    industry=industry or biz_type,
                    city=city,
                    governorate=gov,
                    website=website,
                    raw_data={
                        "osm_id": el.get("id"),
                        "osm_type": el.get("type"),
                        "business_type": biz_type,
                        "street": tags.get("addr:street"),
                        "lat": el.get("lat") or (el.get("center") or {}).get("lat"),
                        "lon": el.get("lon") or (el.get("center") or {}).get("lon"),
                    },
                )
                count += 1
