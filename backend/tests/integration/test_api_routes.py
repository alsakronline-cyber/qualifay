"""API route tests against the real app + database: auth, tenant isolation, the review
actions, unsubscribe links, webhook auth and the admin gate — plus a sweep that every
parameterless GET endpoint answers without a server error."""
import pytest
from sqlalchemy import select


# ── Auth ─────────────────────────────────────────────────────────────────────

async def test_login_me_and_bad_password(client, make_tenant, db):
    _tenant, user, _ = await make_tenant("Authco")
    email = user.email
    r = await client.post("/api/v1/auth/login", data={"username": email, "password": "password123"})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200 and me.json()["email"] == email

    bad = await client.post("/api/v1/auth/login", data={"username": email, "password": "nope-nope"})
    assert bad.status_code == 401


async def test_protected_routes_reject_missing_and_refresh_tokens(client, make_tenant):
    _t, _u, _ = await make_tenant("Tokco")
    assert (await client.get("/api/v1/leads/")).status_code == 401
    r = await client.post("/api/v1/auth/login", data={"username": _u.email, "password": "password123"})
    refresh = r.json()["refresh_token"]
    r = await client.get("/api/v1/leads/", headers={"Authorization": f"Bearer {refresh}"})
    assert r.status_code == 401, "a refresh token must not work as a bearer token"


async def test_suspended_company_is_locked_out(client, db, make_tenant):
    tenant, _u, auth = await make_tenant("Suspco")
    tenant.status = "suspended"
    await db.commit()
    assert (await client.get("/api/v1/auth/me", headers=auth)).status_code == 403


# ── Tenant isolation ─────────────────────────────────────────────────────────

async def test_tenant_cannot_see_or_act_on_another_tenants_lead(client, make_tenant, make_lead):
    a, _, auth_a = await make_tenant("Alpha")
    _b, _, auth_b = await make_tenant("Beta")
    lead = await make_lead(a, stage="pending_review")
    lead_id = lead.id

    assert (await client.get(f"/api/v1/leads/{lead_id}", headers=auth_a)).status_code == 200
    assert (await client.get(f"/api/v1/leads/{lead_id}", headers=auth_b)).status_code == 404
    for action in ("approve", "reject", "take-manually"):
        r = await client.post(f"/api/v1/leads/{lead_id}/{action}", headers=auth_b, json={})
        assert r.status_code == 404, (action, r.status_code)
    listing = await client.get("/api/v1/leads/", headers=auth_b)
    assert listing.status_code == 200 and lead_id not in listing.text
    queue = await client.get("/api/v1/leads/review-queue", headers=auth_b)
    assert lead_id not in queue.text


# ── Review actions ───────────────────────────────────────────────────────────

async def test_reject_and_take_manually(client, db, celery, make_tenant, make_lead):
    from app.models.models import Lead, LeadStage
    tenant, user, auth = await make_tenant("Revco")
    user_id = user.id
    l1 = await make_lead(tenant, stage="pending_review")
    l2 = await make_lead(tenant, stage="pending_review", phone="+201112223334")
    id1, id2 = l1.id, l2.id

    assert (await client.post(f"/api/v1/leads/{id1}/reject", headers=auth, json={})).status_code == 200
    r = await client.post(f"/api/v1/leads/{id2}/take-manually", headers=auth, json={})
    assert r.status_code == 200 and r.json()["assigned_to"] == user_id

    db.expire_all()
    rows = {l.id: l for l in (await db.execute(select(Lead))).scalars().all()}
    assert rows[id1].stage == LeadStage.archived
    assert rows[id2].stage == LeadStage.manual and rows[id2].assigned_to == user_id
    assert not celery.args_for("process_approved_lead"), "reject / take-manually never queue outreach"


# ── Unsubscribe link ─────────────────────────────────────────────────────────

