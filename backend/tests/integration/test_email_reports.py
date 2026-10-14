"""Email reports: each cold email is recorded, and the record is stamped when the email is
opened (pixel), bounces, gets a reply or the lead unsubscribes. SMTP is stubbed."""
from datetime import datetime

import pytest
from sqlalchemy import select


@pytest.fixture
def smtp(monkeypatch):
    """Capture outgoing messages instead of talking to an SMTP server."""
    from app.services import email_service as es
    sent = []

    def fake_send(self, host, port, user, pwd, from_name, from_email, to, subject, body_text,
                  unsubscribe_url=None, html_body=None):
        sent.append(es.build_message(from_name, from_email or user, to, subject, body_text,
                                     unsubscribe_url, html_body))

    monkeypatch.setattr(es.EmailService, "_send_via_sync", fake_send)
    return sent


@pytest.fixture
def make_mailbox(db):
    async def _make(tenant):
        from app.core.crypto import encrypt
        from app.models.models import EmailAccount
        acct = EmailAccount(tenant_id=tenant.id, from_name="Acme Sales", from_email="sales@acme.test",
                            smtp_host="smtp.acme.test", smtp_port=465, smtp_user="sales@acme.test",
                            smtp_password_enc=encrypt("pw"), status="active",
                            email_started_at=datetime(2026, 1, 1))
        db.add(acct)
        await db.commit()
        return acct
    return _make


def _html_part(msg):
    for part in msg.walk():
        if part.get_content_type() == "text/html":
            return part.get_payload(decode=True).decode()
    return None


async def _email_lead(make_lead, tenant, **kw):
    return await make_lead(tenant, phone=None, email=kw.pop("email", "mona@nile.example"),
                           consent_method="legitimate_interest", consent_at=datetime.utcnow(), **kw)


async def test_send_open_bounce_unsubscribe_and_analytics(client, db, llm, smtp, make_tenant,
                                                          make_lead, make_mailbox):
    from app.models.models import EmailSend
    from app.services.email_inbox_service import _handle_bounce
    from app.services.unsubscribe import make_token
    from app.workers.outreach_tasks import _process_approved_lead

    tenant, _, auth = await make_tenant("Mailco")
    tenant_id = tenant.id
    await make_mailbox(tenant)
    l1 = await _email_lead(make_lead, tenant, email="a@one.example")
    l2 = await _email_lead(make_lead, tenant, email="b@two.example")
    l3 = await _email_lead(make_lead, tenant, email="c@three.example")
    ids = [l1.id, l2.id, l3.id]
    llm.set("consent_checker", {"compliant": True})
    llm.set("aida_writer", "Hello from Acme")

    for lid in ids:
        out = await _process_approved_lead(lid, channel="email")
        assert out.get("sent"), out
    assert len(smtp) == 3

    # Each email: plain text + HTML with the pixel, and one EmailSend row.
    html = _html_part(smtp[0])
    plain = next(p for p in smtp[0].walk() if p.get_content_type() == "text/plain").get_payload(decode=True).decode()
    first_line = plain.strip().splitlines()[0]
    assert html and "/api/v1/webhook/open/" in html and first_line in html   # same words in both parts
    assert smtp[0].get_content_type() == "multipart/alternative"
    sends = {s.lead_id: s for s in (await db.execute(select(EmailSend))).scalars().all()}
    assert set(sends) == set(ids) and all(s.tracked for s in sends.values())

    # Open lead 1 twice (counts both, first-open time kept).
    pixel = html.split('src="', 1)[1].split('"', 1)[0].split("/api/v1/webhook/open/", 1)[1]
    for _ in range(2):
        r = await client.get(f"/api/v1/webhook/open/{pixel}")
        assert r.status_code == 200 and r.headers["content-type"] == "image/gif"
    # A forged pixel still returns the image but records nothing.
    assert (await client.get(f"/api/v1/webhook/open/{ids[1]}.deadbeef.gif")).status_code == 200

    # Lead 2 bounces; lead 3 unsubscribes through the link.
    await _handle_bounce(db, {"body": "Delivery failed for b@two.example", "mailbox_tenant_id": tenant_id})
    await client.get(f"/api/v1/webhook/unsubscribe?token={make_token(ids[2], tenant_id)}")

    db.expire_all()
    rows = {s.lead_id: s for s in (await db.execute(select(EmailSend))).scalars().all()}
    assert rows[ids[0]].open_count == 2 and rows[ids[0]].opened_at
    assert rows[ids[1]].opened_at is None and rows[ids[1]].bounced_at
    assert rows[ids[2]].unsubscribed_at

    r = await client.get("/api/v1/email/analytics?days=30", headers=auth)
    assert r.status_code == 200, r.text
    a = r.json()
    assert a["totals"] == {"sent": 3, "delivered": 2, "opened": 1, "bounced": 1,
                           "replied": 0, "unsubscribed": 1, "tracked": 3}
    assert a["rates"]["open"] == 50.0 and a["rates"]["bounce"] == pytest.approx(33.3)
    assert sum(d["sent"] for d in a["series"]) == 3 and a["tracking_enabled"] is True

    r = await client.get("/api/v1/email/sends?status=bounced", headers=auth)
    assert [i["to_email"] for i in r.json()["items"]] == ["b@two.example"]
    r = await client.get("/api/v1/email/sends?status=not_opened", headers=auth)
    assert {i["to_email"] for i in r.json()["items"]} == {"c@three.example"}
    r = await client.get("/api/v1/email/sends?search=one.example", headers=auth)
    assert r.json()["total"] == 1


