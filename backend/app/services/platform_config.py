"""Editable platform config — per-plan limits + global feature flags. Stored as one JSON
row (platform_settings) that the owner edits; falls back to these defaults for any missing
key, so the app always has a complete config even before anything is saved."""
from sqlalchemy import select

# A limit of 0 means "unlimited".
DEFAULT_CONFIG = {
    "plan_limits": {
        "trial":   {"wa_instances": 3, "monthly_leads": 500},
        "starter": {"wa_instances": 3, "monthly_leads": 500},
        "growth":  {"wa_instances": 3, "monthly_leads": 5000},
        "agency":  {"wa_instances": 0, "monthly_leads": 0},
    },
    "features": {
        "allow_signups": True,   # allow new company registrations
        "scraping": True,
        "ai_replies": True,
    },
}


def _merge(base: dict, override: dict) -> dict:
    out = {k: dict(v) if isinstance(v, dict) else v for k, v in base.items()}
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = {**out[k], **v}
        else:
            out[k] = v
    return out


async def get_platform_config(db) -> dict:
    from app.models.models import PlatformSettings
    row = (await db.execute(select(PlatformSettings).where(PlatformSettings.id == "singleton"))).scalar_one_or_none()
    return _merge(DEFAULT_CONFIG, (row.data if row else {}) or {})


async def get_plan_limit(db, plan: str, key: str) -> int:
    """The numeric limit for a plan (0 = unlimited)."""
    cfg = await get_platform_config(db)
    return int(cfg.get("plan_limits", {}).get(plan, {}).get(key, 0) or 0)


async def feature_enabled(db, name: str) -> bool:
    cfg = await get_platform_config(db)
    return bool(cfg.get("features", {}).get(name, True))
