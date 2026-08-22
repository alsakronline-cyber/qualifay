"""Per-tenant scraper API keys (Apollo / Hunter / Google CSE / Meta Ad Library).

Stored encrypted (app.core.crypto, same as SMTP passwords) in Tenant.scraper_keys_enc as a
JSON dict. Actual values are NEVER returned by the API — only a set/not-set status. When a
scrape job runs, the tenant's keys are injected into the job config; the scrapers already
prefer config keys over the global .env fallback, so a tenant with its own key uses it.
"""
import json
import logging

from sqlalchemy import select

from app.core.crypto import encrypt, decrypt

logger = logging.getLogger(__name__)

# field name -> the scrape-config key the scrapers read
CONFIG_MAP = {
    "apollo": "apollo_api_key",
    "hunter": "hunter_api_key",
    "google_cse_key": "cse_key",
    "google_cse_cx": "cse_cx",
    "facebook_adlib": "adlib_token",
}
KEY_FIELDS = list(CONFIG_MAP.keys())


async def get_keys(db, tenant_id: str) -> dict:
    from app.models.models import Tenant
    t = (await db.execute(select(Tenant).where(Tenant.id == tenant_id))).scalar_one_or_none()
    enc = getattr(t, "scraper_keys_enc", None) if t else None
    if not enc:
        return {}
    try:
        data = json.loads(decrypt(enc))
        return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.warning("scraper key decrypt failed for tenant %s: %s", tenant_id, e)
        return {}


def status(keys: dict) -> dict:
    """set/not-set booleans — safe to return to the client."""
    return {k: bool(keys.get(k)) for k in KEY_FIELDS}


async def set_keys(db, tenant_id: str, updates: dict) -> dict:
    """Merge in only the provided fields; empty string clears that key. Returns status."""
    from app.models.models import Tenant
    t = (await db.execute(select(Tenant).where(Tenant.id == tenant_id))).scalar_one()
    cur = await get_keys(db, tenant_id)
    for k in KEY_FIELDS:
        if k in updates:
            v = (updates[k] or "").strip()
            if v:
                cur[k] = v
            else:
                cur.pop(k, None)
    t.scraper_keys_enc = encrypt(json.dumps(cur)) if cur else None
    await db.commit()
    return status(cur)


async def inject_config(db, tenant_id: str, cfg: dict) -> dict:
    """Add the tenant's own keys into a scrape-job config (scrapers fall back to global when
    absent). Mutates and returns cfg."""
    keys = await get_keys(db, tenant_id)
    for field, cfg_key in CONFIG_MAP.items():
        if keys.get(field):
            cfg[cfg_key] = keys[field]
    return cfg