async def test_tracking_off_sends_plain_text_only(client, db, llm, smtp, make_tenant, make_lead, make_mailbox):
    from app.models.models import EmailSend
    from app.workers.outreach_tasks import _process_approved_lead
    tenant, _, auth = await make_tenant("Plainco")
    await make_mailbox(tenant)
    lead = await _email_lead(make_lead, tenant)
    lead_id = lead.id
    r = await client.put("/api/v1/email/tracking", json={"enabled": False}, headers=auth)
    assert r.status_code == 200
    llm.set("consent_checker", {"compliant": True})
    llm.set("aida_writer", "Hi")
    await _process_approved_lead(lead_id, channel="email")
    assert smtp[0].get_content_type() == "text/plain"
    db.expire_all()
    send = (await db.execute(select(EmailSend))).scalar_one()
    assert send.tracked is False
    assert (await client.get("/api/v1/email/analytics", headers=auth)).json()["tracking_enabled"] is False


async def test_failed_send_leaves_no_record(db, llm, monkeypatch, make_tenant, make_lead, make_mailbox):
    from app.models.models import EmailSend
    from app.services import email_service as es
    from app.workers.outreach_tasks import _process_approved_lead

    def boom(*a, **kw):
        raise OSError("SMTP down")
    monkeypatch.setattr(es.EmailService, "_send_via_sync", boom)
    tenant, _, _ = await make_tenant("Failco")
    await make_mailbox(tenant)
    lead = await _email_lead(make_lead, tenant)
    llm.set("consent_checker", {"compliant": True})
    llm.set("aida_writer", "Hi")
    out = await _process_approved_lead(lead.id, channel="email")
    assert out.get("error") == "email_send_failed"
    assert (await db.execute(select(EmailSend))).scalars().all() == []


async def test_reports_are_tenant_scoped(client, db, llm, smtp, make_tenant, make_lead, make_mailbox):
    from app.workers.outreach_tasks import _process_approved_lead
    a, _, _ = await make_tenant("Scopea")
    _b, _, auth_b = await make_tenant("Scopeb")
    await make_mailbox(a)
    lead = await _email_lead(make_lead, a)
    llm.set("consent_checker", {"compliant": True})
    llm.set("aida_writer", "Hi")
    await _process_approved_lead(lead.id, channel="email")
    assert (await client.get("/api/v1/email/analytics", headers=auth_b)).json()["totals"]["sent"] == 0
    assert (await client.get("/api/v1/email/sends", headers=auth_b)).json()["items"] == []


async def test_non_admin_cannot_toggle_tracking(client, db, make_tenant):
    from app.models.models import User
    _t, user, auth = await make_tenant("Roleco")
    u = (await db.execute(select(User).where(User.id == user.id))).scalar_one()
    u.is_tenant_admin = False
    await db.commit()
    # Token still claims admin, but require_admin checks the live user dict from the DB.
    r = await client.put("/api/v1/email/tracking", json={"enabled": False}, headers=auth)
    assert r.status_code == 403
