from app.services.email_inbox_service import tenant_mailbox_search


def test_only_business_address_and_bounces():
    q = tenant_mailbox_search("contact@walaa3d.studio", "12-Oct-2026")
    assert q.startswith("(SINCE 12-Oct-2026 ")
    assert 'TO "contact@walaa3d.studio"' in q and 'CC "contact@walaa3d.studio"' in q
    assert 'FROM "mailer-daemon"' in q and "UNSEEN" not in q
