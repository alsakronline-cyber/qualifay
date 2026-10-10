"""Create the Sdiek Marketing workspace (a separate Qualifay company) with its owner login and
three small-batch Site Factory campaigns. Idempotent — safe to run again.

Run on the server, inside the backend container:
    SDIEK_ADMIN_PASSWORD='…' python -m app.site_factory.setup_workspace --email you@example.com --name "Mohamed Ramadan"
(If SDIEK_ADMIN_PASSWORD isn't set you'll be prompted; the password is never stored in code.)
Then log in with that email, connect a WhatsApp number under WhatsApp, and open /site-factory.
"""
from __future__ import annotations

import argparse
import asyncio
import getpass
import os
from datetime import datetime, timedelta

from sqlalchemy import select

SLUG = "sdiek-marketing"

STARTER_CAMPAIGNS = [
    {"name": "مصانع — العاشر و6 أكتوبر (دفعة تجريبية)", "segment": "manufacturer",
     "areas": ["10th of Ramadan", "6th of October"], "max_new_per_day": 20, "max_intros_per_day": 8},
    {"name": "محلات — مدينة نصر والمعادي (دفعة تجريبية)", "segment": "store",
     "areas": ["Nasr City", "Maadi"], "max_new_per_day": 20, "max_intros_per_day": 8},
    {"name": "عيادات — المعادي ومصر الجديدة (دفعة تجريبية)", "segment": "clinic",
     "areas": ["Maadi", "Heliopolis"], "max_new_per_day": 15, "max_intros_per_day": 6},
]

PROFILE = {
    "business_name": "Sdiek Marketing",
    "offer": "Websites, Google Business Profile, social media setup and WhatsApp automation for Egyptian businesses",
    "website": "https://alsakronline-cyber.github.io/sdiek-marketing/",
    "language": "ar",
}


async def main(email: str, full_name: str, password: str) -> None:
    from passlib.context import CryptContext
    from app.core.database import AsyncSessionLocal, init_db
    from app.models.models import Plan, SiteFactoryCampaign, Subscription, Tenant, User
    from app.site_factory.insights import DEFAULT_PRICES_EGP

    await init_db()
    async with AsyncSessionLocal() as db:
        tenant = (await db.execute(select(Tenant).where(Tenant.slug == SLUG))).scalar_one_or_none()
        if not tenant:
            tenant = Tenant(slug=SLUG, name="Sdiek Marketing", plan=Plan.agency, language="ar", ai_language="masri",
                            tenant_profile=PROFILE, autonomy="copilot", onboarding_done=True, auto_approve=False)
            db.add(tenant)
            await db.flush()
            db.add(Subscription(tenant_id=tenant.id, plan=Plan.agency, status="active", currency="EGP",
                                current_period_end=datetime.utcnow() + timedelta(days=3650)))
            print(f"created workspace {SLUG}")
        else:
            print(f"workspace {SLUG} already exists")

        user = (await db.execute(select(User).where(User.email == email.lower()))).scalar_one_or_none()
        if user and user.tenant_id != tenant.id:
            raise SystemExit(f"{email} already belongs to another company — use a different email for the Sdiek workspace.")
        if not user:
            db.add(User(tenant_id=tenant.id, email=email.lower(), full_name=full_name, language="ar",
                        hashed_password=CryptContext(schemes=["bcrypt"], deprecated="auto").hash(password),
                        is_tenant_admin=True, is_admin=False, status="active"))
            print(f"created owner login {email}")

        existing = {c.name for c in (await db.execute(select(SiteFactoryCampaign).where(
            SiteFactoryCampaign.tenant_id == tenant.id))).scalars().all()}
        for c in STARTER_CAMPAIGNS:
            if c["name"] in existing:
                continue
            db.add(SiteFactoryCampaign(tenant_id=tenant.id, price_egp=DEFAULT_PRICES_EGP["website"],
                                       service_prices=dict(DEFAULT_PRICES_EGP), sender_name=full_name.split()[0],
                                       brand_name="Sdiek Marketing", sources=["google_maps", "osm"], active=True, **c))
            print(f"added campaign: {c['name']}")
        await db.commit()
    print("done — log in, connect a warmed WhatsApp number, then review /site-factory before approving anything.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Create the Sdiek Marketing workspace")
    ap.add_argument("--email", required=True)
    ap.add_argument("--name", default="Mohamed Ramadan")
    a = ap.parse_args()
    pw = os.environ.get("SDIEK_ADMIN_PASSWORD") or getpass.getpass("Password for the Sdiek owner login: ")
    if len(pw) < 10:
        raise SystemExit("Use a password of at least 10 characters.")
    asyncio.run(main(a.email, a.name, pw))
