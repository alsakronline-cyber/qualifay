"""Google Maps Places API (New) scraper — uses the v1 Text Search endpoint"""
import asyncio
import logging
from typing import AsyncGenerator, Optional

import httpx

from scrapers.base import BaseScraper, RawLead, BlockedError
from app.core.config import settings
from app.lib.phone import normalize_egyptian_phone

logger = logging.getLogger(__name__)

PLACES_NEW_URL = "https://places.googleapis.com/v1/places:searchText"

EGYPT_GOVERNORATES = {
    "cairo": "Cairo", "giza": "Giza", "alexandria": "Alexandria",
    "luxor": "Luxor", "aswan": "Aswan", "asyut": "Asyut",
    "beheira": "Beheira", "beni suef": "Beni Suef",
    "dakahlia": "Dakahlia", "damietta": "Damietta",
    "fayoum": "Fayoum", "gharbia": "Gharbia", "ismailia": "Ismailia",
    "kafr el sheikh": "Kafr El Sheikh", "matruh": "Matruh",
    "minya": "Minya", "monufia": "Monufia", "new valley": "New Valley",
    "north sinai": "North Sinai", "port said": "Port Said",
    "qalyubia": "Qalyubia", "qena": "Qena", "red sea": "Red Sea",
    "sharqia": "Sharqia", "sohag": "Sohag", "south sinai": "South Sinai",
    "suez": "Suez",
}

BUSINESS_TYPE_TO_INDUSTRY = {
    "restaurant": "Food & Beverage", "food": "Food & Beverage",
    "hospital": "Healthcare", "doctor": "Healthcare", "pharmacy": "Healthcare",
    "school": "Education", "university": "Education",
    "bank": "Finance", "finance": "Finance",
    "hotel": "Hospitality",
    "store": "Retail", "shop": "Retail",
    "factory": "Manufacturing", "construction": "Construction",
    "real_estate": "Real Estate", "lawyer": "Legal",
    "accounting": "Accounting", "gym": "Fitness", "salon": "Beauty",
}

# Fields to request from the new Places API
FIELD_MASK = ",".join([
    "places.id",
    "places.displayName",
    "places.formattedAddress",
    "places.addressComponents",
    "places.nationalPhoneNumber",
    "places.internationalPhoneNumber",
    "places.websiteUri",
    "places.types",
    "places.rating",
    "places.userRatingCount",
    "places.businessStatus",
    "places.location",
])


def _extract_city_governorate(components: list) -> tuple[Optional[str], Optional[str]]:
    city = None
    governorate = None
    for comp in components:
        types = comp.get("types", [])
        name = comp.get("longText", "") or comp.get("longName", "")
        if "locality" in types or "sublocality" in types:
            city = name
        if "administrative_area_level_1" in types:
            governorate = EGYPT_GOVERNORATES.get(name.lower(), name)
    return city, governorate


def _extract_industry(types: list) -> Optional[str]:
    for t in types:
        t_lower = t.lower()
        for key, industry in BUSINESS_TYPE_TO_INDUSTRY.items():
            if key in t_lower:
                return industry
    return None


class GoogleMapsScraper(BaseScraper):
    source = "google_maps"
    delay_min = 1.0
    delay_max = 2.0

    async def scrape(self, config: dict, tenant_id: str) -> AsyncGenerator[RawLead, None]:
        """
        config keys:
          query: str        — text search e.g. "software companies Cairo"
          location: str     — city name or "lat,lng" (default: Cairo)
          max_results: int  — cap (default 20, max 60 per 3 pages)
        """
        api_key = settings.GOOGLE_MAPS_API_KEY
        if not api_key:
            raise ValueError("GOOGLE_MAPS_API_KEY not configured")

        query = config.get("query", "")
        location_str = config.get("location", "Cairo")
        max_results = min(int(config.get("max_results", 20)), 60)

        # Build location bias if lat,lng provided; otherwise embed location in query
        location_bias = None
        try:
            lat, lng = [float(x.strip()) for x in location_str.split(",")]
            location_bias = {
                "circle": {
                    "center": {"latitude": lat, "longitude": lng},
                    "radius": 50000.0
                }
            }
            search_query = query
        except (ValueError, AttributeError):
            # Location is a city name — append to query
            search_query = f"{query} in {location_str}" if location_str else query

        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": FIELD_MASK,
        }

        results_count = 0
        next_page_token = None
        seen_ids = set()

        async with httpx.AsyncClient(timeout=30) as client:
            while results_count < max_results:
                await asyncio.sleep(1.0)

                payload = {
                    "textQuery": search_query,
                    "pageSize": min(20, max_results - results_count),
                    "languageCode": "en",
                }
                if location_bias:
                    payload["locationBias"] = location_bias
                if next_page_token:
                    payload["pageToken"] = next_page_token

                try:
                    resp = await client.post(PLACES_NEW_URL, json=payload, headers=headers)
                    if resp.status_code == 429:
                        raise BlockedError("Google Maps quota exceeded")
                    if resp.status_code != 200:
                        error_msg = resp.text[:300]
                        logger.error(f"Places API error {resp.status_code}: {error_msg}")
                        raise RuntimeError(f"Places API returned {resp.status_code}: {error_msg}")
                    data = resp.json()
                except httpx.RequestError as e:
                    logger.error(f"Google Maps request error: {e}")
                    raise

                places = data.get("places", [])
                if not places:
                    break

                for place in places:
                    if results_count >= max_results:
                        return

                    place_id = place.get("id", "")
                    if place_id in seen_ids:
                        continue
                    seen_ids.add(place_id)

                    if place.get("businessStatus") == "PERMANENTLY_CLOSED":
                        continue

                    name = place.get("displayName", {}).get("text", "")
                    raw_phone = (
                        place.get("internationalPhoneNumber")
                        or place.get("nationalPhoneNumber")
                    )
                    phone = normalize_egyptian_phone(raw_phone) if raw_phone else None
                    website = place.get("websiteUri")

                    address_components = place.get("addressComponents", [])
                    city, governorate = _extract_city_governorate(address_components)

                    place_types = place.get("types", [])
                    industry = _extract_industry(place_types)

                    raw_data = {
                        "place_id": place_id,
                        "formatted_address": place.get("formattedAddress"),
                        "rating": place.get("rating"),
                        "user_ratings_total": place.get("userRatingCount"),
                        "types": place_types,
                        "business_status": place.get("businessStatus"),
                        "location": place.get("location"),
                    }

                    yield RawLead(
                        source=self.source,
                        name=name,
                        phone=phone,
                        company=name,
                        industry=industry,
                        city=city,
                        governorate=governorate,
                        website=website,
                        raw_data=raw_data,
                    )
                    results_count += 1

                next_page_token = data.get("nextPageToken")
                if not next_page_token:
                    break