async def test_unsubscribe_link_get_and_one_click_post(client, db, make_tenant, make_lead):
    from app.models.models import Lead, LeadStatus
    from app.services.unsubscribe import unsubscribe_url, PATH
    tenant, _, _ = await make_tenant("Unsubco")
    l1 = await make_lead(tenant, email="a@x.test")
    l2 = await make_lead(tenant, email="b@x.test", phone="+201009998887")
    url1, url2 = unsubscribe_url(l1), unsubscribe_url(l2)
    id1, id2 = l1.id, l2.id
    assert PATH in url1

    def local(url):  # the public link, minus scheme + host
        return "/" + url.split("://", 1)[1].split("/", 1)[1]

    r = await client.get(local(url1))
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    r = await client.post(local(url2))
    assert r.status_code == 200
    # Idempotent: a second click is still a success page.
    assert (await client.get(local(url1))).status_code == 200

    db.expire_all()
    for lid in (id1, id2):
        lead = (await db.execute(select(Lead).where(Lead.id == lid))).scalar_one()
        assert lead.status == LeadStatus.unsubscribed


async def test_unsubscribe_rejects_forged_and_foreign_tokens(client, db, make_tenant, make_lead):
    import jwt
    from app.api.auth import create_access_token
    from app.models.models import Lead, LeadStatus
    tenant, user, _ = await make_tenant("Forgeco")
    lead = await make_lead(tenant)
    lead_id = lead.id
    forged = jwt.encode({"lead_id": lead_id, "purpose": "unsubscribe"}, "wrong-key", algorithm="HS256")
    assert (await client.get(f"/api/v1/webhook/unsubscribe?token={forged}")).status_code == 400
    # A login token for the same id is not an unsubscribe token.
    access = create_access_token({"sub": user.id, "lead_id": lead_id})
    assert (await client.get(f"/api/v1/webhook/unsubscribe?token={access}")).status_code == 400
    db.expire_all()
    lead = (await db.execute(select(Lead).where(Lead.id == lead_id))).scalar_one()
    assert lead.status == LeadStatus.active


async def test_unsubscribe_token_cannot_cross_tenants(client, db, make_tenant, make_lead):
    from app.models.models import Lead, LeadStatus
    from app.services.unsubscribe import make_token
    a, _, _ = await make_tenant("Crossa")
    b, _, _ = await make_tenant("Crossb")
    lead = await make_lead(a)
    lead_id, b_id = lead.id, b.id
    await client.get(f"/api/v1/webhook/unsubscribe?token={make_token(lead_id, b_id)}")
    db.expire_all()
    assert (await db.execute(select(Lead).where(Lead.id == lead_id))).scalar_one().status == LeadStatus.active


# ── Webhooks / admin ─────────────────────────────────────────────────────────

async def test_evolution_webhook_requires_api_key(client):
    r = await client.post("/api/v1/webhook/evolution", json={"event": "messages.upsert"})
    assert r.status_code == 401
    r = await client.post("/api/v1/webhook/evolution", json={"event": "x"}, headers={"apikey": "wrong"})
    assert r.status_code == 401


async def test_platform_admin_routes_are_gated(client, db, make_tenant):
    from app.models.models import User
    _t, user, auth = await make_tenant("Gateco")
    user_id = user.id
    assert (await client.get("/api/v1/admin/ai-usage", headers=auth)).status_code == 403
    u = (await db.execute(select(User).where(User.id == user_id))).scalar_one()
    u.is_admin = True
    await db.commit()
    r = await client.get("/api/v1/admin/ai-usage", headers=auth)
    assert r.status_code == 200 and "by_agent" in r.json()


# ── Sweep ────────────────────────────────────────────────────────────────────

def _parameterless_gets():
    from fastapi.routing import APIRoute
    from app.main import app
    paths = set()
    for route in app.routes:
        if isinstance(route, APIRoute) and "GET" in route.methods and "{" not in route.path:
            paths.add(route.path)
    return sorted(paths)


_SWEEP_SKIP = {
    "/api/v1/webhook/unsubscribe",   # needs a token; covered above
}


@pytest.mark.parametrize("path", [p for p in _parameterless_gets() if p not in _SWEEP_SKIP])
async def test_get_endpoint_has_no_server_error(path, client, db, llm, whatsapp, celery, make_tenant):
    from app.models.models import User
    _t, user, auth = await make_tenant("Sweep")
    u = (await db.execute(select(User).where(User.id == user.id))).scalar_one()
    u.is_admin = True   # reach the admin routes too
    await db.commit()
    r = await client.get(path, headers=auth)
    assert r.status_code < 500, f"{path} → {r.status_code}: {r.text[:300]}"
